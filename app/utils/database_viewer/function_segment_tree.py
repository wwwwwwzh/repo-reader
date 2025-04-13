#!/usr/bin/env python3
"""
Function Segment Tree Builder - Creates a hierarchical view of function segments

This script creates a tree visualization starting from a root function,
showing all its segments and recursively including called functions and
their segments up to a specified depth.

Usage:
  python function_segment_tree.py --repo-hash REPO_HASH --function-id FUNCTION_ID [options]
  python function_segment_tree.py --repo-hash REPO_HASH --function-name FUNCTION_NAME [options]
"""

import argparse
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

def connect_to_db(db_uri):
    """Connect to the database and return a session"""
    try:
        print(f"Connecting to database: {db_uri}")
        engine = create_engine(db_uri)
        Session = sessionmaker(bind=engine)
        session = Session()
        # Test connection
        session.execute(text("SELECT 1"))
        print("Database connection successful!")
        return session, engine
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_function_from_db(session, repo_hash, function_id=None, function_name=None):
    """Get a function from the database by ID or name"""
    if not function_id and not function_name:
        print("Either function_id or function_name must be provided")
        return None
    
    try:
        # Check if the repository exists first
        repo_query = text("SELECT * FROM repositories WHERE id = :repo_hash")
        repo = session.execute(repo_query, {"repo_hash": repo_hash}).fetchone()
        
        if not repo:
            print(f"Repository with hash {repo_hash} not found in the database")
            return None
        
        # If an ID is provided, look up by ID
        if function_id:
            # Check if the ID includes the repo hash prefix
            if ":" not in function_id:
                full_function_id = f"{repo_hash}:{function_id}"
            else:
                full_function_id = function_id
            
            function_query = text("SELECT * FROM functions WHERE id = :func_id")
            function = session.execute(function_query, {"func_id": full_function_id}).fetchone()
            
            if not function:
                # Try without the repo hash prefix
                function_query = text("SELECT * FROM functions WHERE id = :func_id")
                function = session.execute(function_query, {"func_id": function_id}).fetchone()
        
        # If a name is provided, look up by name
        elif function_name:
            # First try exact match on name
            function_query = text("""
                SELECT * FROM functions 
                WHERE repo_id = :repo_hash AND name = :func_name
                LIMIT 1
            """)
            function = session.execute(function_query, {
                "repo_hash": repo_hash,
                "func_name": function_name
            }).fetchone()
            
            # If no match, try partial match on full_name
            if not function:
                function_query = text("""
                    SELECT * FROM functions 
                    WHERE repo_id = :repo_hash AND full_name LIKE :func_name
                    LIMIT 1
                """)
                function = session.execute(function_query, {
                    "repo_hash": repo_hash,
                    "func_name": f"%{function_name}%"
                }).fetchone()
                
                # If still no match, try partial match on name
                if not function:
                    function_query = text("""
                        SELECT * FROM functions 
                        WHERE repo_id = :repo_hash AND name LIKE :func_name
                        LIMIT 1
                    """)
                    function = session.execute(function_query, {
                        "repo_hash": repo_hash,
                        "func_name": f"%{function_name}%"
                    }).fetchone()
        
        if not function:
            print(f"Function not found in repository {repo_hash}")
            return None
        
        # Return both the function and repository
        return function, repo
        
    except Exception as e:
        print(f"Error getting function: {e}")
        return None

def get_segments_for_function(session, function_id, include_content=True):
    """Get all segments for a function"""
    try:
        # Build the query
        query_params = {"function_id": function_id}
        
        # Select appropriate fields
        if include_content:
            query = """
                SELECT id, type, content, lineno, end_lineno, index, target_id, segment_data
                FROM segments
                WHERE function_id = :function_id
                ORDER BY index
            """
        else:
            query = """
                SELECT id, type, lineno, end_lineno, index, target_id, segment_data
                FROM segments
                WHERE function_id = :function_id
                ORDER BY index
            """
        
        # Execute the query
        segments = session.execute(text(query), query_params).fetchall()
        
        return segments
    
    except Exception as e:
        print(f"Error getting segments: {e}")
        return []

def get_function_by_id(session, function_id):
    """Get function by ID"""
    try:
        function_query = text("SELECT * FROM functions WHERE id = :func_id")
        function = session.execute(function_query, {"func_id": function_id}).fetchone()
        return function
    except Exception as e:
        print(f"Error getting function: {e}")
        return None

