#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from sqlalchemy import create_engine, text, select, delete
from sqlalchemy.orm import sessionmaker, Session
from dulwich.repo import Repo
from sqlalchemy.dialects.postgresql import insert

import tempfile
import shutil
import hashlib
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
load_dotenv()

Base = declarative_base()
Base.metadata.reflect = True

from app.utils.logging_utils import logger


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.ast_parser import build_registry, build_function_LLM_analysis, build_segments, find_entry_points, build_tree_from_function
from app.utils.llm_function_analyzer import set_api_key, analyze_function
from app.utils.registry_utls import load_registry, save_registry
from app.models import Repository, Function, Segment, FunctionCall, FuncComponent


def hash_url(url, algorithm='sha256'):
    # Convert the URL to bytes
    url_bytes = url.encode('utf-8')
    
    # Initialize the hasher based on the specified algorithm
    if algorithm.lower() == 'sha256':
        hash_object = hashlib.sha256(url_bytes)
    elif algorithm.lower() == 'sha1':
        hash_object = hashlib.sha1(url_bytes)
    elif algorithm.lower() == 'md5':
        hash_object = hashlib.md5(url_bytes)
    else:
        raise ValueError("Unsupported algorithm. Use sha256, sha1, or md5.")
    
    # Return the hexadecimal digest of the hash
    return hash_object.hexdigest()

def _filter_payload(payload: Dict, allowed: Set[str]) -> Dict:
    """Return a dict containing only keys that exist in `allowed`."""
    return {k: v for k, v in payload.items() if k in allowed}



# ──────────────────────────────────
# Helper: make every row homogeneous
# ──────────────────────────────────
def _normalise_rows(rows: List[Dict]) -> None:
    """
    Mutates *rows* in‑place so that every dict has the same keys,
    inserting ``None`` for any missing column.
    """
    if not rows:
        return
    all_cols = {k for row in rows for k in row.keys()}
    for row in rows:
        for col in all_cols:
            row.setdefault(col, None)


def _bulk_upsert(
    session: Session,
    model,
    rows: List[Dict],
    pk_fields: Tuple[str, ...] = ("id",),
) -> None:
    if not rows:
        return

    _normalise_rows(rows)               # ← NEW

    stmt = insert(model).values(rows)
    update_cols = {c.name: c for c in stmt.excluded if c.name not in pk_fields}
    stmt = stmt.on_conflict_do_update(
        index_elements=list(pk_fields),
        set_=update_cols,
    )
    session.execute(stmt)

# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def store_registry_in_database(
    registry,
    repo_url: str,
    repo_hash: str,
    entry_points: List[str],
    session: Session,
):
    """
    Persist a fully‑populated ``FunctionRegistry`` to the database in one
    transaction – no per‑row commits, no ORM instance thrashing.

    Parameters
    ----------
    registry
        Your in‑memory ``FunctionRegistry``.
    repo_url
        GitHub/remote URL of the repository.
    repo_hash
        SHA‑256 (or any hash) used as repository ID.
    entry_points
        List of **raw** function‑IDs (the registry keys) that form the entry
        surface of the app.
    session
        An **active** SQLAlchemy ``Session``.
    """
    ts_now = datetime.now(timezone.utc)

    # ──────────────────────────────────
    # 1. Repository (single row UPSERT)
    # ──────────────────────────────────
    repo_stmt = insert(Repository).values(
        id=repo_hash,
        url=repo_url,
        entry_points=entry_points,
        parsed_at=ts_now,
    ).on_conflict_do_update(
        index_elements=["id"],
        set_={
            "url": repo_url,
            "entry_points": entry_points,
            "parsed_at": ts_now,
        },
    )
    session.execute(repo_stmt)

    # Column name caches – so we filter payloads cheaply
    fn_cols   = set(Function.__table__.columns.keys())
    comp_cols = set(FuncComponent.__table__.columns.keys())
    seg_cols  = set(Segment.__table__.columns.keys())

    # Collections to bulk‑insert / ‑upsert
    fn_rows, comp_rows, seg_rows, call_rows = [], [], [], []

    # ──────────────────────────────────
    # 2. Gather rows from the registry
    # ──────────────────────────────────
    for func_id, info in registry.functions.items():
        db_func_id = f"{repo_hash}:{func_id}"
        is_entry   = func_id in entry_points

        # 2‑a) Function row
        fn_payload = {
            **_filter_payload(info, fn_cols),
            "id": db_func_id,
            "repo_id": repo_hash,
            "is_entry": is_entry,
        }
        fn_rows.append(fn_payload)

        # 2‑b) Components
        for comp in info.get("components", []):
            comp_rows.append({
                **_filter_payload(comp, comp_cols),
                "id": f"{db_func_id}:{comp['id']}",
                "function_id": db_func_id,
            })

        # 2‑c) Segments
        for idx, seg in enumerate(info.get("segments", [])):
            row = {
                **_filter_payload(seg, seg_cols),
                "id": f"{db_func_id}:segment_{idx}",
                "function_id": db_func_id,
                "index": idx,
            }

            # Extra handling for call segments
            if seg.get("type") == "call" and "callee_id" in seg:
                row["target_id"] = f"{repo_hash}:{seg['callee_id']}"
            if seg.get("component_id"):
                row["func_component_id"] = (
                    f"{db_func_id}:{seg['component_id']}"
                )

            # Store misc metadata in `segment_data`
            if seg["type"] in ("call", "comment"):
                row["segment_data"] = {
                    "callee_name": seg.get("callee_name"),
                    "is_standalone": seg.get("is_standalone", True),
                }

            seg_rows.append(row)

        # 2‑d) Call relationships
        for callee in info.get("callees", []):
            call_rows.append({
                "caller_id": db_func_id,
                "callee_id": f"{repo_hash}:{callee}",
                "call_count": 1,
            })

    # ──────────────────────────────────
    # 3. Replace *children* for this repo
    # ──────────────────────────────────
    # (Drop & re‑insert is much simpler than upserting each component/segment.)
    session.execute(
        delete(FuncComponent)
        .where(FuncComponent.id.like(f"{repo_hash}:%"))
    )
    session.execute(
        delete(Segment)
        .where(Segment.id.like(f"{repo_hash}:%"))
    )
    session.execute(
        delete(FunctionCall)
        .where(FunctionCall.caller_id.like(f"{repo_hash}:%"))
    )

    # ──────────────────────────────────
    # 4. Bulk upserts / inserts
    # ──────────────────────────────────
    _bulk_upsert(session, Function, fn_rows, pk_fields=("id",))
    if comp_rows:
        session.bulk_insert_mappings(FuncComponent, comp_rows)
    if seg_rows:
        session.bulk_insert_mappings(Segment, seg_rows)
    if call_rows:
        session.bulk_insert_mappings(FunctionCall, call_rows)

    session.commit()
    return session.get(Repository, repo_hash)




