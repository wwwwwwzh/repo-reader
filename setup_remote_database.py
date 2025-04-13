#!/usr/bin/env python3
import argparse
from sqlalchemy import create_engine, MetaData, text
def setup_remote_database(host, port, user, password, dbname):
    """
    Set up the required database tables on the remote server
    """
    # Construct SQLAlchemy URI
    db_uri = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    
    # Connect to the database
    engine = create_engine(db_uri)
    metadata = MetaData()
    
    # Create SQL statements for tables
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
            module_name VARCHAR(256)
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
        """,
        """
        -- For backwards compatibility, keep the ast_nodes table
        CREATE TABLE IF NOT EXISTS ast_nodes (
            id VARCHAR(128) PRIMARY KEY,
            repo_id VARCHAR(64) REFERENCES repositories(id),
            parent_id VARCHAR(128) REFERENCES ast_nodes(id),
            name VARCHAR(128),
            full_name VARCHAR(512),
            code_preview TEXT,
            has_children BOOLEAN,
            level INTEGER
        )
        """
    ]
    
    # Execute the SQL
    with engine.begin() as connection:
        for sql in sql_statements:
            connection.execute(text(sql))

    
    # Create indexes for performance
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_functions_repo_id ON functions(repo_id)",
        "CREATE INDEX IF NOT EXISTS idx_segments_function_id ON segments(function_id)",
        "CREATE INDEX IF NOT EXISTS idx_segments_target_id ON segments(target_id)",
        "CREATE INDEX IF NOT EXISTS idx_function_calls_caller ON function_calls(caller_id)",
        "CREATE INDEX IF NOT EXISTS idx_function_calls_callee ON function_calls(callee_id)"
    ]
    
    with engine.begin() as connection:
        for sql in index_statements:
            connection.execute(text(sql))
    
    print(f"Database tables created successfully on {host}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up remote database tables")
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", default="5432", help="Database port")
    parser.add_argument("--user", default="codeuser", help="Database user")
    parser.add_argument("--password", default="<code_password>", help="Database password")
    parser.add_argument("--dbname", default="code", help="Database name")
    
    args = parser.parse_args()
    
    setup_remote_database(args.host, args.port, args.user, args.password, args.dbname)