def build_function_segment_tree(session, function_id, max_depth=3, current_depth=0, 
                                include_content=True, visited_functions=None):
    """
    Build a tree of functions and their segments recursively
    
    Args:
        session: Database session
        function_id: ID of the function to start from
        max_depth: Maximum depth to traverse
        current_depth: Current depth (for recursion)
        include_content: Whether to include segment content
        visited_functions: Set of visited function IDs to prevent cycles
        
    Returns:
        Dictionary representing the tree structure
    """
    if visited_functions is None:
        visited_functions = set()
    
    # Prevent infinite recursion from circular references
    if function_id in visited_functions:
        return {
            "type": "function_ref",
            "id": function_id,
            "name": "CIRCULAR_REFERENCE"
        }
    
    # Mark this function as visited
    visited_functions.add(function_id)
    
    # Get function info
    function = get_function_by_id(session, function_id)
    if not function:
        return {
            "type": "function",
            "id": function_id,
            "name": "UNKNOWN_FUNCTION"
        }
    
    # Start building the tree node for this function
    func_node = {
        "type": "function",
        "id": function_id,
        "name": function[1],  # function.name
        "full_name": function[2],  # function.full_name
        "file_path": function[3],  # function.file_path
        "lineno": function[4],  # function.lineno
        "end_lineno": function[5],  # function.end_lineno
        "is_entry": function[6],  # function.is_entry
        "class_name": function[7],  # function.class_name
        "module_name": function[8],  # function.module_name
        "segments": []
    }
    
    # If we've reached max depth, don't add segments
    if current_depth >= max_depth:
        func_node["truncated"] = True
        return func_node
    
    # Get segments for this function
    segments = get_segments_for_function(session, function_id, include_content)
    
    # Add each segment to the tree
    for segment in segments:
        if include_content:
            segment_id, seg_type, content, lineno, end_lineno, index, target_id, segment_data = segment
        else:
            segment_id, seg_type, lineno, end_lineno, index, target_id, segment_data = segment
            content = None
        
        # Basic segment info
        segment_node = {
            "type": f"segment_{seg_type}",
            "id": segment_id,
            "segment_type": seg_type,
            "lineno": lineno,
            "end_lineno": end_lineno,
            "index": index
        }
        
        # Add content if included
        if include_content and content:
            segment_node["content"] = content
        
        # For call segments, add the target function if it exists
        if seg_type == 'call' and target_id:
            # Recursively add the target function
            target_func = build_function_segment_tree(
                session, target_id, max_depth, current_depth + 1, 
                include_content, visited_functions.copy()
            )
            segment_node["target_function"] = target_func
        
        # Add segment to function node
        func_node["segments"].append(segment_node)
    
    return func_node

def print_tree(node, indent=0, max_content_lines=50):
    """Print the tree in a readable format"""
    # Print indentation
    indent_str = "  " * indent
    
    # print(node)
    
    # Print based on node type
    if node["type"] == "function" or node["type"] == "function_ref":
        # Function node
        print(f"{indent_str}Function: {node['name']} ({node.get('full_name', 'N/A')})")
        print(f"{indent_str}  File: {node.get('file_path', 'N/A')}")
        print(f"{indent_str}  Lines: {node.get('lineno', 'N/A')} - {node.get('end_lineno', 'N/A')}")
        
        # Print truncated message if applicable
        if node.get("truncated"):
            print(f"{indent_str}  [TRUNCATED - Max depth reached]")
            return
        
        # Print segments
        if "segments" in node:
            print(f"{indent_str}  Segments:")
            for segment in node["segments"]:
                print_tree(segment, indent + 2, max_content_lines)
    
    elif node["type"].startswith("segment_"):
        # Segment node
        seg_type = node["segment_type"].upper()
        print(f"{indent_str}[{seg_type}] Line {node.get('lineno', 'N/A')}")
        
        # Print content preview if available
        if "content" in node:
            content_lines = node["content"].split("\n")
            print(f"{indent_str}  Content:")
            
            # Limit the number of lines shown
            preview_lines = content_lines[:max_content_lines]
            for line in preview_lines:
                print(f"{indent_str}    {line}")
            
            # Show message if content was truncated
            if len(content_lines) > max_content_lines:
                print(f"{indent_str}    ... ({len(content_lines) - max_content_lines} more lines)")
        
        # For call segments, print the target function
        if "target_function" in node:
            print(f"{indent_str}  Calls:")
            print_tree(node["target_function"], indent + 2, max_content_lines)

def export_tree_to_json(tree, output_file):
    """Export the tree to a JSON file"""
    try:
        with open(output_file, 'w') as f:
            json.dump(tree, f, indent=2)
        print(f"Tree exported to {output_file}")
        return True
    except Exception as e:
        print(f"Error exporting tree: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Build a function segment tree")
    
    # Function identification (need one of these)
    function_group = parser.add_mutually_exclusive_group(required=True)
    function_group.add_argument("--function-id", help="Function ID")
    function_group.add_argument("--function-name", help="Function name")
    
    # Required arguments
    parser.add_argument("--repo-hash", required=True, help="Repository hash")
    
    # Optional arguments
    parser.add_argument("--db-uri", 
                        default="postgresql://codeuser:<code_password>@localhost:5432/code", 
                        help="Database URI (default: %(default)s)")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="Maximum tree depth (default: %(default)s)")
    parser.add_argument("--output-file", help="Output JSON file")
    parser.add_argument("--no-content", action="store_true",
                        help="Exclude segment content to reduce output size")
    parser.add_argument("--max-content-lines", type=int, default=50,
                        help="Maximum lines of content to display (default: %(default)s)")
    
    args = parser.parse_args()
    
    # Connect to the database
    session, engine = connect_to_db(args.db_uri)
    
    try:
        # Get the function
        function_result = get_function_from_db(
            session, 
            args.repo_hash, 
            args.function_id, 
            args.function_name
        )
        
        if function_result:
            function, repo = function_result
            function_id = function[0]  # function.id
            
            print(f"Building tree for function: {function[2]}")  # function.full_name
            
            # Build the tree
            tree = build_function_segment_tree(
                session,
                function_id,
                args.max_depth,
                include_content=not args.no_content
            )
            
            # Print the tree
            print("\nFUNCTION SEGMENT TREE:")
            print("=" * 80)
            print_tree(tree, max_content_lines=args.max_content_lines)
            
            # Export to JSON if requested
            if args.output_file:
                export_tree_to_json(tree, args.output_file)
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    main()