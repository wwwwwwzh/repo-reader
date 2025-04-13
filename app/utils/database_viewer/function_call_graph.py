#!/usr/bin/env python3
"""
Function Call Graph - Utility to generate a call graph for a repository

This script generates a DOT format graph of function calls for a repository.
The graph can be visualized using tools like Graphviz.

For example:
  1. Generate the DOT file: 
     python function_call_graph.py --repo-hash abc123 --output-file calls.dot
  2. Convert to an image: 
     dot -Tpng calls.dot -o calls.png

Usage:
  python function_call_graph.py --repo-hash REPO_HASH --output-file output.dot
  python function_call_graph.py --repo-hash REPO_HASH --function-id FUNCTION_ID --output-file output.dot
  python function_call_graph.py --repo-hash REPO_HASH --function-name FUNCTION_NAME --output-file output.dot
  
Options:
  --repo-hash        Repository hash to query
  --function-id      ID of the root function (optional, if not provided will use entry points)
  --function-name    Name of the root function (optional)
  --output-file      Output file name for the DOT graph
  --db-uri           Database URI (default: postgresql://codeuser:<code_password>@localhost:5432/code)
  --max-depth        Maximum depth for the call graph (default: 3)
  --entry-only       Use only entry points as roots
  --include-modules  List of modules to include (comma separated)
  --exclude-modules  List of modules to exclude (comma separated)
"""

import argparse
import sys
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

def get_repository(session, repo_hash):
    """Get repository info"""
    try:
        repo_query = text("SELECT * FROM repositories WHERE id = :repo_hash")
        repo = session.execute(repo_query, {"repo_hash": repo_hash}).fetchone()
        
        if not repo:
            print(f"Repository with hash {repo_hash} not found in the database")
            return None
        
        return repo
    except Exception as e:
        print(f"Error getting repository: {e}")
        return None

def get_function_by_id_or_name(session, repo_hash, function_id=None, function_name=None):
    """Get a function by ID or name"""
    try:
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
        
        elif function_name:
            # Try exact match on name
            function_query = text("""
                SELECT * FROM functions 
                WHERE repo_id = :repo_hash AND (name = :func_name OR full_name = :func_name)
                LIMIT 1
            """)
            function = session.execute(function_query, {
                "repo_hash": repo_hash,
                "func_name": function_name
            }).fetchone()
            
            # If no match, try partial match
            if not function:
                function_query = text("""
                    SELECT * FROM functions 
                    WHERE repo_id = :repo_hash AND (name LIKE :pattern OR full_name LIKE :pattern)
                    LIMIT 1
                """)
                function = session.execute(function_query, {
                    "repo_hash": repo_hash,
                    "pattern": f"%{function_name}%"
                }).fetchone()
        
        else:
            return None
        
        return function
    
    except Exception as e:
        print(f"Error getting function: {e}")
        return None

def get_entry_points(session, repo_hash):
    """Get all entry point functions for a repository"""
    try:
        # Get entry points from repository if available
        repo_query = text("SELECT entry_points FROM repositories WHERE id = :repo_hash")
        repo_entry_points = session.execute(repo_query, {"repo_hash": repo_hash}).fetchone()
        
        if repo_entry_points and repo_entry_points[0]:
            # Convert entry point IDs to full IDs with repo hash
            entry_point_ids = []
            for entry_id in repo_entry_points[0]:
                if ":" not in entry_id:
                    entry_point_ids.append(f"{repo_hash}:{entry_id}")
                else:
                    entry_point_ids.append(entry_id)
            
            # Query functions with these IDs
            placeholders = ", ".join([f"'{id}'" for id in entry_point_ids])
            function_query = text(f"""
                SELECT * FROM functions 
                WHERE id IN ({placeholders})
            """)
            functions = session.execute(function_query).fetchall()
            
            if functions:
                return functions
        
        # Fall back to functions marked as entry points
        function_query = text("""
            SELECT * FROM functions 
            WHERE repo_id = :repo_hash AND is_entry = TRUE
        """)
        functions = session.execute(function_query, {"repo_hash": repo_hash}).fetchall()
        
        return functions
    
    except Exception as e:
        print(f"Error getting entry points: {e}")
        return []

