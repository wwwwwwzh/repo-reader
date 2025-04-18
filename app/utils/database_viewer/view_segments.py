#!/usr/bin/env python3
"""
Enhanced Segment Viewer - Utility to view all segments of a function with component organization

Usage:
  python view_segments.py --repo-hash REPO_HASH --function-id FUNCTION_ID
  python view_segments.py --repo-hash REPO_HASH --function-name FUNCTION_NAME
  
Options:
  --repo-hash        Repository hash to query
  --function-id      ID of the function to view segments for
  --function-name    Name of the function to view segments for (will match against full_name)
  --db-uri           Database URI (default: postgresql://codeuser:<code_password>@localhost:5432/code)
  --segment-type     Filter segments by type (code, call, comment)
  --show-target      For call segments, display the target function's code
  --colorize         Add syntax highlighting to code segments
  --by-component     Organize segments by their components
"""

import argparse
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
            
            # If searching by name, suggest similar functions
            if function_name:
                suggest_query = text("""
                    SELECT name, full_name FROM functions 
                    WHERE repo_id = :repo_hash AND (name ILIKE :pattern OR full_name ILIKE :pattern)
                    LIMIT 10
                """)
                
                suggestions = session.execute(suggest_query, {
                    "repo_hash": repo_hash,
                    "pattern": f"%{function_name}%"
                }).fetchall()
                
                if suggestions:
                    print("\nSuggested functions:")
                    for suggestion in suggestions:
                        print(f"- {suggestion[1]} (name: {suggestion[0]})")
            
            return None
        
        # Return both the function and repository
        return function, repo
        
    except Exception as e:
        print(f"Error getting function: {e}")
        return None

def get_segments_for_function(session, function_id, segment_type=None):
    """Get all segments for a function"""
    try:
        # Build the query
        query_params = {"function_id": function_id}
        
        query = """
            SELECT id, type, content, lineno, end_lineno, index, target_id, func_component_id, segment_data
            FROM segments
            WHERE function_id = :function_id
        """
        
        # Add segment type filter if provided
        if segment_type:
            query += " AND type = :segment_type"
            query_params["segment_type"] = segment_type
        
        # Order by index for correct sequence
        query += " ORDER BY index"
        
        # Execute the query
        segments = session.execute(text(query), query_params).fetchall()
        
        return segments
    
    except Exception as e:
        print(f"Error getting segments: {e}")
        return []

def get_components_for_function(session, function_id):
    """Get all components for a function"""
    try:
        query = """
            SELECT id, name, short_description, long_description, start_lineno, end_lineno, index
            FROM func_components
            WHERE function_id = :function_id
            ORDER BY index
        """
        
        components = session.execute(text(query), {"function_id": function_id}).fetchall()
        return components
    
    except Exception as e:
        print(f"Error getting components: {e}")
        return []

def get_target_function(session, target_id):
    """Get target function for a call segment"""
    try:
        function_query = text("SELECT * FROM functions WHERE id = :func_id")
        function = session.execute(function_query, {"func_id": target_id}).fetchone()
        return function
    except Exception as e:
        print(f"Error getting target function: {e}")
        return None

def get_component_by_id(session, component_id):
    """Get component by ID"""
    try:
        component_query = text("SELECT * FROM func_components WHERE id = :comp_id")
        component = session.execute(component_query, {"comp_id": component_id}).fetchone()
        return component
    except Exception as e:
        print(f"Error getting component: {e}")
        return None