def build_and_store_code_tree(repo_url, entry_points, db_uri, verbose=False, reuse_registry = [False, False, False], force_push=False, batch_size=50):
    """
    Main function to build a code tree and store it in the database
    
    Args:
        repo_url: Repository URL
        entry_points: List of entry point files
        db_uri: Database URI
        verbose: Whether to print verbose output
        
    Returns:
        Repository hash
    """
    logger.info(" ------------------------- ------------------------- ------------------------- -------------------------\n ------------------------- ------------------------- Building started -------------------------  -------------------------\n ------------------------- ------------------------- ------------------------- -------------------------")
    # Create temporary directory for repository
    repo_clone_dir = os.path.join("/home/webadmin/projects/code", "repos")
    # temp_dir = tempfile.mkdtemp(prefix="code_tree_")
    
    registry_dir = "/home/webadmin/projects/code/cache/registry"
    try:
        # Clone the repository
        if verbose:
            logger.info(f"Cloning repository {repo_url}...")
        
        # Create a simple GitManager class if not imported
        class SimpleGitManager:
            def __init__(self, cache_dir):
                self.cache_dir = cache_dir
                os.makedirs(cache_dir, exist_ok=True)
                
            def clone(self, repo_url):
                """Simple clone implementation"""
                from dulwich.porcelain import clone
                
                repo_name = repo_url.split("/")[-1].replace(".git", "")
                repo_hash = hash_url(repo_url, 'sha256')
                repo_path = os.path.join(self.cache_dir, repo_hash)
                logger.info(f"Cloning repository to {repo_path}...")
                
                if os.path.exists(repo_path):
                    if force_push:
                        logger.info(f"Force clone is enabled. Removing existing directory: {repo_path}")
                        shutil.rmtree(repo_path)
                    else:
                        logger.info(f"Directory already exists and force_clone is False: {repo_path}")

                # Clone the repository (this will create the repo_path directory)
                clone(repo_url, repo_path, depth=1)
                
                return Repo(repo_path), repo_path, repo_hash
        
        # Clone repository
        git_manager = SimpleGitManager(repo_clone_dir)
        repo, repo_path, repo_hash = git_manager.clone(repo_url)
        
        
        if verbose:
            logger.info(f"Repository cloned to {repo_path}")
            logger.info(f"Repository hash: {repo_hash}")
        
        # Scan the project
        if verbose:
            logger.info("--------------------------------------------------------------------------------\n----------------------------------------Scanning functions----------------------------------------\n--------------------------------------------------------------------------------")
        
        if reuse_registry[0]:
            registry = load_registry(os.path.join(registry_dir, f"{repo_hash}_1"))
        else:
            registry = build_registry(repo_path)
        
        if verbose:
            logger.info(f"Found {len(registry.functions)} functions")
        
        # Find entry points
        entry_point_ids = []
        for entry_file in entry_points:
            if ':' in entry_file:
                file_path, function_name = entry_file.split(':', 1)
                # Find function by name in the specified file
                for func_id, func_info in registry.functions.items():
                    if (func_info['file_path'].endswith(file_path) and 
                        (func_info['name'] == function_name or 
                         func_info['full_name'].endswith(function_name))):
                        entry_point_ids.append(func_id)
                        if verbose:
                            logger.info(f"Found entry point: {func_info['full_name']}")
            else:
                # Treat the whole file as an entry point
                file_entry_points = []
                for func_id, func_info in registry.functions.items():
                    if func_info['file_path'].endswith(entry_file):
                        file_entry_points.append(func_id)
                        if verbose:
                            logger.info(f"Found entry point: {func_info['full_name']}")
                
                # If we found functions in this file, add them all
                if file_entry_points:
                    entry_point_ids.extend(file_entry_points)
        
        if not entry_point_ids:
            logger.info("No entry points found. Please check your entry point specifications.")
            return None
        
        save_registry(registry, os.path.join(registry_dir,f"{repo_hash}_1"))
        
        logger.info("--------------------------------------------------------------------------------\n----------------------------------------LLM analysis----------------------------------------\n--------------------------------------------------------------------------------")
        if reuse_registry[1]:
            registry = load_registry(os.path.join(registry_dir, f"{repo_hash}_2"))
        else:
            registry = build_function_LLM_analysis(registry)
            save_registry(registry, os.path.join(registry_dir,f"{repo_hash}_2"))
            
        logger.info("--------------------------------------------------------------------------------\n----------------------------------------Segment analysis----------------------------------------\n--------------------------------------------------------------------------------")
        if reuse_registry[2]:
            registry = load_registry(os.path.join(registry_dir, f"{repo_hash}_3"))
        else:
            registry = build_segments(registry, batch_size = batch_size)
            save_registry(registry, os.path.join(registry_dir,f"{repo_hash}_3"))
        
        
        # Connect to the database
        if verbose:
            logger.info("--------------------------------------------------------------------------------\n----------------------------------------Connetting to Database----------------------------------------\n--------------------------------------------------------------------------------")

        
        engine = create_engine(db_uri)
        
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        
        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Store in database
        try:
            if verbose:
                logger.info("Storing data in database...")
            
            repo_record = store_registry_in_database(
                registry, repo_url, repo_hash, entry_point_ids, session
            )
            
            if verbose:
                logger.info(f"Successfully stored data for repository {repo_url}")
                logger.info(f"Repository hash: {repo_hash}")
            
            return repo_hash
            
        except Exception as e:
            session.rollback()
            logger.info(f"Error storing data: {str(e)}")
            raise
        finally:
            session.close()
    
    finally:
        # Clean up
        # shutil.rmtree(temp_dir)
        logger.info("Done building and uploading tree")