def get_function_calls(session, function_id, max_depth=3, current_depth=0, 
                      visited=None, include_modules=None, exclude_modules=None):
    """
    Get all function calls recursively up to max_depth
    
    Args:
        session: Database session
        function_id: ID of the function to start from
        max_depth: Maximum depth to traverse
        current_depth: Current depth (for recursion)
        visited: Set of visited function IDs
        include_modules: List of modules to include
        exclude_modules: List of modules to exclude
        
    Returns:
        Dict with nodes and edges for the call graph
    """
    if visited is None:
        visited = set()
    
    if current_depth > max_depth or function_id in visited:
        return {"nodes": [], "edges": []}
    
    visited.add(function_id)
    
    result = {"nodes": [], "edges": []}
    
    try:
        # Get function info
        function_query = text("SELECT * FROM functions WHERE id = :func_id")
        function = session.execute(function_query, {"func_id": function_id}).fetchone()
        
        if not function:
            return result
        
        # Check module filters
        if include_modules and function[8] not in include_modules:  # function.module_name
            return result
        
        if exclude_modules and function[8] in exclude_modules:  # function.module_name
            return result
        
        # Add this function as a node
        result["nodes"].append({
            "id": function[0],  # function.id
            "name": function[1],  # function.name
            "full_name": function[2],  # function.full_name
            "module": function[8],  # function.module_name
            "is_entry": function[6]  # function.is_entry
        })
        
        # If we've reached max depth, don't get children
        if current_depth == max_depth:
            return result
        
        # Get callees
        callees_query = text("""
            SELECT f.* FROM functions f
            JOIN function_calls fc ON fc.callee_id = f.id
            WHERE fc.caller_id = :func_id
        """)
        callees = session.execute(callees_query, {"func_id": function_id}).fetchall()
        
        # Process each callee
        for callee in callees:
            callee_id = callee[0]  # callee.id
            
            # Skip if already visited
            if callee_id in visited:
                # Still add the edge
                result["edges"].append({
                    "from": function_id,
                    "to": callee_id
                })
                continue
            
            # Add edge
            result["edges"].append({
                "from": function_id,
                "to": callee_id
            })
            
            # Recursively get callees
            callee_result = get_function_calls(
                session, callee_id, max_depth, current_depth + 1, 
                visited, include_modules, exclude_modules
            )
            
            # Add to result
            result["nodes"].extend(callee_result["nodes"])
            result["edges"].extend(callee_result["edges"])
        
        return result
    
    except Exception as e:
        print(f"Error getting function calls: {e}")
        return result

