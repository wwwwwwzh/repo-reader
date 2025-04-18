#!/usr/bin/env python3
"""
Visual Function Segment Tree - Creates a visual hierarchical view of function segments

This script generates a visual tree representation starting from a root function,
showing all its segments and recursively including called functions.

Usage:
  python visual_segment_tree.py --repo-hash REPO_HASH --function-id FUNCTION_ID [options]
  python visual_segment_tree.py --repo-hash REPO_HASH --function-name FUNCTION_NAME [options]
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

def get_segments_for_function(session, function_id):
    """Get all segments for a function"""
    try:
        query = """
            SELECT id, type, content, lineno, end_lineno, index, target_id, segment_data
            FROM segments
            WHERE function_id = :function_id
            ORDER BY index
        """
        
        segments = session.execute(text(query), {"function_id": function_id}).fetchall()
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

def collect_tree_data(session, function_id, max_depth=3, current_depth=0, visited_functions=None):
    """Collect data for generating a hierarchical tree visualization"""
    if visited_functions is None:
        visited_functions = set()
    
    # Prevent infinite recursion from circular references
    if function_id in visited_functions:
        return {
            "name": "CIRCULAR_REF",
            "type": "function",
            "id": function_id
        }
    
    # Mark this function as visited
    visited_functions.add(function_id)
    
    # Get function info
    function = get_function_by_id(session, function_id)
    if not function:
        return {
            "name": "UNKNOWN_FUNCTION",
            "type": "function",
            "id": function_id
        }
    
    # Start building the tree node for this function
    func_node = {
        "name": function[1],  # function.name
        "full_name": function[2],  # function.full_name
        "type": "function",
        "id": function_id,
        "children": []
    }
    
    # If we've reached max depth, don't add segments
    if current_depth >= max_depth:
        func_node["truncated"] = True
        return func_node
    
    # Get segments for this function
    segments = get_segments_for_function(session, function_id)
    
    # Add each segment to the tree
    for segment in segments:
        segment_id, seg_type, content, lineno, end_lineno, index, target_id, segment_data = segment
        
        # Create content preview
        content_preview = content
        if content and len(content) > 50:
            content_preview = content[:47] + "..."
        
        # Basic segment info
        segment_node = {
            "name": f"{seg_type.upper()}: {content_preview}",
            "type": f"segment_{seg_type}",
            "id": segment_id,
            "segment_type": seg_type,
            "lineno": lineno,
            "children": []
        }
        
        # For call segments, add the target function if it exists
        if seg_type == 'call' and target_id:
            # Get target function info
            target_func = get_function_by_id(session, target_id)
            if target_func:
                # Add target function as child
                target_name = target_func[1]  # target_func.name
                
                # Show more info in the name
                segment_node["name"] = f"CALL: {target_name}()"
                
                # Recursively add the target function and its segments
                if current_depth < max_depth - 1:  # Limit recursion
                    target_node = collect_tree_data(
                        session, target_id, max_depth, current_depth + 1, 
                        visited_functions.copy()
                    )
                    if target_node:
                        segment_node["children"].append(target_node)
        
        # Add segment to function node
        func_node["children"].append(segment_node)
    
    return func_node

def generate_dot_graph(tree_data, output_file):
    """Generate a DOT graph from the tree data"""
    try:
        with open(output_file, 'w') as f:
            f.write("digraph SegmentTree {\n")
            f.write("  node [shape=box, style=filled, fontname=\"Arial\"];\n")
            f.write("  edge [fontname=\"Arial\"];\n")
            f.write("\n")
            
            # Generate unique IDs for each node
            node_ids = {}
            next_id = 1
            
            # First pass: assign IDs and create nodes
            nodes_to_process = [tree_data]
            while nodes_to_process:
                node = nodes_to_process.pop(0)
                
                # Assign ID if not already assigned
                if node.get("id") not in node_ids:
                    node_ids[node.get("id")] = f"node_{next_id}"
                    next_id += 1
                
                node_id = node_ids[node.get("id")]
                
                # Set node color based on type
                if node.get("type") == "function":
                    fillcolor = "lightblue"
                elif node.get("type") == "segment_call":
                    fillcolor = "lightgreen"
                elif node.get("type") == "segment_code":
                    fillcolor = "lightyellow"
                elif node.get("type") == "segment_comment":
                    fillcolor = "lightgrey"
                else:
                    fillcolor = "white"
                
                # Truncate long names
                label = node.get("name", "")
                if len(label) > 30:
                    label = label[:27] + "..."
                
                # Add node
                f.write(f'  {node_id} [label="{label}", fillcolor="{fillcolor}"];\n')
                
                # Queue up children for processing
                if "children" in node:
                    for child in node["children"]:
                        nodes_to_process.append(child)
            
            f.write("\n")
            
            # Second pass: create edges
            nodes_to_process = [tree_data]
            while nodes_to_process:
                node = nodes_to_process.pop(0)
                
                node_id = node_ids[node.get("id")]
                
                # Add edges to children
                if "children" in node:
                    for child in node["children"]:
                        if child.get("id") in node_ids:
                            child_id = node_ids[child.get("id")]
                            f.write(f"  {node_id} -> {child_id};\n")
                        
                        # Queue up children for processing
                        nodes_to_process.append(child)
            
            f.write("}\n")
        
        print(f"DOT graph generated: {output_file}")
        print(f"To generate an image, run: dot -Tpng {output_file} -o tree.png")
        
        return True
    
    except Exception as e:
        print(f"Error generating DOT graph: {e}")
        return False

def generate_html_tree(tree_data, output_file):
    """Generate an HTML file with a collapsible tree visualization"""
    try:
        with open(output_file, 'w') as f:
            # Write HTML header
            f.write("""<!DOCTYPE html>
                <html>
                <head>
                    <title>Function Segment Tree</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            margin: 20px;
                        }
                        .tree ul {
                            padding-left: 20px;
                        }
                        .tree li {
                            list-style-type: none;
                            margin: 10px 0;
                            position: relative;
                        }
                        .tree li::before {
                            content: "";
                            position: absolute;
                            top: -5px;
                            left: -15px;
                            border-left: 1px solid #ccc;
                            border-bottom: 1px solid #ccc;
                            width: 10px;
                            height: 15px;
                        }
                        .tree ul > li:first-child::before {
                            top: 10px;
                            height: 0;
                        }
                        .tree ul > li:only-child::before {
                            display: none;
                        }
                        .tree li::after {
                            position: absolute;
                            content: "";
                            top: 10px;
                            left: -15px;
                            border-left: 1px solid #ccc;
                            height: 100%;
                        }
                        .tree li:last-child::after {
                            display: none;
                        }
                        .tree .caret {
                            cursor: pointer;
                            user-select: none;
                        }
                        .tree .caret::before {
                            content: "▶ ";
                            color: black;
                            display: inline-block;
                            margin-right: 6px;
                        }
                        .tree .caret-down::before {
                            content: "▼ ";
                        }
                        .tree .nested {
                            display: none;
                        }
                        .tree .active {
                            display: block;
                        }
                        .function {
                            background-color: #e3f2fd;
                            padding: 5px;
                            border-radius: 4px;
                            border: 1px solid #90caf9;
                        }
                        .segment_code {
                            background-color: #fffde7;
                            padding: 5px;
                            border-radius: 4px;
                            border: 1px solid #fff59d;
                        }
                        .segment_call {
                            background-color: #e8f5e9;
                            padding: 5px;
                            border-radius: 4px;
                            border: 1px solid #a5d6a7;
                        }
                        .segment_comment {
                            background-color: #f5f5f5;
                            padding: 5px;
                            border-radius: 4px;
                            border: 1px solid #e0e0e0;
                        }
                    </style>
                </head>
                <body>
                    <h1>Function Segment Tree</h1>
                    <div class="tree">
                """)
            
            # Generate tree HTML
            def generate_tree_html(node, indent=8):
                indent_str = " " * indent
                html = ""
                
                # Start list item
                html += f"{indent_str}<li>\n"
                
                # Get node class based on type
                node_class = node.get("type", "")
                
                # If node has children, make it collapsible
                if "children" in node and node["children"]:
                    html += f"{indent_str}  <span class=\"caret {node_class}\">{node.get('name', '')}</span>\n"
                    html += f"{indent_str}  <ul class=\"nested\">\n"
                    
                    # Add children
                    for child in node["children"]:
                        html += generate_tree_html(child, indent + 4)
                    
                    html += f"{indent_str}  </ul>\n"
                else:
                    html += f"{indent_str}  <span class=\"{node_class}\">{node.get('name', '')}</span>\n"
                
                # End list item
                html += f"{indent_str}</li>\n"
                
                return html
            
            # Write tree structure
            f.write("        <ul>\n")
            f.write(generate_tree_html(tree_data))
            f.write("        </ul>\n")
            
            # Write JavaScript for collapsible functionality
            f.write("""    </div>

                    <script>
                        document.addEventListener('DOMContentLoaded', function() {
                            // Add click event to all carets
                            var carets = document.getElementsByClassName("caret");
                            for (var i = 0; i < carets.length; i++) {
                                carets[i].addEventListener("click", function() {
                                    this.classList.toggle("caret-down");
                                    var nested = this.nextElementSibling;
                                    if (nested) {
                                        nested.classList.toggle("active");
                                    }
                                });
                            }
                            
                            // Expand the first level by default
                            var rootCaret = document.querySelector(".caret");
                            if (rootCaret) {
                                rootCaret.classList.add("caret-down");
                                var rootNested = rootCaret.nextElementSibling;
                                if (rootNested) {
                                    rootNested.classList.add("active");
                                }
                            }
                        });
                    </script>
                </body>
                </html>""")
    except Exception as e:
        print(f"Error: {e}")
        
        
        