def str2bool(v):
    """
    Convert a string to a boolean.
    Accepts: "yes", "true", "t", "1" as True and
    "no", "false", "f", "0" as False (case insensitive).
    """
    if isinstance(v, bool):
        return v
    lower_v = v.lower()
    if lower_v in ('yes', 'true', 't', '1'):
        return True
    elif lower_v in ('no', 'false', 'f', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError(f"Boolean value expected. Got '{v}' instead.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and store a code tree")
    
    # Command subparsers
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Build command
    build_parser = subparsers.add_parser("build", help="Build and store a code tree")
    build_parser.add_argument("repo_url", help="Repository URL")
    build_parser.add_argument("entry_points", nargs="+", help="Entry point files (file.py[:function_name])")
    build_parser.add_argument("--db-uri", 
                            default="postgresql://codeuser:<code_password>@localhost:5432/code",
                            help="Database URI")
    build_parser.add_argument("-f", "--force_push", action="store_true", help="reclone repo even if exist")
    build_parser.add_argument(
        '--reuse_registry',
        nargs=3,  # Expect exactly 3 arguments
        type=str2bool,  # Convert the string inputs to booleans using our helper
        metavar=('BOOL1', 'BOOL2', 'BOOL3'),
        default=[False, False, False],
        help='reuse cache of [functions, llm analysis attached, segments attached]'
    )
    build_parser.add_argument("--batch-size", type=int, default=50, 
                             help="Number of functions to process in each batch during segmentation")
    build_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    # View command
    # view_parser = subparsers.add_parser("view", help="View a function tree")
    # view_parser.add_argument("repo_hash", help="Repository hash")
    # view_parser.add_argument("function_id", help="Function ID")
    # view_parser.add_argument("--level", type=int, default=2, help="Maximum level to print")
    # view_parser.add_argument("--db-uri",
    #                        default="postgresql://codeuser:<code_password>@localhost:5432/code",
    #                        help="Database URI")
    # view_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.command == "build":
        repo_hash = build_and_store_code_tree(
            args.repo_url, args.entry_points, args.db_uri, args.verbose, args.reuse_registry, args.force_push, args.batch_size
        )
        
        if repo_hash:
            logger.info(f"Successfully built and stored code tree for {args.repo_url}")
            logger.info(f"Repository hash: {repo_hash}")
    
    elif args.command == "view":
        print("NO LONGER SUPPORTED")
    
    else:
        parser.print_help()
        
# python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:main   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose
# python /home/webadmin/projects/code/app/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --list-nodes
# python /home/webadmin/projects/code/app/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --node-id "140462637984400" --show-segments
# python -m app.remote_tree_builder view d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9 --list-entries --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code
# python -m app.remote_tree_builder view d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9 main --level 3