def generate_dot_graph(call_graph, output_file):
    """Generate a DOT graph from the call graph"""
    try:
        # Create a mapping of node IDs to names
        node_name_map = {}
        for node in call_graph["nodes"]:
            node_id = node["id"].replace(":", "_")  # Replace colons for DOT format
            node_name_map[node["id"]] = node["name"]
        
        with open(output_file, 'w') as f:
            f.write("digraph CallGraph {\n")
            f.write("  node [shape=box, style=filled, fontname=\"Arial\"];\n")
            f.write("  edge [fontname=\"Arial\"];\n")
            f.write("\n")
            
            # Add nodes
            for node in call_graph["nodes"]:
                # Use full_name instead of ID as the node identifier in the graph
                safe_name = node["full_name"].replace(":", "_").replace(".", "_").replace("-", "_")
                
                # Format the label with module info
                label = node["name"]
                if node["module"]:
                    label = f"{node['name']}\\n({node['module']})"
                
                # Set color based on entry point status
                if node["is_entry"]:
                    f.write(f"  \"{safe_name}\" [label=\"{label}\", fillcolor=\"lightblue\"];\n")
                else:
                    f.write(f"  \"{safe_name}\" [label=\"{label}\", fillcolor=\"lightgrey\"];\n")
                
                # Store mapping for edge creation
                node_name_map[node["id"]] = safe_name
            
            f.write("\n")
            
            # Add edges
            for edge in call_graph["edges"]:
                if edge["from"] in node_name_map and edge["to"] in node_name_map:
                    from_name = node_name_map[edge["from"]]
                    to_name = node_name_map[edge["to"]]
                    f.write(f"  \"{from_name}\" -> \"{to_name}\";\n")
            
            f.write("}\n")
        
        print(f"DOT graph generated: {output_file}")
        print(f"To generate an image, run: dot -Tpng {output_file} -o output.png")
        
        return True
    
    except Exception as e:
        print(f"Error generating DOT graph: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate a function call graph")
    
    # Repository hash is required
    parser.add_argument("--repo-hash", required=True, help="Repository hash")
    
    # Function identification (optional, will use entry points if not provided)
    function_group = parser.add_mutually_exclusive_group()
    function_group.add_argument("--function-id", help="Function ID")
    function_group.add_argument("--function-name", help="Function name")
    
    # Output file
    parser.add_argument("--output-file", required=True, help="Output file name for the DOT graph")
    
    # Optional arguments
    parser.add_argument("--db-uri", 
                        default="postgresql://codeuser:<code_password>@localhost:5432/code", 
                        help="Database URI (default: %(default)s)")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="Maximum depth for the call graph (default: %(default)s)")
    parser.add_argument("--entry-only", action="store_true",
                        help="Use only entry points as roots")
    parser.add_argument("--include-modules", 
                        help="List of modules to include (comma separated)")
    parser.add_argument("--exclude-modules",
                        help="List of modules to exclude (comma separated)")
    
    args = parser.parse_args()
    
    # Connect to the database
    session, engine = connect_to_db(args.db_uri)
    
    # Check if repository exists
    repo = get_repository(session, args.repo_hash)
    if not repo:
        sys.exit(1)
    
    # Process module filters
    include_modules = None
    if args.include_modules:
        include_modules = [m.strip() for m in args.include_modules.split(',')]
    
    exclude_modules = None
    if args.exclude_modules:
        exclude_modules = [m.strip() for m in args.exclude_modules.split(',')]
    
    # Determine root functions
    root_functions = []
    
    if args.function_id or args.function_name:
        # Use specified function
        function = get_function_by_id_or_name(
            session, args.repo_hash, args.function_id, args.function_name
        )
        
        if function:
            root_functions.append(function)
        else:
            print("Specified function not found")
            sys.exit(1)
    elif args.entry_only:
        # Use entry points
        root_functions = get_entry_points(session, args.repo_hash)
        
        if not root_functions:
            print("No entry points found for the repository")
            sys.exit(1)
    else:
        # First try entry points
        root_functions = get_entry_points(session, args.repo_hash)
        
        # If no entry points, use all functions
        if not root_functions:
            print("No entry points found, using all functions as roots (this may take a while)")
            function_query = text("""
                SELECT * FROM functions
                WHERE repo_id = :repo_hash
            """)
            root_functions = session.execute(function_query, {"repo_hash": args.repo_hash}).fetchall()
    
    print(f"Found {len(root_functions)} root functions")
    
    # Generate call graph for each root function
    combined_graph = {"nodes": [], "edges": []}
    visited_nodes = set()
    visited_edges = set()
    
    for root_function in root_functions:
        print(f"Processing function: {root_function[2]}")  # root_function.full_name
        
        # Get call graph
        call_graph = get_function_calls(
            session, 
            root_function[0],  # root_function.id
            args.max_depth,
            include_modules=include_modules,
            exclude_modules=exclude_modules
        )
        
        # Add to combined graph without duplicates
        for node in call_graph["nodes"]:
            node_id = node["id"]
            if node_id not in visited_nodes:
                combined_graph["nodes"].append(node)
                visited_nodes.add(node_id)
        
        for edge in call_graph["edges"]:
            edge_key = (edge["from"], edge["to"])
            if edge_key not in visited_edges:
                combined_graph["edges"].append(edge)
                visited_edges.add(edge_key)
    
    # Generate DOT graph
    if combined_graph["nodes"]:
        generate_dot_graph(combined_graph, args.output_file)
        print(f"Generated call graph with {len(combined_graph['nodes'])} nodes and "
              f"{len(combined_graph['edges'])} edges")
    else:
        print("No functions found for the call graph")
    
    session.close()
if __name__ == "__main__":
    main()
# python /home/webadmin/projects/code/app/utils/database_viewer/function_call_graph.py --repo-hash d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9 --entry-only --output-file /home/webadmin/projects/code/calls.dot -Tpng /home/webadmin/projects/code/calls.dot -o calls.png