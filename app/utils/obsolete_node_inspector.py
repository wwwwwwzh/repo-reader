#!/usr/bin/env python3
"""
Node Inspector - Utility to inspect AST node properties from a remote database

Usage:
  python node_inspector.py --repo-hash REPO_HASH --node-id NODE_ID
  python node_inspector.py --repo-hash REPO_HASH --list-nodes
  python node_inspector.py --repo-hash REPO_HASH --node-id NODE_ID --show-segments
  
Use --db-uri to specify a different database connection string if needed.
"""

import os
import sys
import json
import argparse
import re
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Boolean, Integer, ForeignKey, JSON, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# Define database models
Base = declarative_base()

class Repository(Base):
    __tablename__ = 'repositories'
    id = Column(String(64), primary_key=True)
    url = Column(String(512))
    entry_points = Column(JSON)
    parsed_at = Column(DateTime, default=datetime.utcnow)

class ASTNode(Base):
    __tablename__ = 'ast_nodes'
    id = Column(String(128), primary_key=True)
    repo_id = Column(String(64), ForeignKey('repositories.id'))
    parent_id = Column(String(128), ForeignKey('ast_nodes.id'))
    name = Column(String(128))
    full_name = Column(String(512))
    code_preview = Column(String)
    has_children = Column(Boolean)
    level = Column(Integer)

def connect_to_db(db_uri):
    """Connect to the database and return a session"""
    try:
        print(f"Connecting to database: {db_uri}")
        engine = create_engine(db_uri)
        Session = sessionmaker(bind=engine)
        session = Session()
        # Test connection with proper text() usage
        session.execute(text("SELECT 1"))
        print("Database connection successful!")
        return session, engine
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("Please check your database connection settings")
        sys.exit(1)

def get_node_from_db(session, repo_hash, node_id):
    """Retrieve a node from the database by repo_hash and node_id"""
    if not node_id.startswith(f"{repo_hash}:"):
        full_node_id = f"{repo_hash}:{node_id}"
    else:
        full_node_id = node_id
    
    try:
        # Try with the full ID first
        node = session.query(ASTNode).filter_by(id=full_node_id).first()
        
        # If not found, try with just the node_id
        if not node:
            node = session.query(ASTNode).filter_by(id=node_id).first()
            
        if not node:
            print(f"Node with ID {node_id} not found in the database")
            return None
        
        # Get repository information
        repo = session.query(Repository).filter_by(id=repo_hash).first()
        if not repo:
            print(f"Repository with hash {repo_hash} not found in the database")
        
        return node, repo
    except Exception as e:
        print(f"Error querying database: {e}")
        return None

def list_repository_nodes(session, repo_hash):
    """List all nodes for a repository"""
    try:
        # First check if the repository exists
        repo = session.query(Repository).filter_by(id=repo_hash).first()
        if not repo:
            print(f"Repository with hash {repo_hash} not found in the database")
            return
        
        # Get all nodes for this repository
        nodes = session.query(ASTNode).filter_by(repo_id=repo_hash).all()
        
        if not nodes:
            print(f"No nodes found for repository {repo_hash}")
            return
        
        print(f"\nRepository: {repo.url}")
        print(f"Hash: {repo_hash}")
        try:
            if isinstance(repo.entry_points, dict) or isinstance(repo.entry_points, list):
                entry_points = repo.entry_points
            else:
                entry_points = json.loads(repo.entry_points)
            print(f"Entry Points: {entry_points}")
        except:
            print(f"Entry Points: {repo.entry_points}")
        print(f"Parsed At: {repo.parsed_at}")
        print(f"Found {len(nodes)} nodes")
        print("-" * 100)
        
        # Sort nodes by level and name for better organization
        nodes.sort(key=lambda x: (x.level, x.name))
        
        # Print table header
        print(f"{'Node ID':<45} {'Name':<25} {'Level':<5} {'Parent ID':<45} {'Has Children'}")
        print("-" * 100)
        
        for node in nodes:
            # Strip the repo_hash prefix for cleaner display
            short_id = node.id.replace(f"{repo_hash}:", "") if node.id.startswith(f"{repo_hash}:") else node.id
            parent_id = (node.parent_id.replace(f"{repo_hash}:", "") 
                        if node.parent_id and node.parent_id.startswith(f"{repo_hash}:") 
                        else "None" if not node.parent_id else node.parent_id)
            
            print(f"{short_id:<45} {node.name:<25} {node.level:<5} {parent_id:<45} {node.has_children}")
    
    except Exception as e:
        print(f"Error listing nodes: {e}")

def extract_segments_from_preview(code_preview):
    """Extract and parse segments from code preview"""
    segments = []
    
    # Check for pattern: "# Code:", "# Comment:", "# Call:"
    segment_pattern = r"# (Code|Comment|Call):([\s\S]*?)(?=# (Code|Comment|Call):|$)"
    matches = re.findall(segment_pattern, code_preview)
    
    for match in matches:
        segment_type = match[0].lower()
        content = match[1].strip()
        if content:
            segments.append({
                'type': segment_type,
                'content': content
            })
    
    return segments

