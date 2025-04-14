import ast as std_ast
import json, traceback
import os
from pathlib import Path
from collections import defaultdict
import tokenize
import re
import logging
from app.utils.llm_function_analyzer import set_api_key, analyze_function

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d - %(levelname)s - %(message)s'
)


class FunctionRegistry:
    """Registry of all functions in a project"""
    def __init__(self):
        self.functions = {}  # Map of function_id -> function_info
        self.module_functions = defaultdict(list)  # Map of module_name -> [function_ids]
        self.id_counter = 0
    
    def add_function(self, module_name, func_name, file_path, lineno, end_lineno, class_name=None):
        """Add a function to the registry"""
        # Create a unique ID for this function
        function_id = f"func_{self.id_counter}"
        self.id_counter += 1
        
        # Determine the fully qualified name
        if class_name:
            full_name = f"{module_name}.{class_name}.{func_name}"
            # Also add a simpler version for easier lookup
            simple_name = f"{module_name}.{func_name}"
        else:
            full_name = f"{module_name}.{func_name}"
            simple_name = full_name
        
        # Store function info
        function_info = {
            'id': function_id,
            'name': func_name,
            'full_name': full_name,
            'simple_name': simple_name,
            'module': module_name,
            'class_name': class_name,
            'file_path': file_path,
            'lineno': lineno,
            'end_lineno': end_lineno,
            'callers': [],  # List of function IDs that call this function
            'callees': [],  # List of function IDs this function calls
            'segments': []  # Will be populated later
        }
        
        # print(function_info)
        
        self.functions[function_id] = function_info
        self.module_functions[module_name].append(function_id)
        
        # Return the ID for reference
        return function_id
    
    def get_function_by_name(self, full_name):
        """Look up a function by its fully qualified name"""
        for func_id, func_info in self.functions.items():
            if func_info['full_name'] == full_name or func_info['simple_name'] == full_name:
                return func_id, func_info
        return None, None
    
    def get_function_by_id(self, function_id):
        """Get function info by ID"""
        return self.functions.get(function_id)
    
    def add_caller(self, function_id, caller_id):
        """Add a caller to a function"""
        if function_id in self.functions and caller_id not in self.functions[function_id]['callers']:
            self.functions[function_id]['callers'].append(caller_id)
    
    def add_callee(self, function_id, callee_id):
        """Add a callee to a function"""
        if function_id in self.functions and callee_id not in self.functions[function_id]['callees']:
            self.functions[function_id]['callees'].append(callee_id)
    
    def add_segment(self, function_id, segment):
        """Add a segment to a function"""
        if function_id in self.functions:
            self.functions[function_id]['segments'].append(segment)


def get_node_end_lineno(node):
    """
    Safely determine the end line number of an AST node, handling Python versions
    that don't have end_lineno attribute.
    
    Args:
        node: AST node
        
    Returns:
        End line number of the node
    """
    # Check if end_lineno is directly available (Python 3.8+)
    if hasattr(node, 'end_lineno') and node.end_lineno is not None:
        return node.end_lineno
    
    # Fall back to calculating it manually
    max_line = getattr(node, 'lineno', 0)
    
    # For function definitions, go through the body
    if isinstance(node, std_ast.FunctionDef):
        for item in node.body:
            if hasattr(item, 'lineno'):
                item_end = get_node_end_lineno(item)
                max_line = max(max_line, item_end)
    
    # For other node types, go through all fields
    for field, value in std_ast.iter_fields(node):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, std_ast.AST) and hasattr(item, 'lineno'):
                    item_end = get_node_end_lineno(item)
                    max_line = max(max_line, item_end)
        elif isinstance(value, std_ast.AST) and hasattr(value, 'lineno'):
            value_end = get_node_end_lineno(value)
            max_line = max(max_line, value_end)
    
    return max_line


