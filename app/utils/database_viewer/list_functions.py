#!/usr/bin/env python3
"""
Function Lister - Utility to list all functions in a repository

Usage:
  python list_functions.py --repo-hash REPO_HASH
  
Options:
  --repo-hash     Repository hash to query
  --db-uri        Database URI (default: postgresql://codeuser:<code_password>@localhost:5432/code)
  --sort-by       Sort by name, file, or module (default: name)
  --filter        Filter functions by name (case-insensitive substring match)
  --entry-only    Show only entry point functions
  --verbose       Show detailed output
"""

import argparse
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pathlib import Path

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

def list_repository_functions(session, repo_hash, sort_by='name', filter_text=None, entry_only=False, verbose=False):
    """List all functions for a repository"""
    try:
        # First check if the repository exists
        repo_query = text("SELECT * FROM repositories WHERE id = :repo_hash")
        repo = session.execute(repo_query, {"repo_hash": repo_hash}).fetchone()
        
        if not repo:
            print(f"Repository with hash {repo_hash} not found in the database")
            return
        
        # Build query for functions
        query_params = {"repo_hash": repo_hash}
        
        # Base query
        query = """
            SELECT id, name, full_name, file_path, lineno, end_lineno, 
                   is_entry, class_name, module_name 
            FROM functions 
            WHERE repo_id = :repo_hash
        """
        
        # Add filters
        if entry_only:
            query += " AND is_entry = TRUE"
        
        if filter_text:
            query += " AND (name ILIKE :filter OR full_name ILIKE :filter)"
            query_params["filter"] = f"%{filter_text}%"
        
        # Add sorting
        if sort_by == 'file':
            query += " ORDER BY file_path, lineno"
        elif sort_by == 'module':
            query += " ORDER BY module_name, name"
        else:  # Default to name
            query += " ORDER BY name"
        
        # Execute the query
        functions = session.execute(text(query), query_params).fetchall()
        
        if not functions:
            print(f"No functions found for repository {repo_hash}" +
                  (" with the specified filter" if filter_text else ""))
            return
        
        # Print repository info
        print(f"\nRepository: {repo[1]}")  # repo.url is at index 1
        print(f"Hash: {repo_hash}")
        print(f"Found {len(functions)} functions")
        print("-" * 100)
        
        # Print table header
        if verbose:
            print(f"{'ID':<40} {'Name':<25} {'Module':<25} {'File':<30} {'Lines':<10} {'Class':<15} {'Entry'}")
            print("-" * 150)
        else:
            print(f"{'Name':<30} {'Module':<30} {'File':<40} {'Lines':<10} {'Entry'}")
            print("-" * 120)
        
        for func in functions:
            # Unpack the function tuple
            func_id, name, full_name, file_path, lineno, end_lineno, is_entry, class_name, module_name = func
            
            # Get just the filename from the path
            filename = Path(file_path).name if file_path else "N/A"
            
            # Format the output
            if verbose:
                # Just show the last part of the ID for cleaner display
                short_id = func_id.split(":")[-1] if ":" in func_id else func_id
                print(f"{short_id:<40} {name:<25} {module_name:<25} {filename:<30} "
                      f"{f'{lineno}-{end_lineno}':<10} {(class_name or 'N/A'):<15} "
                      f"{'✓' if is_entry else ''}")
            else:
                print(f"{name:<30} {module_name:<30} {filename:<40} "
                      f"{f'{lineno}-{end_lineno}':<10} {'✓' if is_entry else ''}")
    
    except Exception as e:
        print(f"Error listing functions: {e}")

def main():
    parser = argparse.ArgumentParser(description="List all functions in a repository")
    
    # Required arguments
    parser.add_argument("--repo-hash", required=True, help="Repository hash")
    
    # Optional arguments
    parser.add_argument("--db-uri", 
                        default="postgresql://codeuser:<code_password>@localhost:5432/code", 
                        help="Database URI (default: %(default)s)")
    parser.add_argument("--sort-by", choices=['name', 'file', 'module'], default='name',
                        help="Sort by name, file, or module (default: %(default)s)")
    parser.add_argument("--filter", help="Filter functions by name (case-insensitive)")
    parser.add_argument("--entry-only", action="store_true", 
                        help="Show only entry point functions")
    parser.add_argument("--verbose", action="store_true", 
                        help="Show detailed output including function IDs")
    
    args = parser.parse_args()
    
    # Connect to the database
    session, engine = connect_to_db(args.db_uri)
    
    # List repository functions
    list_repository_functions(
        session, 
        args.repo_hash, 
        args.sort_by, 
        args.filter, 
        args.entry_only, 
        args.verbose
    )
    
    session.close()

if __name__ == "__main__":
    main()