def display_segments(code_preview):
    """Display segments in a structured format"""
    segments = extract_segments_from_preview(code_preview)
    
    if not segments:
        print("No segments found in code preview")
        return
    
    print("\n" + "=" * 50)
    print("SEGMENTS")
    print("=" * 50)
    
    for i, segment in enumerate(segments):
        print(f"Segment {i+1}: [{segment['type']}]")
        print("-" * 50)
        content_lines = segment['content'].split('\n')
        for j, line in enumerate(content_lines):
            print(f"{j+1:3d} | {line}")
        print()

def display_node_details(session, node, repo=None, include_raw=False, show_segments=False):
    """Display all properties of a node in a detailed format"""
    if not node:
        return
    
    try:
        # Convert node to a dictionary
        node_dict = {
            'id': node.id,
            'repo_id': node.repo_id,
            'parent_id': node.parent_id,
            'name': node.name,
            'full_name': node.full_name,
            'has_children': node.has_children,
            'level': node.level
        }
        
        # Display the node details in a formatted way
        print("\n" + "=" * 50)
        print("NODE DETAILS")
        print("=" * 50)
        
        # Display repository information if available
        if repo:
            print(f"Repository URL: {repo.url}")
            print(f"Repository Hash: {repo.id}")
            try:
                if isinstance(repo.entry_points, dict) or isinstance(repo.entry_points, list):
                    entry_points = repo.entry_points
                else:
                    entry_points = json.loads(repo.entry_points)
                print(f"Entry Points: {entry_points}")
            except:
                print(f"Entry Points: {repo.entry_points}")
            print(f"Parsed At: {repo.parsed_at}")
            print("-" * 50)
        
        # Display node properties
        print(f"Node ID: {node.id}")
        print(f"Parent ID: {node.parent_id or 'None'}")
        print(f"Name: {node.name}")
        print(f"Full Name: {node.full_name}")
        print(f"Has Children: {node.has_children}")
        print(f"Level: {node.level}")
        
        # Display segments if requested
        if show_segments and node.code_preview:
            display_segments(node.code_preview)
        else:
            # Otherwise display the normal code preview
            print("-" * 50)
            print("Code Preview:")
            if node.code_preview:
                code_lines = node.code_preview.split('\n')
                for i, line in enumerate(code_lines):
                    print(f"{i+1:3d} | {line}")
            else:
                print("No code preview available")
        
        # Display the raw node object if requested
        if include_raw:
            print("-" * 50)
            print("Raw Node Data:")
            print(json.dumps(node_dict, indent=2))
        
        print("=" * 50)
        
        # Get and display child nodes if they exist
        try:
            child_nodes = session.query(ASTNode).filter_by(parent_id=node.id).all()
            if child_nodes:
                print("\nCHILD NODES:")
                for i, child in enumerate(child_nodes):
                    print(f"{i+1}. {child.name} ({child.id})")
        except Exception as e:
            print(f"Error getting child nodes: {e}")
            
    except Exception as e:
        print(f"Error displaying node details: {e}")

def main():
    parser = argparse.ArgumentParser(description="Inspect AST node properties from remote database")
    
    # Repository hash is required
    parser.add_argument("--repo-hash", required=True, help="Repository hash")
    
    # Node ID and list-nodes options
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--node-id", help="Node ID to inspect")
    group.add_argument("--list-nodes", action="store_true", help="List all nodes in the repository")
    
    # Database connection settings
    parser.add_argument("--db-uri", 
                       default="postgresql://codeuser:<code_password>@159.223.132.83:5432/code", 
                       help="Database URI (default: %(default)s)")
    parser.add_argument("--raw", action="store_true", help="Include raw node data in the output")
    parser.add_argument("--show-segments", action="store_true", 
                       help="Display segments in a structured format")
    
    args = parser.parse_args()
    
    # Connect to the database
    session, engine = connect_to_db(args.db_uri)
    
    # Process the request
    if args.list_nodes:
        list_repository_nodes(session, args.repo_hash)
    else:
        node_result = get_node_from_db(session, args.repo_hash, args.node_id)
        if node_result:
            node, repo = node_result
            display_node_details(session, node, repo, args.raw, args.show_segments)

if __name__ == "__main__":
    main()

"""
python /nas/longleaf/home/zhw/personal/code_mapper/new/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --list-nodes
python /nas/longleaf/home/zhw/personal/code_mapper/new/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --node-id "140462637984400_segment_10" --show-segments

python /home/webadmin/projects/code/app/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --list-nodes
python /home/webadmin/projects/code/app/utils/node_inspector.py --repo-hash "d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9" --node-id "140462637984400_segment_17" --show-segments

"""