class FunctionScanner(std_ast.NodeVisitor):
    """Scans a Python file for all function definitions"""
    def __init__(self, registry, module_name, file_path):
        self.registry = registry
        self.module_name = module_name
        self.file_path = file_path
        self.current_class = None
    
    def visit_ClassDef(self, node):
        """Handle class definitions"""
        old_class = self.current_class
        self.current_class = node.name
        
        # Visit all nodes in the class body
        self.generic_visit(node)
        
        # Restore previous class context
        self.current_class = old_class
    
    def visit_FunctionDef(self, node):
        """Handle function definitions"""
        # Safely get the end line number
        lineno = node.lineno
        end_lineno = get_node_end_lineno(node)
        
        # Add function to registry
        self.registry.add_function(
            self.module_name, 
            node.name, 
            self.file_path,
            lineno,
            end_lineno,
            self.current_class
        )
        
        # Visit function body
        self.generic_visit(node)

class SimpleImportTracker(std_ast.NodeVisitor):
    """Simple tracker that just records which modules are imported in a file"""
    def __init__(self):
        self.imported_modules = set()  # Set of module names that are imported
        self.from_imports = {}  # Maps local function names to their modules
    
    def visit_Import(self, node):
        """Handle regular imports: import foo, import foo as bar"""
        for alias in node.names:
            # Add the module name to our set
            module_name = alias.name
            self.imported_modules.add(module_name)
    
    def visit_ImportFrom(self, node):
        """Handle from imports: from foo import bar"""
        if node.module:
            # Add the module to our imported modules
            self.imported_modules.add(node.module)
            
            # Also track which functions were imported from which modules
            for alias in node.names:
                if alias.name != '*':
                    self.from_imports[alias.asname or alias.name] = node.module
            


class CallAnalyzer(std_ast.NodeVisitor):
    """Analyze function calls within a function"""
    def __init__(self, registry, function_id, module_name, file_path, source_lines):
        self.registry = registry
        self.function_id = function_id
        self.module_name = module_name
        self.file_path = file_path
        self.source_lines = source_lines
        self.import_tracker = SimpleImportTracker()
        self.calls = []
        self.segments = []
        
        # Initialize import tracker first
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            try:
                tree = std_ast.parse(f.read())
                self.import_tracker.visit(tree)
            except Exception as e:
                print(f"Error parsing imports in {file_path}: {e}")
    
    def visit_Call(self, node):
        """Handle function calls"""
        callee_name = self._get_call_name(node.func)
        if callee_name:
            # Look up the callee in the registry
            callee_id, callee_info = self.find_matching_function(callee_name)
            if callee_id:
                # Get the call line from source
                start_line = node.lineno
                end_line = getattr(node, 'end_lineno', node.lineno)
                call_source = ''.join(self.source_lines[start_line-1:end_line]).strip()
                
                # Record the call
                call_info = {
                    'callee_id': callee_id,
                    'callee_name': callee_info['full_name'],
                    'lineno': start_line,
                    'end_lineno': end_line,
                    'source': call_source
                }
                self.calls.append(call_info)
                
                # Update relationships
                self.registry.add_caller(callee_id, self.function_id)
                self.registry.add_callee(self.function_id, callee_id)
                
                # Add a call segment
                segment = {
                    'type': 'call',
                    'content': call_source,
                    'lineno': start_line,
                    'end_lineno': end_line,
                    'callee_id': callee_id,
                    'callee_name': callee_info['full_name']
                }
                self.segments.append(segment)
        
        # Visit arguments
        self.generic_visit(node)
    
    def _get_call_name(self, node):
        """Extract the name of a called function"""
        if isinstance(node, std_ast.Name):
            # Simple name like 'func()'
            return node.id
        elif isinstance(node, std_ast.Attribute):
            # Attribute chain like 'module.func()'
            return self._get_attribute_chain(node)
        return None
    
    def _get_attribute_chain(self, node):
        """Extract an attribute chain like module.submodule.function"""
        if isinstance(node, std_ast.Name):
            return node.id
        elif isinstance(node, std_ast.Attribute):
            base = self._get_attribute_chain(node.value)
            if base:
                return f"{base}.{node.attr}"
        return None
    
    def find_matching_function(self, call_name):
        """
        Find the best matching function for a given call name.
        This handles different cases:
        1. Direct match by full name
        2. Match by simple name when imported
        3. Match by suffix (e.g., 'helpers.validate_input' matches 'utils.helpers.validate_input')
        """
        # logging.info(f"{call_name=}, {self.import_tracker.imported_modules=}")
        # Case 1: Direct match by full name
        func_id, func_info = self.registry.get_function_by_name(call_name)
        # logging.info(f"{func_id=}, {func_info=}")
        if func_id:
            return func_id, func_info
        
        # Case 2: If it's a simple name (no dots), check if it might be an imported function
        if '.' not in call_name:
            # Check if we have an import statement for this function
            if call_name in self.import_tracker.from_imports:
                module = self.import_tracker.from_imports[call_name]
                func_full_name = f"{module}.{call_name}"
                func_id, func_info = self.registry.get_function_by_name(func_full_name)
                if func_id:
                    return func_id, func_info
            
            # Try matching against any function with the same name
            # First look in current module (higher priority)
            current_module_name = f"{self.module_name}.{call_name}"
            func_id, func_info = self.registry.get_function_by_name(current_module_name)
            if func_id:
                return func_id, func_info
                
            # Then try all other functions
            for other_id, other_info in self.registry.functions.items():
                if other_info['name'] == call_name:
                    # Check if the module is imported
                    module_parts = other_info['module'].split('.')
                    for part in module_parts:
                        if part in self.import_tracker.imported_modules:
                            logging.info(f"{other_id=}, {other_info=}")
                            return other_id, other_info
        
        # Case 3: Check for suffix matches (handles module.func cases)
        # This is useful for cases like "helpers.validate_input" when the full name is 
        # "utils.helpers.validate_input" but we only see "helpers" in the code
        for func_id, func_info in self.registry.functions.items():
            # logging.info(f"{func_id=} {func_info=}")
            func_full_name = func_info['full_name']
            func_name = func_full_name.split('.')[-1]
            # Check if the call name is a suffix of the full name
            if func_full_name.endswith(call_name) and (
                # Make sure the boundaries match to avoid partial matches
                len(func_name) == len(call_name)
            ):
                # Verify that the module is imported
                func_module = func_info['module']
                if func_module in self.import_tracker.imported_modules:
                    return func_id, func_info
        
        return None, None




