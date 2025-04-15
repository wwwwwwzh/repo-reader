import pickle
import json
import os
from app.utils.ast_parser import FunctionRegistry

def save_registry(registry, output_path, format='pickle'):
    """
    Save a function registry to a file
    
    Args:
        registry: FunctionRegistry object to save
        output_path: Path to save the registry to
        format: Format to use ('pickle' or 'json')
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if format == 'pickle':
            with open(output_path, 'wb') as f:
                pickle.dump(registry, f)
        elif format == 'json':
            # Convert registry to a JSON-serializable dict
            registry_dict = {
                'functions': registry.functions,
                'module_functions': {k: list(v) for k, v in registry.module_functions.items()},
                'id_counter': registry.id_counter
            }
            with open(output_path, 'w') as f:
                json.dump(registry_dict, f, indent=2)
        else:
            print(f"Unsupported format: {format}")
            return False
            
        print(f"Registry saved to {output_path}")
        return True
    
    except Exception as e:
        print(f"Error saving registry: {e}")
        return False

def load_registry(input_path, format='pickle'):
    """
    Load a function registry from a file
    
    Args:
        input_path: Path to load the registry from
        format: Format to use ('pickle' or 'json')
    
    Returns:
        FunctionRegistry: The loaded registry, or None if loading failed
    """
    try:
        if not os.path.exists(input_path):
            print(f"File not found: {input_path}")
            return None
            
        if format == 'pickle':
            with open(input_path, 'rb') as f:
                registry = pickle.load(f)
        elif format == 'json':
            with open(input_path, 'r') as f:
                registry_dict = json.load(f)
            
            # Create a new FunctionRegistry and populate it
            registry = FunctionRegistry()
            registry.functions = registry_dict['functions']
            
            # Convert lists back to sets for module_functions
            registry.module_functions = {
                k: set(v) if isinstance(v, list) else v 
                for k, v in registry_dict['module_functions'].items()
            }
            
            registry.id_counter = registry_dict['id_counter']
        else:
            print(f"Unsupported format: {format}")
            return None
            
        print(f"Registry loaded from {input_path}")
        return registry
    
    except Exception as e:
        print(f"Error loading registry: {e}")
        return None