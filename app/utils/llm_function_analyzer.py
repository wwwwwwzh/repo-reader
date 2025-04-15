"""
LLM Function Analyzer - Uses Deepseek or Groq API to analyze Python functions

This module handles sending functions to the Deepseek or Groq API for analysis and parsing
the response into structured data. It includes slot filling to ensure all required
information is present in the response.
"""

import json
import requests
import logging
import time
import re
import os
from typing import Dict, List, Optional, Any, Tuple, Literal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Configuration
# Note: You should set these via environment variables in production
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = None  # Should be set via environment variable

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = None  # Should be set via environment variable

class SlotFillingError(Exception):
    """Exception raised when required slots are missing in LLM response"""
    pass

class LLMRequestError(Exception):
    """Exception raised when there is an error in the LLM API request"""
    pass

def set_api_key(api_key: str, provider: str = "deepseek") -> None:
    """
    Set the API key for the specified provider
    
    Args:
        api_key: The API key to set
        provider: The API provider (deepseek or groq)
    """
    if provider.lower() == "deepseek":
        global DEEPSEEK_API_KEY
        DEEPSEEK_API_KEY = api_key
        logging.info(f"Set Deepseek API key")
    elif provider.lower() == "groq":
        global GROQ_API_KEY
        GROQ_API_KEY = api_key
        logging.info(f"Set Groq API key")
    else:
        raise ValueError(f"Unsupported provider: {provider}. Use 'deepseek' or 'groq'")