def display_segments(session, function, segments, show_target=False, colorize=False, by_component=False):
    """Display segments in a structured format"""
    if not segments:
        print("No segments found for this function")
        return
    
    # Print function information header
    print("\n" + "=" * 80)
    print(f"FUNCTION: {function[2]}")  # function.full_name is at index 2
    print(f"File: {function[3]}")  # function.file_path is at index 3
    print(f"Lines: {function[4]} - {function[5]}")  # function.lineno and end_lineno
    if function[6]:  # function.is_entry
        print("Entry Point: Yes")
    if function[7]:  # function.class_name
        print(f"Class: {function[7]}")
    print(f"Module: {function[8]}")  # function.module_name
    if function[9]:  # function.short_description
        print(f"Description: {function[9]}")
    print("=" * 80)
    
    if by_component:
        # Get all components
        components = get_components_for_function(session, function[0])
        
        if not components:
            print("\nNo components found. Displaying segments sequentially.")
            display_segments_sequentially(session, segments, show_target, colorize)
            return
        
        # Create a mapping of component_id to segments
        component_segments = {}
        unassigned_segments = []
        
        for segment in segments:
            # Get component ID from segment (if any)
            component_id = segment[7]  # func_component_id is at index 7
            
            if component_id and component_id.strip():
                if component_id not in component_segments:
                    component_segments[component_id] = []
                component_segments[component_id].append(segment)
            else:
                unassigned_segments.append(segment)
        
        # Display segments by component
        for component in components:
            comp_id = component[0]
            comp_name = component[1] or f"Component {component[6]}"  # Use index if no name
            comp_desc = component[2]
            
            print(f"\nCOMPONENT: {comp_name}")
            print(f"Description: {comp_desc}")
            print(f"Lines: {component[4]} - {component[5]}")
            print("-" * 80)
            
            if comp_id in component_segments:
                for i, segment in enumerate(component_segments[comp_id]):
                    display_segment(session, segment, i, show_target, colorize)
            else:
                print("No segments in this component")
        
        # Display unassigned segments
        if unassigned_segments:
            print("\nUNASSIGNED SEGMENTS:")
            print("-" * 80)
            for i, segment in enumerate(unassigned_segments):
                display_segment(session, segment, i, show_target, colorize)
    else:
        # Display segments sequentially
        display_segments_sequentially(session, segments, show_target, colorize)

def display_segments_sequentially(session, segments, show_target=False, colorize=False):
    """Display segments in their original sequence"""
    for i, segment in enumerate(segments):
        display_segment(session, segment, i, show_target, colorize)

def display_segment(session, segment, index, show_target=False, colorize=False):
    """Display a single segment"""
    # Unpack segment tuple
    seg_id, seg_type, content, lineno, end_lineno, idx, target_id, component_id, segment_data = segment
    
    # Print segment header
    print(f"\nSEGMENT {index+1}: [{seg_type.upper()}]")
    print(f"Line: {lineno}" + (f" - {end_lineno}" if end_lineno else ""))
    
    # Show component information if available
    if component_id:
        component = get_component_by_id(session, component_id)
        if component:
            print(f"Component: {component[1] or f'Component {component[6]}'}") 
    
    # For call segments, show target if available
    if seg_type == 'call' and target_id:
        target_function = get_target_function(session, target_id)
        if target_function:
            print(f"Calls: {target_function[2]}")  # target_function.full_name
    
    # Print segment content
    print("-" * 80)
    content_lines = content.split('\n')
    for j, line in enumerate(content_lines):
        print(f"{j+1:3d} | {line}")
    
    # For call segments with target display enabled
    if show_target and seg_type == 'call' and target_id:
        target_function = get_target_function(session, target_id)
        if target_function:
            # Get target function segments
            target_segments = get_segments_for_function(session, target_id)
            
            if target_segments:
                print("\n" + "-" * 40)
                print(f"TARGET FUNCTION: {target_function[2]}")
                print(f"File: {target_function[3]}")
                print(f"Lines: {target_function[4]} - {target_function[5]}")
                print("-" * 40)
                
                # Combine all code segments for a simplified view
                target_code = []
                for target_segment in target_segments:
                    if target_segment[1] == 'code':  # segment.type
                        target_code.append(target_segment[2])  # segment.content
                
                if target_code:
                    combined_code = '\n'.join(target_code)
                    code_lines = combined_code.split('\n')
                    for j, line in enumerate(code_lines):
                        print(f"{j+1:3d} | {line}")
                else:
                    print("No code segments found in target function")

def main():
    parser = argparse.ArgumentParser(description="View segments of a function")
    
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
    parser.add_argument("--segment-type", choices=['code', 'call', 'comment'],
                        help="Filter segments by type")
    parser.add_argument("--show-target", action="store_true",
                        help="Show target function code for call segments")
    parser.add_argument("--colorize", action="store_true",
                        help="Add syntax highlighting to code segments")
    parser.add_argument("--by-component", action="store_true",
                        help="Organize segments by their components")
    
    args = parser.parse_args()
    
    # Connect to the database
    session, engine = connect_to_db(args.db_uri)
    
    # Get the function
    function_result = get_function_from_db(
        session, 
        args.repo_hash, 
        args.function_id, 
        args.function_name
    )
    
    if function_result:
        function, repo = function_result
        
        # Get segments for the function
        segments = get_segments_for_function(session, function[0], args.segment_type)
        
        # Display segments
        display_segments(
            session, 
            function, 
            segments, 
            args.show_target, 
            args.colorize,
            args.by_component
        )
    
    session.close()

if __name__ == "__main__":
    main()