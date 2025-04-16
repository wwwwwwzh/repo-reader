#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
import argparse
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dulwich.repo import Repo
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

def store_registry_in_database(registry, repo_url, repo_hash, entry_points, session):
    """
    Store the function registry in the database
    
    Args:
        registry: FunctionRegistry object
        repo_url: Repository URL
        repo_hash: Repository hash
        entry_points: List of entry function IDs
        session: SQLAlchemy session
    
    Returns:
        Repository object
    """
    # Create or update repository record
    repo_record = session.query(Repository).filter_by(id=repo_hash).first()
    if repo_record:
        # Update existing repository
        repo_record.url = repo_url
        repo_record.entry_points = entry_points
        repo_record.parsed_at = datetime.now(timezone.utc)
    else:
        # Create new repository record
        repo_record = Repository(
            id=repo_hash,
            url=repo_url,
            entry_points=entry_points,
            parsed_at=datetime.now(timezone.utc)
        )
        session.add(repo_record)
    
    # Commit to ensure repository exists before adding functions
    session.commit()
    
    # Store functions
    function_count = 0
    for func_id, func_info in registry.functions.items():
        # Create database ID by combining repo hash and function ID
        db_func_id = f"{repo_hash}:{func_id}"
        
        # Check if function is an entry point
        is_entry = func_id in entry_points
        
        # Create or update function record
        func_record = session.query(Function).filter_by(id=db_func_id).first()
        if func_record:
            # Update existing function
            func_record.name = func_info['name']
            func_record.full_name = func_info['full_name']
            func_record.file_path = func_info['file_path']
            func_record.lineno = func_info['lineno']
            func_record.end_lineno = func_info['end_lineno']
            func_record.is_entry = is_entry
            func_record.class_name = func_info.get('class_name')
            func_record.module_name = func_info['module']
        else:
            # Create new function record
            func_record = Function(
                id=db_func_id,
                repo_id=repo_hash,
                name=func_info['name'],
                full_name=func_info['full_name'],
                file_path=func_info['file_path'],
                lineno=func_info['lineno'],
                end_lineno=func_info['end_lineno'],
                is_entry=is_entry,
                class_name=func_info.get('class_name'),
                module_name=func_info['module']
            )
            session.add(func_record)
        
        function_count += 1
        
        # Commit every 50 functions to avoid overwhelming the database
        if function_count % 50 == 0:
            session.commit()
    
    # Commit all functions
    session.commit()
    
    # Store function components
    component_count = 0
    for func_id, func_info in registry.functions.items():
        db_func_id = f"{repo_hash}:{func_id}"
        
        # First delete existing components for this function
        session.query(FuncComponent).filter_by(function_id=db_func_id).delete()
        
        # Add components
        for component in func_info.get('components', []):
            component_id = f"{db_func_id}:{component['id']}"
            
            # Create component record
            component_record = FuncComponent(
                id=component_id,
                function_id=db_func_id,
                short_description=component['short_description'],
                long_description=component['long_description'],
                start_lineno=component['start_lineno'],
                end_lineno=component['end_lineno'],
                index=component['index']
            )
            session.add(component_record)
            
            component_count += 1
            
            # Commit every 50 components
            if component_count % 50 == 0:
                session.commit()
    
    # Commit all components
    session.commit()
    
    # Store segments
    segment_count = 0
    for func_id, func_info in registry.functions.items():
        db_func_id = f"{repo_hash}:{func_id}"
        
        # First delete existing segments for this function
        session.query(Segment).filter_by(function_id=db_func_id).delete()
        
        # Add segments
        for i, segment in enumerate(func_info['segments']):
            segment_id = f"{db_func_id}:segment_{i}"
            segment_type = segment['type']
            
            # For call segments, set the target ID
            target_id = None
            if segment_type == 'call' and 'callee_id' in segment:
                target_id = f"{repo_hash}:{segment['callee_id']}"
            
            # Create segment record
            segment_record = Segment(
                id=segment_id,
                function_id=db_func_id,
                type=segment_type,
                content=segment['content'],
                lineno=segment['lineno'],
                end_lineno=segment.get('end_lineno'),
                index=i,
                target_id=target_id,
                # Add component ID if it exists
                func_component_id=f"{db_func_id}:{segment.get('component_id')}" if segment.get('component_id') else None,
                segment_data={
                    'callee_name': segment.get('callee_name'),
                    'is_standalone': segment.get('is_standalone', True)
                } if segment_type in ['call', 'comment'] else None
            )
            session.add(segment_record)
            
            segment_count += 1
            
            # Commit every a hundred segments
            if segment_count % 100 == 0:
                session.commit()
    
    # Commit all segments
    session.commit()
    
    # Store function calls (many-to-many relationships)
    for func_id, func_info in registry.functions.items():
        db_func_id = f"{repo_hash}:{func_id}"
        
        # First delete existing call relationships for this function
        session.query(FunctionCall).filter_by(caller_id=db_func_id).delete()
        
        # Add call relationships
        for callee_id in func_info['callees']:
            db_callee_id = f"{repo_hash}:{callee_id}"
            
            # Create call record
            call_record = FunctionCall(
                caller_id=db_func_id,
                callee_id=db_callee_id,
                call_count=1  # We could enhance this by counting actual calls
            )
            session.add(call_record)
    
    # commit for all call relationships
    session.commit()
    
    
    
    return repo_record



def build_and_store_code_tree(repo_url, entry_points, db_uri, verbose=False, reuse_registry = [False, False, False], force_push=False):
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
            registry = build_segments(registry)
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
            args.repo_url, args.entry_points, args.db_uri, args.verbose, args.reuse_registry, args.force_push
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