def analyze_function(
    function_content: str, 
    function_name_full: str,
    provider: str = "deepseek",
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    Send a function to the specified API for analysis
    
    Args:
        function_content: The complete source code of the function
        function_name_full: The fully qualified name of the function
        provider: The API provider to use ('deepseek' or 'groq')
        max_retries: Maximum number of retry attempts
    
    Returns:
        Dict containing the structured analysis
    
    Raises:
        LLMRequestError: If there is an error in the LLM API request
        SlotFillingError: If required slots are missing from the response
        ValueError: If the provider is not supported or API key not set
    """
    # Validate provider
    provider = provider.lower()
    if provider not in ["deepseek", "groq"]:
        raise ValueError(f"Unsupported provider: {provider}. Use 'deepseek' or 'groq'")
    
    # Check API key
    if provider == "deepseek" and not DEEPSEEK_API_KEY:
        raise ValueError("Deepseek API key not set. Call set_api_key() with provider='deepseek' first.")
    elif provider == "groq" and not GROQ_API_KEY:
        raise ValueError("Groq API key not set. Call set_api_key() with provider='groq' first.")
    
    # Build the prompt
    logging.info(f"Analyzing function: {function_name_full} using {provider}")
    prompt = build_analysis_prompt(function_content, function_name_full)
    func_length = len(function_content.split('\n'))
    
    # Make the request with retries
    for attempt in range(max_retries):
        try:
            # Call appropriate API
            if provider == "deepseek":
                response = call_deepseek_api(prompt)
            else:  # provider == "groq"
                response = call_groq_api(prompt)
            
            # Parse and validate the response
            analysis = parse_llm_response(response)
            logging.info(f"Analysis received")
            
            analysis['function_name'] = function_name_full
            
            # Ensure all required fields are present
            validate_slots(func_length, analysis)

            return analysis
            
        except (LLMRequestError, SlotFillingError, json.JSONDecodeError) as e:
            logger.warning(f"Attempt {attempt+1}/{max_retries} failed: {str(e)}")
            if attempt == max_retries - 1:
                # This was the last attempt, re-raise the exception
                raise
            # Wait before retrying (exponential backoff)
            time.sleep(2 ** attempt)
    
    # This should never be reached due to the re-raise above
    raise RuntimeError("Unexpected code path in analyze_function")

def build_analysis_prompt(function_content: str, function_name_full: str) -> str:
    """
    Build the prompt for the LLM analysis
    
    Args:
        function_content: The full source code of the function
        function_name_full: The full module name of the function
    
    Returns:
        The complete prompt to send to the LLM
    """
    # Add line numbers to the function content
    lines = function_content.split('\n')
    numbered_content = '\n'.join(f"{i+1:3d} | {line}" for i, line in enumerate(lines))
    # logging.info(numbered_content)
    
    prompt = """
Analyze the following Python function and provide a structured analysis. Your analysis MUST include all of the following components:

1. Short Description: Describe the function's purpose in 10 words or fewer
2. Input/Output Description: Describe the inputs and outputs of the function in 50 words or fewer
3. Long Description: Provide a more detailed explanation of what the function does in 50 words or fewer
4. Components of function: Identify no more than 5 **MUTUALLY EXCLUSIVE and COLLECTIVELY EXHAUSTIVE** components of the function and for each provide:
   - Start line number (def line is line 1, last line of function is length of all lines, first component MUST start at line 1, the start line number of any other component should be exactly 1 more than previous component's end line)
   - End line number (note that end line number of last component MUST match the end line number of the entire function)
   - Short description (10 words or fewer)
   - Long description (50 words or fewer)

Format your response using this exact JSON structure:
```json
{{
  "short_description": "",
  "input_output_description": "",
  "long_description": "",
  "components": [
    {{
      "start_line": 0,
      "end_line": 0,
      "short_description": "",
      "long_description": ""
    }}
  ]
}}
```

Here is the function to analyze:
Function full module name: {function_name_full}
```python
{function}
```
    """.strip().format(function=numbered_content, function_name_full=function_name_full)
    
    return prompt


def call_deepseek_api(prompt: str) -> str:
    """
    Call the Deepseek API with the given prompt
    
    Args:
        prompt: The prompt to send to the API
    
    Returns:
        The API response text
    
    Raises:
        LLMRequestError: If there is an error in the API request
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    data = {
        "model": "deepseek-chat",  # Update with the specific model you're using
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,  # Lower temperature for more consistent responses
        "max_tokens": 2000
    }
    
    try:
        logging.info("Sending request to Deepseek API")
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=data,
            timeout=30  # 30 second timeout
        )

        if response.status_code != 200:
            raise LLMRequestError(f"API request failed with status code {response.status_code}: {response.text}")
        
        response_data = response.json()
        
        # Extract the response content based on Deepseek API structure
        try:
            logging.info("Successfully received response from Deepseek API")
            return response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise LLMRequestError(f"Failed to extract content from API response: {str(e)}")
            
    except requests.RequestException as e:
        raise LLMRequestError(f"API request failed: {str(e)}")

def call_groq_api(prompt: str) -> str:
    """
    Call the Groq API with the given prompt using the Llama-4-Maverick model
    
    Args:
        prompt: The prompt to send to the API
    
    Returns:
        The API response text
    
    Raises:
        LLMRequestError: If there is an error in the API request
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # Using the specified model
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,  # Lower temperature for more consistent responses
        "max_completion_tokens": 2000,
        "top_p": 1.0,
        "stream": False,
        "stop": None
    }
    
    try:
        # logging.info("Sending request to Groq API")
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=data,
            timeout=30  # 30 second timeout
        )

        if response.status_code != 200:
            raise LLMRequestError(f"API request failed with status code {response.status_code}: {response.text}")
        
        response_data = response.json()
        
        # Extract the response content from the Groq API structure
        try:
            logging.info("Successfully received response from Groq API")
            return response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise LLMRequestError(f"Failed to extract content from API response: {str(e)}")
            
    except requests.RequestException as e:
        raise LLMRequestError(f"API request failed: {str(e)}")
    
def parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    Parse the LLM response to extract the JSON analysis
    
    Args:
        response_text: The raw text response from the LLM
    
    Returns:
        Dict containing the parsed analysis
    
    Raises:
        json.JSONDecodeError: If the response cannot be parsed as JSON
    """
    # Extract JSON from the response (it might be wrapped in markdown code blocks)
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    
    if json_match:
        json_str = json_match.group(1)
    else:
        # If no code blocks found, try to use the whole response
        json_str = response_text
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {response_text}")
        raise


def parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    Parse the LLM response to extract the JSON analysis
    
    Args:
        response_text: The raw text response from the LLM
    
    Returns:
        Dict containing the parsed analysis
    
    Raises:
        json.JSONDecodeError: If the response cannot be parsed as JSON
    """
    # Extract JSON from the response (it might be wrapped in markdown code blocks)
    # logging.info(f"parse_llm_response {response_text=}")
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    
    if json_match:
        json_str = json_match.group(1)
    else:
        # If no code blocks found, try to use the whole response
        json_str = response_text
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {response_text}")
        raise

def validate_slots(func_length: int, analysis: Dict[str, Any]) -> None:
    """
    Validate that all required slots are filled in the analysis
    
    Args:
        analysis: The parsed analysis dict
    
    Raises:
        SlotFillingError: If any required slots are missing
    """
    required_fields = [
        "function_name",
        "short_description",
        "input_output_description",
        "long_description",
        "components"
    ]
    
    missing_fields = [field for field in required_fields if field not in analysis or not analysis[field]]
    
    if missing_fields:
        raise SlotFillingError(f"Missing required fields in analysis: {', '.join(missing_fields)}")
    
    # Also validate each component
    if not isinstance(analysis["components"], list):
        raise SlotFillingError("'components' field must be a list")
    
    if analysis["components"][0]['start_line'] != 1:
        raise SlotFillingError("'components' must start at line 1")
    
    if analysis["components"][-1]['end_line'] != func_length:
        raise SlotFillingError("'components' must end at last line of function")
    
    for i, component in enumerate(analysis["components"]):
        component_required_fields = [
            "start_line",
            "end_line", 
            "short_description", 
            "long_description"
        ]
        
        missing_component_fields = [
            field for field in component_required_fields 
            if field not in component or component[field] == ""
        ]
        
        if missing_component_fields:
            raise SlotFillingError(
                f"Missing required fields in component {i}: {', '.join(missing_component_fields)}"
            )
        
        # Validate line numbers
        if not isinstance(component["start_line"], int) or not isinstance(component["end_line"], int):
            raise SlotFillingError(f"Line numbers must be integers in component {i}")
        
        if component["start_line"] > component["end_line"]:
            raise SlotFillingError(
                f"Start line ({component['start_line']}) is greater than " 
                f"end line ({component['end_line']}) in component {i}"
            )
            

# Example usage for testing
# if __name__ == "__main__":
#     import sys
#     import argparse
    
#     parser = argparse.ArgumentParser(description="Analyze a Python function using Deepseek API")
#     parser.add_argument("--file", required=True, help="Path to the Python file")
#     parser.add_argument("--function", required=True, help="Name of the function to analyze")
#     parser.add_argument("--api-key", help="Deepseek API key (or set DEEPSEEK_API_KEY env var)")
    
#     args = parser.parse_args()
    
#     # Get API key
#     api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
#     if not api_key:
#         parser.error("API key must be provided via --api-key or DEEPSEEK_API_KEY env var")
    
#     set_api_key(api_key)
    
#     # Read the file
#     with open(args.file, "r") as f:
#         file_content = f.read()
    
#     # Find the function (very simple approach)
#     pattern = re.compile(rf"def\s+{args.function}\s*\(.*?\).*?:", re.DOTALL)
#     match = pattern.search(file_content)
    
#     if not match:
#         print(f"Function '{args.function}' not found in {args.file}")
#         sys.exit(1)
    
#     # Very simple function extraction - for a real implementation, use AST
#     func_start = match.start()
#     lines = file_content[func_start:].split("\n")
    
#     indent = re.match(r"(\s*)", lines[1]).group(1) if len(lines) > 1 else ""
#     func_content = lines[0] + "\n"
    
#     for line in lines[1:]:
#         if line.strip() and not line.startswith(indent):
#             break
#         func_content += line + "\n"
    
#     try:
#         analysis = analyze_function(func_content, args.function, args.file)
#         print(json.dumps(analysis, indent=2))
#     except Exception as e:
#         print(f"Error analyzing function: {str(e)}")
#         sys.exit(1)