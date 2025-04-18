#!/usr/bin/env python3
"""
Database setup script - Drops and recreates all tables for the code analysis application
"""
import os
import sys
import argparse
from sqlalchemy import create_engine, MetaData, text

def setup_database(db_uri, drop_existing=False):
    """
    Set up the database schema, optionally dropping existing tables first
    
    Args:
        db_uri: Database connection URI
        drop_existing: Whether to drop existing tables
    """
    print(f"Connecting to database: {db_uri}")
    engine = create_engine(db_uri)
    
    # Connect to the database
    with engine.connect() as connection:
        # Drop existing tables if requested
        if drop_existing:
            print("Dropping existing tables...")
            
            # Define tables to drop in reverse dependency order
            tables = [
                "ast_nodes",
                "func_components",
                "segments",
                "function_calls",
                "functions",
                "repositories"
            ]
            
            for table in tables:
                try:
                    connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    print(f"  Dropped table: {table}")
                except Exception as e:
                    print(f"  Error dropping table {table}: {e}")
        
        # Create the tables
        print("Creating tables...")
        
        # SQL statements for table creation
        sql_statements = [
            """
            CREATE TABLE IF NOT EXISTS repositories (
                id VARCHAR(64) PRIMARY KEY,
                url VARCHAR(512) UNIQUE,
                entry_points JSONB,
                parsed_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS functions (
                id VARCHAR(128) PRIMARY KEY,
                repo_id VARCHAR(64) REFERENCES repositories(id) ON DELETE CASCADE,
                name VARCHAR(128),
                full_name VARCHAR(512),
                file_path VARCHAR(512),
                lineno INTEGER,
                end_lineno INTEGER,
                is_entry BOOLEAN DEFAULT FALSE,
                class_name VARCHAR(128),
                module_name VARCHAR(256),
                short_description TEXT,
                input_output_description TEXT,
                long_description TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS func_components (
                id VARCHAR(256) PRIMARY KEY,
                function_id VARCHAR(128) REFERENCES functions(id) ON DELETE CASCADE,
                name VARCHAR(128),
                short_description VARCHAR(255),
                long_description TEXT,
                start_lineno INTEGER,
                end_lineno INTEGER,
                index INTEGER
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS segments (
                id VARCHAR(256) PRIMARY KEY,
                function_id VARCHAR(128) REFERENCES functions(id) ON DELETE CASCADE,
                type VARCHAR(32),
                content TEXT,
                lineno INTEGER,
                end_lineno INTEGER,
                index INTEGER,
                target_id VARCHAR(128) REFERENCES functions(id) ON DELETE SET NULL,
                func_component_id VARCHAR(256) REFERENCES func_components(id) ON DELETE SET NULL,
                segment_data JSONB
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS function_calls (
                caller_id VARCHAR(128) REFERENCES functions(id) ON DELETE CASCADE,
                callee_id VARCHAR(128) REFERENCES functions(id) ON DELETE CASCADE,
                call_count INTEGER DEFAULT 1,
                call_data JSONB,
                PRIMARY KEY (caller_id, callee_id)
            )
            """
        ]
        
        # Execute the SQL statements
        for sql in sql_statements:
            try:
                connection.execute(text(sql))
            except Exception as e:
                print(f"Error executing SQL: {e}")
                print(f"Statement: {sql}")
                raise
        
        # Create indexes for better performance
        print("Creating indexes...")
        index_statements = [
            "CREATE INDEX IF NOT EXISTS idx_functions_repo_id ON functions(repo_id)",
            "CREATE INDEX IF NOT EXISTS idx_segments_function_id ON segments(function_id)",
            "CREATE INDEX IF NOT EXISTS idx_segments_target_id ON segments(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_segments_component_id ON segments(func_component_id)",
            "CREATE INDEX IF NOT EXISTS idx_components_function_id ON func_components(function_id)",
            "CREATE INDEX IF NOT EXISTS idx_function_calls_caller ON function_calls(caller_id)",
            "CREATE INDEX IF NOT EXISTS idx_function_calls_callee ON function_calls(callee_id)"
        ]
        
        for sql in index_statements:
            try:
                connection.execute(text(sql))
            except Exception as e:
                print(f"Error creating index: {e}")
                
        connection.commit()
    print("Database setup complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up database tables")
    parser.add_argument("--db-uri", 
                        default="postgresql://codeuser:<code_password>@localhost:5432/code", 
                        help="Database URI (default: %(default)s)")
    parser.add_argument("--drop", action="store_true", 
                        help="Drop existing tables before creating new ones")
    
    args = parser.parse_args()
    
    # Use DATABASE_URL environment variable if set
    db_uri = os.environ.get('DATABASE_URL', args.db_uri)
    
    setup_database(db_uri, args.drop)