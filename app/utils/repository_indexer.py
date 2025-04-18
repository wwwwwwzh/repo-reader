#!/usr/bin/env python3
"""
Repository Indexer - Build a RAG store for code repositories

This module builds a vector database index for a code repository,
storing functions with their descriptions and code for semantic search.
"""

import os
import sys
from typing import Dict, List, Optional
import logging
from pathlib import Path
from dotenv import load_dotenv
import hashlib

# LangChain imports
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

# Local imports
from app.models import *
from app.utils.logging_utils import logger
from app import db

# Load environment variables
load_dotenv()

# Configure embeddings model
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not found in environment variables. Vector embeddings will fail.")

# Configure database directory
RAG_DB_DIR = os.environ.get("RAG_DB_DIR", "/home/webadmin/projects/code/rag_db")

def create_function_documents(repo_hash: str, session) -> List[Document]:
    """
    Create LangChain Document objects from repository functions
    
    Args:
        repo_hash: Repository hash
        session: Database session
        
    Returns:
        List of Document objects
    """
    # Query all functions in the repository
    functions = session.query(Function).filter_by(repo_id=repo_hash).all()
    logger.info(f"Creating documents for {len(functions)} functions from repo {repo_hash}")
    
    documents = []
    for func in functions:
        # Add null checks for all fields
        name = func.name or ""
        full_name = func.full_name or ""
        file_path = func.file_path or ""
        module_name = func.module_name or ""
        class_name = func.class_name or ""
        short_description = func.short_description or ""
        input_output_description = func.input_output_description or ""
        long_description = func.long_description or ""
        lineno = func.lineno or 0
        end_lineno = func.end_lineno or 0
        is_entry = func.is_entry or False
        
        # Prepare metadata - move short_description to metadata
        metadata = {
            "repo_hash": repo_hash,
            "function_id": func.id,
            "name": name,
            "full_name": full_name,
            "file_path": file_path,
            "module_name": module_name,
            "class_name": class_name,
            "is_entry": is_entry,
            "lineno": lineno,
            "end_lineno": end_lineno,
            "short_description": short_description  # Moved to metadata
        }

        # Query segments directly from the database instead of using the relationship
        segments = session.query(Segment).filter_by(function_id=func.id).order_by(Segment.index).all()
        
        # Create content that includes description and code
        code_content = "\n".join(segment.content for segment in segments) if segments else ""
        # logger.info(code_content[:100])
        
        # Combine description and code
        content = f"Function: {full_name}\n"
        # Don't include short_description in content since it's in metadata
        if input_output_description:
            content += f"Input/Output: {input_output_description}\n"
        if long_description:
            content += f"Long Description: {long_description}\n"
        content += f"\nCode:\n{code_content}"
        
        # Create Document object
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)
    
    return documents

def build_repository_index(repo_hash: str, session=None, chunk_size: int = 2000, 
                          chunk_overlap: int = 200) -> bool:
    """
    Build a vector store index for a repository
    
    Args:
        repo_hash: Repository hash
        session: Database session (optional)
        chunk_size: Maximum size of text chunks
        chunk_overlap: Overlap between chunks
        
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Building index for repository {repo_hash}")
    
    try:
        # Create vector store directory
        repo_db_dir = os.path.join(RAG_DB_DIR, repo_hash)
        if os.path.exists(repo_db_dir):
            logger.warning(f"Deleting existing vector store at {repo_db_dir}")
            import shutil
            shutil.rmtree(repo_db_dir)
        os.makedirs(repo_db_dir, exist_ok=True)
        
        # Create session if not provided
        if session is None:
            from sqlalchemy.orm import Session
            session = Session(db.engine)
        
        # Check if repository exists
        repo = session.query(Repository).filter_by(id=repo_hash).first()
        if not repo:
            logger.error(f"Repository {repo_hash} not found in database")
            return False
        
        # Create documents from functions
        documents = create_function_documents(repo_hash, session)
        if not documents:
            logger.warning(f"No functions found for repository {repo_hash}")
            return False
        
        logger.info(f"Created {len(documents)} documents for repository {repo_hash}")
        
        # Create text splitter for chunking
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Split documents into chunks
        split_docs = text_splitter.split_documents(documents)
        logger.info(f"Split into {len(split_docs)} chunks")
        
        # Initialize embedding model
        embeddings = OpenAIEmbeddings(
            openai_api_key=OPENAI_API_KEY,
            model="text-embedding-3-small"
        )
        

        
        # Build vector store
        logger.info(f"Building vector store in {repo_db_dir}")
        collection_name = f"repo_{repo_hash[:58]}"  # Use consistent collection name based on repo hash

        vectorstore = Chroma.from_documents(
            documents=split_docs,
            embedding=embeddings,
            persist_directory=repo_db_dir,
            collection_name=collection_name
        )
        
        # Persist to disk
        vectorstore.persist()
        logger.info(f"Successfully built index for repository {repo_hash}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error building repository index: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def load_repository_index(repo_hash: str) -> Optional[Chroma]:
    """
    Load a repository's vector store index
    
    Args:
        repo_hash: Repository hash
        
    Returns:
        Chroma vector store or None if not found
    """
    repo_db_dir = os.path.join(RAG_DB_DIR, repo_hash)
    if not os.path.exists(repo_db_dir):
        logger.warning(f"Vector store not found for repository {repo_hash}")
        return None
    
    try:
        # Initialize embedding model
        embeddings = OpenAIEmbeddings(
            openai_api_key=OPENAI_API_KEY,
            model="text-embedding-3-small"
        )
        
        # Load vector store from disk
        logger.info(f"Loading vector store from {repo_db_dir}")
        collection_name = f"repo_{repo_hash[:58]}"  # Use the same collection name pattern
        vectorstore = Chroma(
            persist_directory=repo_db_dir,
            embedding_function=embeddings,
            collection_name=collection_name  
        )        
        return vectorstore
        
    except Exception as e:
        logger.error(f"Error loading repository index: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None



def index_repository_after_build(repo_hash: str, repo_url: str, entry_points: List[str]) -> bool:
    """
    Function to be called at the end of remote_tree_builder to index the repository
    
    Args:
        repo_hash: Repository hash
        repo_url: Repository URL
        entry_points: List of entry point file paths
        
    Returns:
        True if successful, False otherwise
    """
    from app import create_app
    app = create_app()
    
    with app.app_context():
        from sqlalchemy.orm import Session
        session = Session(db.engine)
        
        try:
            success = build_repository_index(repo_hash, session)
            if success:
                logger.info(f"Successfully indexed repository {repo_hash}")
            else:
                logger.error(f"Failed to index repository {repo_hash}")
            
            return success
            
        finally:
            session.close()
if __name__ == "__main__":
    # CLI for testing and manual indexing
    import argparse
    
    parser = argparse.ArgumentParser(description="Build a RAG store for a code repository")
    parser.add_argument("repo_hash", help="Repository hash to index")
    parser.add_argument("--chunk-size", type=int, default=2000, help="Maximum chunk size")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap")
    
    args = parser.parse_args()
    
    from sqlalchemy.orm import Session
    session = Session(db.engine)
    
    try:
        success = build_repository_index(
            args.repo_hash,
            session,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap
        )
        
        if success:
            print(f"Successfully indexed repository {args.repo_hash}")
            sys.exit(0)
        else:
            print(f"Failed to index repository {args.repo_hash}")
            sys.exit(1)
            
    finally:
        session.close()