def extract_function_content(file_path, start_line, end_line):
    """
    Extract function content from a file based on line numbers
    
    Args:
        file_path: Path to the source file
        start_line: Starting line number (absolute, 1-based)
        end_line: Ending line number (absolute, 1-based)
    
    Returns:
        String containing the function content
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        # Read all lines and extract the relevant ones
        # Note: line numbers are 1-based but array indices are 0-based
        lines = f.readlines()
        # Subtract 1 from line numbers to convert to 0-based indices
        content = ''.join(lines[start_line-1:end_line])
        # logging.warning(start_line)
        # logging.warning(end_line)
        # logging.warning(content)
        if content.endswith('\n'): # remove trailing new line for easier analysis later on. See build_analysis_prompt()
            content = content[:-1]
        return content
    
def extract_segments(file_path, function_info, call_segments):
    """
    Extract all segments from a function in three types:
      - "call": function call segments (from call_segments)
      - "comment": consecutive standalone comment lines combined into one comment segment
      - "code": any code that is not part of a call or a standalone comment

    Consecutive standalone comments will be concatenated, and each segment is annotated
    with its starting (and ending) line number.

    If a segment spans across multiple components, it will be split into multiple segments
    to ensure each segment belongs to exactly one component.

    Args:
        file_path (str): Path to the source file.
        function_info (dict): Dictionary with function details, including 'lineno' and 'end_lineno'.
        call_segments (list): List of call segments (each a dict with keys including 'lineno', 'end_lineno', 
                              'callee_id', 'callee_name', etc.).

    Returns:
        List[dict]: List of segments. Each segment is a dict with at least the following keys:
            - type: one of "call", "comment", or "code"
            - content: the text content of the segment
            - lineno: starting line number of the segment
            - end_lineno: ending line number of the segment
    """
    # Read the source file entirely (we also need it for slicing call segments or code segments)
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        source_lines = f.readlines()
    
    # Retrieve the function boundaries (absolute line numbers)
    start_line = function_info['lineno']  # absolute position of def 
    end_line = function_info['end_lineno']
    # logging.warning(f"{start_line=}, {end_line=}")
    
    # Extract the function's own lines (this is used later for tokenizing comments)
    function_lines = source_lines[start_line-1:end_line]  # 0 is def
    # logging.warning(f"{function_lines[-2:]=}")
    relative_end_line = len(function_lines)  # needs +1 when indexing
    
    # Use tokenize to extract all comments falling inside the function boundary.
    all_comments = []
    with open(file_path, 'rb') as f:
        try:
            tokens = tokenize.tokenize(f.readline)
            for tok in tokens:
                # Only consider tokens within our function range.
                if tok.type == tokenize.COMMENT and start_line <= tok.start[0] <= end_line:
                    all_comments.append({
                        'type': 'comment',     # our renamed type for comment segments
                        'content': tok.string,
                        'lineno': tok.start[0] - start_line + 1,
                        'col': tok.start[1],
                        'is_standalone': (tok.start[1] == 0)  # if column is 0, then the comment stands on its own.
                    })
        except Exception as e:
            print(f"Error extracting comments: {e}")

    # Build a mapping from each absolute line number to its call segment (if it belongs to one)
    # Note that for each call segment, every line in the range [call['lineno'], call['end_lineno']] maps to that call.
    call_map = {}
    for call in call_segments:
        for line in range(call['lineno'], call['end_lineno'] + 1):
            call_map[line] = call
    
    # Build a mapping for standalone comments: only include if it is truly standalone.
    comment_map = {}
    for comment in all_comments:
        # if comment['is_standalone']:
        comment_map[comment['lineno']] = comment
    # print("comment_map")
    # print(comment_map)
    logging.info(f"{call_map=}, {comment_map=}")
    segments = []

    i = 1  # i is relative
    while i <= relative_end_line:
        # print(i)
        # -- Process a call segment first --
        if i in call_map and call_map[i]['lineno'] == i:
            # Create the call segment by joining source lines covering the call.
            call_seg = call_map[i]
            segments.append({
                'type': 'call',
                'content': call_seg['content'],
                'lineno': call_seg['lineno'], 
                'end_lineno': call_seg['end_lineno'],
                'callee_id': call_seg.get('callee_id'),
                'callee_name': call_seg.get('callee_name')
            })
            # Jump to the line after the call segment.
            i = call_seg['end_lineno'] + 1
            continue
        
        # -- Process a standalone comment --
        if i in comment_map:
            # Start a block for consecutive standalone comments.
            comment_start = i
            comment_block = [comment_map[i]['content']]
            i += 1
            # Continue as long as the next lines are also standalone comments.
            while i <= relative_end_line and i in comment_map:
                comment_block.append(comment_map[i]['content'])
                i += 1
            # Merge the consecutive comments into one segment.
            segments.append({
                'type': 'comment',
                'content': "\n".join(comment_block),
                'lineno': comment_start,
                'end_lineno': i - 1
            })
            continue
        
        # -- Process a code segment --
        # If the line does not belong to a call segment or a standalone comment, it is code.
        code_start = i
        code_lines = []
        while i <= relative_end_line and (i not in call_map) and (i not in comment_map):
            code_lines.append(function_lines[i-1])
            i += 1
        code_content = "".join(code_lines).rstrip()
        if code_content:
            segments.append({
                'type': 'code',
                'content': code_content,
                'lineno': code_start,
                'end_lineno': i - 1
            })
    
    # Ensure the segments are sorted by starting line number.
    segments.sort(key=lambda seg: seg['lineno'])
    
    # Split segments that cross component boundaries
    final_segments = []
    func_components = sorted(function_info.get('components', []), key=lambda c: c['start_lineno'])
    
    for segment in segments:
        # Convert segment relative line numbers to absolute for comparison with components
        segment_abs_start = function_info['lineno'] + segment['lineno'] - 1
        segment_abs_end = function_info['lineno'] + segment['end_lineno'] - 1
        
        # If no components or segment is a call (which we don't want to split), add as is
        if not func_components or segment['type'] == 'call':
            # Still try to assign a component ID if possible
            for component in func_components:
                if (component['start_lineno'] <= segment_abs_start and 
                    segment_abs_end <= component['end_lineno']):
                    logging.info(f"attaching call to component: {segment=}")
                    segment['component_id'] = component['id']
                    break
            final_segments.append(segment)
            continue
        
        # Check if segment spans multiple components
        segment_processed = False
        
        for idx, component in enumerate(func_components):
            component_start = component['start_lineno']
            component_end = component['end_lineno']
            
            # Skip components that end before the segment starts
            if component_end < segment_abs_start:
                continue
                
            # Skip components that start after the segment ends
            if component_start > segment_abs_end:
                break
                
            # Case 1: Segment starts and ends within this component
            if component_start <= segment_abs_start and segment_abs_end <= component_end:
                segment['component_id'] = component['id']
                final_segments.append(segment)
                segment_processed = True
                logging.info(f"attaching call to component: {segment=}")
                break
                
            # Case 2: Segment starts in this component but ends later
            if component_start <= segment_abs_start and segment_abs_end > component_end:
                # Calculate relative line numbers within the function
                split_rel_start = segment['lineno']
                split_rel_end = component_end - function_info['lineno'] + 1
                
                # Content for the first part (from segment start to component end)
                first_part_lines = function_lines[split_rel_start-1:split_rel_end]
                first_part_content = "".join(first_part_lines).rstrip()
                
                if first_part_content:
                    # Add first part segment
                    first_part = {
                        'type': segment['type'],
                        'content': first_part_content,
                        'lineno': split_rel_start,
                        'end_lineno': split_rel_end,
                        'component_id': component['id']
                    }
                    final_segments.append(first_part)
                
                # Adjust segment for the remaining part
                segment['lineno'] = split_rel_end + 1
                segment_abs_start = function_info['lineno'] + segment['lineno'] - 1
                
                # Recalculate content for the remaining part
                remaining_lines = function_lines[split_rel_end:segment['end_lineno']]
                remaining_content = "".join(remaining_lines).rstrip()
                
                if not remaining_content:
                    segment_processed = True
                    break
                    
                segment['content'] = remaining_content
                logging.warning(f"spliting segment across component: {segment=}")
                # Continue to next component to process the remaining part
                
            # Case 3: Segment starts before this component but ends within it
            elif component_start > segment_abs_start and segment_abs_end <= component_end:
                # Calculate relative line numbers within the function
                split_rel_end = segment['end_lineno']
                split_rel_start = component_start - function_info['lineno'] + 1
                
                # Content for the last part (from component start to segment end)
                last_part_lines = function_lines[split_rel_start-1:split_rel_end]
                last_part_content = "".join(last_part_lines).rstrip()
                
                if last_part_content:
                    # Add last part segment
                    last_part = {
                        'type': segment['type'],
                        'content': last_part_content,
                        'lineno': split_rel_start,
                        'end_lineno': split_rel_end,
                        'component_id': component['id']
                    }
                    final_segments.append(last_part)
                
                # Adjust segment for the first part
                segment['end_lineno'] = split_rel_start - 1
                
                # Recalculate content for the first part
                first_lines = function_lines[segment['lineno']-1:segment['end_lineno']]
                first_content = "".join(first_lines).rstrip()
                
                if first_content:
                    segment['content'] = first_content
                    # Try to find a component for the first part
                    for prev_comp in func_components:
                        prev_comp_start = prev_comp['start_lineno']
                        prev_comp_end = prev_comp['end_lineno']
                        segment_abs_start = function_info['lineno'] + segment['lineno'] - 1
                        segment_abs_end = function_info['lineno'] + segment['end_lineno'] - 1
                        
                        if (prev_comp_start <= segment_abs_start and 
                            segment_abs_end <= prev_comp_end):
                            segment['component_id'] = prev_comp['id']
                            break
                            
                    final_segments.append(segment)
                
                segment_processed = True
                break
                
        # If segment wasn't processed (no matching component found), add it without a component ID
        if not segment_processed:
            logging.warning(f"SEGMENT NOT ATTACHED: {segment=}")
            # segment.pop('component_id', None)  # Remove any existing component_id
            segment['component_id'] = func_components[0]['id']
            final_segments.append(segment)
    
    # Ensure segments are sorted by starting line number
    final_segments.sort(key=lambda seg: seg['lineno'])
    
    return final_segments



def scan_project(project_root):
    """
    Scan an entire project to build a function registry with all functions,
    their calls, and segments
    
    Args:
        project_root: Path to the project root directory
        
    Returns:
        FunctionRegistry object with all project functions
    """
    registry = FunctionRegistry()
    project_root = Path(project_root)
    
    # First pass: Find all functions in the project
    print("First pass: Scanning for all functions...")
    for py_file in project_root.rglob('*.py'):
        if 'venv' in str(py_file) or 'env' in str(py_file):
            continue
            
        try:
            relative_path = py_file.relative_to(project_root)
            if py_file.name == '__init__.py':
                module_name = '.'.join(relative_path.parent.parts)
                if not module_name:
                    module_name = 'root'
            else:
                module_name = '.'.join(relative_path.with_suffix('').parts)
                
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                try:
                    tree = std_ast.parse(f.read())
                    scanner = FunctionScanner(registry, module_name, str(py_file))
                    scanner.visit(tree)
                    
                except Exception as e:
                    print(f"Error parsing {py_file}: {e}")
        except ValueError:
            continue
    
    logging.info(f"Found {registry.functions} functions")
    
    # Second pass: Use LLM to analyze functions and extract components

    print("Second pass: Analyzing functions with LLM...")
    
    set_api_key(os.environ.get("DEEPSEEK_API_KEY"), provider="deepseek")
    set_api_key(os.environ.get("GROQ_API_KEY"), provider="groq")
    
    for func_id, func_info in registry.functions.items():
        # Get function source code
        file_path = func_info['file_path']
        # Extract function content from the file based on line numbers
        # Note: lineno and end_lineno are absolute (file-based) line numbers
        logging.info(f"{func_id}, {func_info}")
        func_content = extract_function_content(file_path, func_info['lineno'], func_info['end_lineno'])
        
        
        
        try:
            # Call LLM to analyze the function
            analysis = analyze_function(func_content, func_info['full_name'], provider="groq")
            logging.info(f"{analysis=}")
            # Store LLM-generated metadata in function info
            func_info['short_description'] = analysis['short_description']
            func_info['input_output_description'] = analysis['input_output_description']
            func_info['long_description'] = analysis['long_description']
            
            # Process components
            components = []
            for i, comp in enumerate(analysis['components']):
                logging.info(f"{comp=}")
                # Note: LLM returns relative line numbers (1 = first line of function)
                # Convert to absolute line numbers for storage
                abs_start_line = func_info['lineno'] + comp['start_line'] - 1
                abs_end_line = func_info['lineno'] + comp['end_line'] - 1
                
                component = {
                    'id': f"{func_id}_component_{i}",
                    'short_description': comp['short_description'],
                    'long_description': comp['long_description'],
                    'start_lineno': abs_start_line,
                    'end_lineno': abs_end_line,
                    'index': i
                }
                components.append(component)
            
            # Store components in function info
            func_info['components'] = components
            
        except Exception as e:
            print(f"Error analyzing function {func_info['full_name']} with LLM: {e}")
            traceback.print_exc()

    # Third pass: Analyze function calls and build segments
    logging.info("Third pass: Analyzing function calls and building segments...")
    for func_id, func_info in registry.functions.items():
        file_path = func_info['file_path']
        module_name = func_info['module']
        
        
        # Skip if file doesn't exist
        if not os.path.exists(file_path):
            continue
        
        # Read the source code
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source_lines = f.readlines()
            
        # Extract function body for analysis
        function_body_lines = source_lines[func_info['lineno']-1:func_info['end_lineno']]
        function_body = ''.join(function_body_lines)
        
        # If function body is empty or just pass, skip call analysis
        if not function_body.strip() or re.match(r'\s*pass\s*', function_body.strip()):
            continue
        
        # Parse the function body to find calls
        try:
            tree = std_ast.parse(function_body)
                
            analyzer = CallAnalyzer(registry, func_id, module_name, file_path, function_body_lines)
            analyzer.visit(tree)
            
            # Process segments
            call_segments = analyzer.segments
            if func_info['name'] == 'main': 
                logging.info(f"{func_info=}\n{analyzer.calls=}\n{analyzer.segments=}")
                logging.info(f"Seg: {call_segments}")
            all_segments = extract_segments(file_path, func_info, call_segments)
            
            # Add segments to the function
            for segment in all_segments:
                registry.add_segment(func_id, segment)
                
        except Exception as e:
            print(f"Error analyzing function {func_info['full_name']}: {e}")
    
    return registry


def find_entry_points(registry, entry_files):
    """
    Find entry points in the registry based on a list of entry files
    
    Args:
        registry: FunctionRegistry object
        entry_files: List of file paths to treat as entries, can include
                     file_path:function_name format
        
    Returns:
        List of function IDs that are entry points
    """
    entry_points = []
    
    for entry_spec in entry_files:
        # Check if entry spec includes a function name
        if ':' in entry_spec:
            file_path, function_name = entry_spec.split(':', 1)
            
            # Handle special case for __main__
            if function_name == '__main__':
                for func_id, func_info in registry.functions.items():
                    # Look for all functions in this file
                    if os.path.basename(func_info['file_path']) == file_path:
                        # Check if it's a main function or in a main block
                        if (func_info['name'] == 'main' or 
                            func_info['full_name'].endswith('.main') or
                            '__main__' in func_info['full_name']):
                            entry_points.append(func_id)
                            print(f"Found entry point: {func_info['full_name']} (main)")
            else:
                # Find the specific function in this file
                found = False
                for func_id, func_info in registry.functions.items():
                    # Match by file name and function name
                    rel_path = os.path.basename(func_info['file_path'])
                    if rel_path == file_path or rel_path == os.path.basename(file_path):
                        if (func_info['name'] == function_name or 
                            func_info['full_name'].endswith(f'.{function_name}')):
                            entry_points.append(func_id)
                            print(f"Found entry point: {func_info['full_name']}")
                            found = True
                
                if not found:
                    print(f"Warning: Could not find function {function_name} in {file_path}")
        else:
            # Treat the whole file as an entry point
            file_path = entry_spec
            file_count = 0
            
            for func_id, func_info in registry.functions.items():
                rel_path = os.path.basename(func_info['file_path'])
                if rel_path == file_path or rel_path == os.path.basename(file_path):
                    entry_points.append(func_id)
                    print(f"Found entry point: {func_info['full_name']}")
                    file_count += 1
            
            if file_count == 0:
                print(f"Warning: Could not find any functions in {file_path}")
    
    return entry_points

def build_tree_from_function(registry, function_id, max_depth=3, current_depth=0):
    """
    Build a tree from a function node with segments
    
    Args:
        registry: FunctionRegistry object
        function_id: ID of the function to use as root
        max_depth: Maximum depth of the tree (excluding segments)
        current_depth: Current depth (for recursion)
        
    Returns:
        Tree structure
    """
    if current_depth > max_depth or function_id is None:
        return None
    
    # Get function info
    func_info = registry.get_function_by_id(function_id)
    if not func_info:
        return None
    
    # Create node for this function
    node = {
        'id': function_id,
        'name': func_info['name'],
        'full_name': func_info['full_name'],
        'file_path': func_info['file_path'],
        'segments': func_info['segments'],
        'children': []
    }
    
    # Add callees as children
    if current_depth < max_depth:
        for callee_id in func_info['callees']:
            child_node = build_tree_from_function(
                registry, callee_id, max_depth, current_depth + 1
            )
            if child_node:
                node['children'].append(child_node)
    
    return node


def print_tree(node, max_level=2, current_level=0, prefix=""):
    """
    Print a tree with levels
    
    Args:
        node: Tree node to print
        max_level: Maximum level to print (0=root, 1=segments, 2=callee functions, etc.)
        current_level: Current level (for recursion)
        prefix: Prefix string for indentation
    """
    if node is None:
        return
    
    # Print the current node
    print(f"{prefix}└── {node['name']} ({node['full_name']})")
    
    # If we're at the max level, stop
    if current_level >= max_level:
        return
    
    # Print segments at level 1
    if current_level + 1 <= max_level and 'segments' in node:
        segment_prefix = prefix + "    "
        for i, segment in enumerate(node['segments']):
            seg_type = segment['type']
            content = segment['content']
            
            # Shorten long content
            if len(content) > 100:
                content = content[:97] + "..."
            
            # Print segment
            if seg_type == 'call' and 'callee_name' in segment:
                print(f"{segment_prefix}├── [CALL] {segment['callee_name']}: {content}")
            else:
                print(f"{segment_prefix}├── [{seg_type.upper()}] {content}")
    
    # Print children at level 2+
    if current_level + 2 <= max_level and 'children' in node:
        child_prefix = prefix + "    "
        for child in node['children']:
            print_tree(child, max_level, current_level + 2, child_prefix)


def print_function_info(registry, function_id):
    """
    Print detailed information about a function
    
    Args:
        registry: FunctionRegistry object
        function_id: ID of the function to print
    """
    func_info = registry.get_function_by_id(function_id)
    if not func_info:
        print(f"Function {function_id} not found")
        return
    
    print("=" * 60)
    print(f"FUNCTION: {func_info['full_name']}")
    print(f"ID: {function_id}")
    print(f"File: {func_info['file_path']}")
    print(f"Lines: {func_info['lineno']} - {func_info['end_lineno']}")
    
    # Print callers
    print("\nCALLERS:")
    if func_info['callers']:
        for caller_id in func_info['callers']:
            caller = registry.get_function_by_id(caller_id)
            if caller:
                print(f"  - {caller['full_name']}")
    else:
        print("  None")
    
    # Print callees
    print("\nCALLEES:")
    if func_info['callees']:
        for callee_id in func_info['callees']:
            callee = registry.get_function_by_id(callee_id)
            if callee:
                print(f"  - {callee['full_name']}")
    else:
        print("  None")
    
    # Print segments
    print("\nSEGMENTS:")
    for i, segment in enumerate(func_info['segments']):
        seg_type = segment['type']
        content = segment['content']
        print(f"\n  {i+1}. [{seg_type.upper()}]")
        print(f"     Line: {segment['lineno']}")
        if seg_type == 'call' and 'callee_name' in segment:
            print(f"     Calls: {segment['callee_name']}")
        print("-" * 40)
        
        # Print the content with line numbers
        lines = content.split('\n')
        for j, line in enumerate(lines):
            print(f"     {j+1:3d} | {line}")
    
    print("=" * 60)


# Example usage:
# if __name__ == "__main__":
#     import sys
    
#     if len(sys.argv) < 2:
#         print("Usage: python ast_parser.py <project_root> [entry_file1] [entry_file2] ...")
#         sys.exit(1)
    
#     project_root = sys.argv[1]
#     entry_files = sys.argv[2:] if len(sys.argv) > 2 else []
    
#     # Scan project
#     registry = scan_project(project_root)
    
#     # Find entry points
#     if entry_files:
#         entry_points = find_entry_points(registry, entry_files)
#         print(f"\nFound {len(entry_points)} entry points")
        
#         # Print trees for each entry point
#         for entry_id in entry_points:
#             entry_info = registry.get_function_by_id(entry_id)
#             if entry_info:
#                 print(f"\nTree for entry point: {entry_info['full_name']}")
#                 tree = build_tree_from_function(registry, entry_id, max_depth=3)
#                 print_tree(tree, max_level=3)