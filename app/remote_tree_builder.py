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
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

# Import custom modules for database models and AST parsing
try:
    from app.models import Repository, Function, Segment, FunctionCall
except ImportError:
    # For standalone script, define models here
    
    from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey, DateTime
    from sqlalchemy.dialects.postgresql import JSON
    from sqlalchemy.orm import relationship
    
    
    
    class Repository(Base):
        __tablename__ = 'repositories'
        id = Column(String(64), primary_key=True)
        url = Column(String(512), unique=True)
        entry_points = Column(JSON)
        parsed_at = Column(DateTime)
    
    class Function(Base):
        __tablename__ = 'functions'
        id = Column(String(128), primary_key=True)
        repo_id = Column(String(64), ForeignKey('repositories.id', ondelete='CASCADE'))
        name = Column(String(128))
        full_name = Column(String(512))
        file_path = Column(String(512))
        lineno = Column(Integer)
        end_lineno = Column(Integer)
        is_entry = Column(Boolean, default=False)
        class_name = Column(String(128), nullable=True)
        module_name = Column(String(256))
    
    class Segment(Base):
        __tablename__ = 'segments'
        id = Column(String(256), primary_key=True)
        function_id = Column(String(128), ForeignKey('functions.id', ondelete='CASCADE'))
        type = Column(String(32))
        content = Column(Text)
        lineno = Column(Integer)
        end_lineno = Column(Integer, nullable=True)
        index = Column(Integer)
        target_id = Column(String(128), ForeignKey('functions.id', ondelete='SET NULL'), nullable=True)
        metadata = Column(JSON, nullable=True)
    
    class FunctionCall(Base):
        __tablename__ = 'function_calls'
        caller_id = Column(String(128), ForeignKey('functions.id', ondelete='CASCADE'), primary_key=True)
        callee_id = Column(String(128), ForeignKey('functions.id', ondelete='CASCADE'), primary_key=True)
        call_count = Column(Integer, default=1)
        metadata = Column(JSON, nullable=True)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from app.utils.ast_parser import scan_project, find_entry_points, build_tree_from_function, print_tree, print_function_info
except ImportError:
    # For standalone running, import from the current directory
    from utils.ast_parser import scan_project, find_entry_points, build_tree_from_function, print_tree, print_function_info

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
                segment_data=json.dumps({
                    'callee_name': segment.get('callee_name'),
                    'is_standalone': segment.get('is_standalone', True)
                }) if segment_type in ['call', 'comment'] else None
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
    
    # Final commit for all call relationships
    session.commit()
    
    return repo_record


def clone_repository(repo_url, cache_dir='/tmp/repos'):
    """
    Clone a git repository
    
    Args:
        repo_url: Repository URL
        cache_dir: Directory to cache repositories
        
    Returns:
        Tuple of (repo object, repo path, repo hash)
    """
    from ..utils.git_manager import GitManager
    
    # Ensure cache directory exists
    os.makedirs(cache_dir, exist_ok=True)
    
    # Clone repository
    git_manager = GitManager(cache_dir)
    repo, repo_path = git_manager.clone(repo_url)
    
    # Get repository hash
    repo_hash = repo.head().decode('utf-8')
    
    return repo, repo_path, repo_hash


def build_and_store_code_tree(repo_url, entry_points, db_uri, verbose=False):
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
    # Create temporary directory for repository
    temp_dir = tempfile.mkdtemp(prefix="code_tree_")
    try:
        # Clone the repository
        if verbose:
            print(f"Cloning repository {repo_url}...")
        
        # Create a simple GitManager class if not imported
        class SimpleGitManager:
            def __init__(self, cache_dir):
                self.cache_dir = cache_dir
                os.makedirs(cache_dir, exist_ok=True)
                
            def clone(self, repo_url):
                """Simple clone implementation"""
                from dulwich.porcelain import clone
                
                repo_name = repo_url.split("/")[-1].replace(".git", "")
                repo_path = os.path.join(self.cache_dir, repo_name)
                
                if not os.path.exists(repo_path):
                    clone(repo_url, repo_path, depth=1)
                
                return Repo(repo_path), repo_path
        
        # Clone repository
        git_manager = SimpleGitManager(temp_dir)
        repo, repo_path = git_manager.clone(repo_url)
        repo_hash = repo.head().decode('utf-8')
        
        if verbose:
            print(f"Repository cloned to {repo_path}")
            print(f"Repository hash: {repo_hash}")
        
        # Scan the project
        if verbose:
            print("Scanning project for functions...")
        
        registry = scan_project(repo_path)
        
        if verbose:
            print(f"Found {len(registry.functions)} functions")
        
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
                            print(f"Found entry point: {func_info['full_name']}")
            else:
                # Treat the whole file as an entry point
                file_entry_points = []
                for func_id, func_info in registry.functions.items():
                    if func_info['file_path'].endswith(entry_file):
                        file_entry_points.append(func_id)
                        if verbose:
                            print(f"Found entry point: {func_info['full_name']}")
                
                # If we found functions in this file, add them all
                if file_entry_points:
                    entry_point_ids.extend(file_entry_points)
        
        if not entry_point_ids:
            print("No entry points found. Please check your entry point specifications.")
            return None
        
        # Connect to the database
        if verbose:
            print(f"Connecting to database: {db_uri}")
        
        engine = create_engine(db_uri)
        
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        
        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Store in database
        try:
            if verbose:
                print("Storing data in database...")
            
            repo_record = store_registry_in_database(
                registry, repo_url, repo_hash, entry_point_ids, session
            )
            
            if verbose:
                print(f"Successfully stored data for repository {repo_url}")
                print(f"Repository hash: {repo_hash}")
            
            return repo_hash
            
        except Exception as e:
            session.rollback()
            print(f"Error storing data: {str(e)}")
            raise
        finally:
            session.close()
    
    finally:
        # Clean up
        shutil.rmtree(temp_dir)


