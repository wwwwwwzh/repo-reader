#!/usr/bin/env python3
"""
Repository Question Answering - Answer questions about code repositories

This module uses RAG (Retrieval Augmented Generation) to answer questions
about a code repository by retrieving relevant functions and using
Groq to analyze and generate responses.
"""

import os
import json
import requests
import time
from typing import Dict, List, Any, Tuple, Optional
from dotenv import load_dotenv
import logging

# LangChain imports
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
# Local imports
from app.utils.logging_utils import logger
from app.models import Repository, Function, Segment
from app import db
from app.utils.repository_indexer import load_repository_index

# Load environment variables
load_dotenv()

# Configure API keys
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Constants
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def format_function_for_context(function: Function, include_segments: bool = True) -> str:
    """
    Format a function for inclusion in the context

    Args:
        function: Function object
        include_segments: Whether to include function segments/code

    Returns:
        Formatted function text
    """
    # Start with basic function info
    result = f"Function: {function.full_name}\n"
    result += f"File: {function.file_path} (Lines {function.lineno}-{function.end_lineno})\n"
    
    # Add descriptions if available
    if function.short_description:
        result += f"Description: {function.short_description}\n"
    if function.input_output_description:
        result += f"Input/Output: {function.input_output_description}\n"
    if function.long_description:
        result += f"Details: {function.long_description}\n"
    
    # Add function code if requested
    if include_segments and function.segments:
        # Sort segments by index
        segments = sorted(function.segments, key=lambda s: s.index)
        code = "\n".join(segment.content for segment in segments)
        result += f"\nCode:\n```python\n{code}\n```\n"
    
    return result