def query_and_print_tree(repo_hash, entry_id, db_uri, max_level=2, verbose=False):
    """
    Query the database and print a function tree
    
    Args:
        repo_hash: Repository hash
        entry_id: Entry function ID
        db_uri: Database URI
        max_level: Maximum level to print
        verbose: Whether to print verbose output
    """
    # Connect to database
    engine = create_engine(db_uri)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get repository
        repo = session.query(Repository).filter_by(id=repo_hash).first()
        if not repo:
            print(f"Repository with hash {repo_hash} not found")
            return
        
        # Get entry function
        function = session.query(Function).filter_by(id=entry_id).first()
        if not function:
            print(f"Function with ID {entry_id} not found")
            return
        
        print("=" * 60)
        print(f"FUNCTION TREE: {function.full_name}")
        print(f"Repository: {repo.url}")
        print("=" * 60)
        
        # Get segments for this function
        segments = session.query(Segment).filter_by(function_id=entry_id).order_by(Segment.index).all()
        
        # Print function details
        print(f"Function: {function.name}")
        print(f"Full name: {function.full_name}")
        print(f"File: {function.file_path}")
        print(f"Lines: {function.lineno} - {function.end_lineno}")
        
        # Print segments if level >= 1
        if max_level >= 1:
            print("\nSEGMENTS:")
            for segment in segments:
                print(f"\n  [{segment.type.upper()}] Line {segment.lineno}")
                
                # For call segments, show target
                if segment.type == 'call' and segment.target_id:
                    target = session.query(Function).filter_by(id=segment.target_id).first()
                    if target:
                        print(f"  Calls: {target.full_name}")
                
                # Print content
                content_lines = segment.content.split('\n')
                for i, line in enumerate(content_lines[:10]):  # Limit to 10 lines
                    print(f"    {i+1:3d} | {line}")
                
                if len(content_lines) > 10:
                    print(f"    ... ({len(content_lines)-10} more lines)")
                
                # For call segments with level >= 2, show called function
                if segment.type == 'call' and segment.target_id and max_level >= 2:
                    target = session.query(Function).filter_by(id=segment.target_id).first()
                    if target:
                        # Get segments for the target function
                        target_segments = session.query(Segment).filter_by(
                            function_id=segment.target_id
                        ).order_by(Segment.index).all()
                        
                        print(f"\n  CALLED FUNCTION: {target.name}")
                        print(f"  Full name: {target.full_name}")
                        print(f"  File: {target.file_path}")
                        print(f"  Lines: {target.lineno} - {target.end_lineno}")
                        
                        # Print target segments if level >= 3
                        if max_level >= 3:
                            print("\n  TARGET SEGMENTS:")
                            for target_segment in target_segments:
                                print(f"\n    [{target_segment.type.upper()}] Line {target_segment.lineno}")
                                
                                # Limit content
                                target_content_lines = target_segment.content.split('\n')
                                for i, line in enumerate(target_content_lines[:5]):  # More limited
                                    print(f"      {i+1:3d} | {line}")
                                
                                if len(target_content_lines) > 5:
                                    print(f"      ... ({len(target_content_lines)-5} more lines)")
    finally:
        session.close()


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
    build_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    # View command
    view_parser = subparsers.add_parser("view", help="View a function tree")
    view_parser.add_argument("repo_hash", help="Repository hash")
    view_parser.add_argument("function_id", help="Function ID")
    view_parser.add_argument("--level", type=int, default=2, help="Maximum level to print")
    view_parser.add_argument("--db-uri",
                           default="postgresql://codeuser:<code_password>@localhost:5432/code",
                           help="Database URI")
    view_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.command == "build":
        repo_hash = build_and_store_code_tree(
            args.repo_url, args.entry_points, args.db_uri, args.verbose
        )
        
        if repo_hash:
            print(f"Successfully built and stored code tree for {args.repo_url}")
            print(f"Repository hash: {repo_hash}")
    
    elif args.command == "view":
        query_and_print_tree(
            args.repo_hash, args.function_id, args.db_uri, args.level, args.verbose
        )
    
    else:
        parser.print_help()
        
# python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:main   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose
# python /home/webadmin/projects/code/app/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --list-nodes
# python /home/webadmin/projects/code/app/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --node-id "140462637984400" --show-segments
# python -m app.remote_tree_builder view d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9 --list-entries --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code
# python -m app.remote_tree_builder view d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9 main --level 3