async def search_repository_functions(repo_hash: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Search for functions in a repository that are relevant to a query

    Args:
        repo_hash: Repository hash
        query: Search query
        k: Number of results to return

    Returns:
        List of function data dictionaries
    """
    # Load the vector store
    vectorstore = load_repository_index(repo_hash)
    if not vectorstore:
        logger.error(f"Failed to load vector store for repository {repo_hash}")
        return []
    
    try:
        # Perform similarity search
        results = vectorstore.similarity_search_with_relevance_scores(query, k=k)
        
        # Extract function IDs from metadata
        function_data = []
        for doc, score in results:
            if score < 0.6:  # Skip results with low relevance scores
                continue
                
            metadata = doc.metadata
            function_data.append({
                "id": metadata["function_id"],
                "full_name": metadata["full_name"],
                "file_path": metadata["file_path"],
                "relevance_score": score
            })
        
        return function_data
        
    except Exception as e:
        logger.error(f"Error searching repository functions: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def search_repository_functions_sync(repo_hash: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Synchronous version of search_repository_functions

    Args:
        repo_hash: Repository hash
        query: Search query
        k: Number of results to return

    Returns:
        List of function data dictionaries
    """
    # Load the vector store
    vectorstore = load_repository_index(repo_hash)
    if not vectorstore:
        logger.error(f"Failed to load vector store for repository {repo_hash}")
        return []
    
    try:
        # Perform similarity search
        results = vectorstore.similarity_search_with_relevance_scores(query, k=k)
        
        # Extract function IDs from metadata
        function_data = []
        
        for doc, score in results:
            # logger.info(f"{score=}, {doc.metadata["full_name"]=}")
            if score < 0.01:  # Skip results with low relevance scores
                continue
                
            metadata = doc.metadata
            function_data.append({
                "id": metadata["function_id"],
                "full_name": metadata["full_name"],
                "file_path": metadata["file_path"],
                "relevance_score": score
            })
        
        return function_data
        
    except Exception as e:
        logger.error(f"Error searching repository functions: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def get_function_details(function_id: str, session=None) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a function

    Args:
        function_id: Function ID
        session: Database session (optional)

    Returns:
        Function details dictionary or None if not found
    """
    # Create session if not provided
    close_session = False
    if session is None:
        from sqlalchemy.orm import Session
        session = Session(db.engine)
        close_session = True
    
    try:
        # Query function
        function = session.query(Function).filter_by(id=function_id).first()
        if not function:
            return None
        
        # Get segments directly from database instead of using relationship
        segments = session.query(Segment).filter_by(function_id=function_id).order_by(Segment.index).all()
        
        # Build function code
        code = "\n".join(segment.content for segment in segments) if segments else ""
        
        # Build function details
        details = {
            "id": function.id,
            "name": function.name,
            "full_name": function.full_name,
            "file_path": function.file_path,
            "module_name": function.module_name,
            "class_name": function.class_name,
            "lineno": function.lineno,
            "end_lineno": function.end_lineno,
            "short_description": function.short_description,
            "input_output_description": function.input_output_description,
            "long_description": function.long_description,
            "code": code
        }
        
        return details
        
    finally:
        if close_session:
            session.close()
def build_context_for_groq(query: str, functions: List[Dict[str, Any]]) -> str:
    """
    Build the context for Groq from a list of functions

    Args:
        query: User query
        functions: List of function details

    Returns:
        Context string
    """
    context = f"# Code Repository Context\n\n"
    
    # Add functions to context
    for i, func in enumerate(functions):
        # Add function with index marker
        context += f"## Function {i+1}: {func['full_name']}\n"
        context += f"File: {func['file_path']}\n"
        
        # Add descriptions if available
        if func.get('short_description'):
            context += f"Description: {func['short_description']}\n"
        if func.get('input_output_description'):
            context += f"Input/Output: {func['input_output_description']}\n"
        if func.get('long_description'):
            context += f"Details: {func['long_description']}\n"
        
        # Add code with index marker
        context += f"\nCode:\n```python\n{func['code']}\n```\n\n"
    
    return context


def query_groq(query: str, context: str, model: str = DEFAULT_GROQ_MODEL, 
               temperature: float = 0.2, max_tokens: int = 1000) -> str:
    """
    Query Groq with the user's question and repository context

    Args:
        query: User query
        context: Repository context
        model: Groq model to use
        temperature: Generation temperature
        max_tokens: Maximum tokens to generate

    Returns:
        Generated response
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not found in environment variables")
        return "Error: API key not configured properly. Please contact the administrator."
    
    try:
        # Build the prompt
        system_prompt = """
You are a code repository expert assistant. You analyze and explain code structures to help users understand code repositories.
Your task is to analyze the provided code functions and answer the user's question.

When you reference specific functions or code in your answer, you should:
1. Cite the function number (e.g., Function 1, Function 2)
2. Be specific about where in the code you're referencing
3. Explain how the code works and why it's relevant to the question

Keep your answers clear, concise, and technically accurate. Explain complex concepts in an accessible way.
Do not hallucinate or make up information about code that isn't provided in the context.
"""

        user_prompt = f"""
I'll analyze the following code repository to answer your question.

{context}

Your question: {query}
"""

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Make the API request
        response = requests.post(GROQ_API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        # Parse response
        response_data = response.json()
        return response_data["choices"][0]["message"]["content"]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error querying Groq API: {str(e)}")
        return f"Error: Failed to query Groq API. {str(e)}"
    except Exception as e:
        logger.error(f"Error in query_groq: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Error processing your request: {str(e)}"


def answer_repository_question(repo_hash: str, query: str, k: int = 5) -> Dict[str, Any]:
    """
    Answer a question about a repository using RAG and Groq
    
    Args:
        repo_hash: Repository hash
        query: User query
        k: Number of relevant functions to retrieve
        
    Returns:
        Dictionary with answer and metadata
    """
    # Create application context
    from app import create_app
    app = create_app()
    
    with app.app_context():
        try:
            # 1. Search for relevant functions
            logger.info(f"Searching for functions relevant to: {query}")
            function_data = search_repository_functions_sync(repo_hash, query, k=k)
            
            if not function_data:
                return {
                    "answer": "I couldn't find any relevant functions to answer your question. Please try rephrasing or ask a different question.",
                    "functions": [],
                    "error": None
                }
            
            # 2. Get full function details from database
            from sqlalchemy.orm import Session
            session = Session(db.engine)
            
            try:
                functions_with_details = []
                for func in function_data:
                    details = get_function_details(func["id"], session)
                    if details:
                        # Add relevance score
                        details["relevance_score"] = func["relevance_score"]
                        functions_with_details.append(details)
                
                # Sort by relevance score (highest first)
                functions_with_details.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            finally:
                session.close()
            
            # 3. Build context for Groq
            context = build_context_for_groq(query, functions_with_details)
            
            # 4. Query Groq for answer
            logger.info(f"Querying Groq with context size: {len(context)} characters")
            answer = query_groq(query, context)
            
            # 5. Return result
            return {
                "answer": answer,
                "functions": [{
                    "id": f["id"],
                    "name": f["name"],
                    "full_name": f["full_name"],
                    "file_path": f["file_path"],
                    "relevance_score": f.get("relevance_score", 0)
                } for f in functions_with_details],
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error answering repository question: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "answer": f"Error processing your request: {str(e)}",
                "functions": [],
                "error": str(e)
            }
if __name__ == "__main__":
    # CLI for testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Answer questions about a code repository")
    parser.add_argument("repo_hash", help="Repository hash")
    parser.add_argument("query", help="Question about the repository")
    parser.add_argument("--k", type=int, default=5, help="Number of functions to retrieve")
    
    args = parser.parse_args()
    
    result = answer_repository_question(args.repo_hash, args.query, k=args.k)
    
    print("ANSWER:")
    print(result["answer"])
    
    print("\nRELEVANT FUNCTIONS:")
    for func in result["functions"]:
        print(f"- {func['full_name']} (Score: {func['relevance_score']:.4f})")