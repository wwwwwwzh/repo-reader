import ast as std_ast
import json, traceback
import os
from pathlib import Path
from collections import defaultdict
import re, textwrap, tokenize
from typing import List, Optional, Iterable, Tuple

from app.utils.llm_function_analyzer import set_api_key, analyze_function

from app.utils.logging_utils import logger




class FunctionRegistry:
    """
    Registry of every function/method we’ve seen.

    Fast indexes:
        ctor_by_class      :  DemoApp         -> func_id
        methods_by_class   :  DemoApp.run_demo -> func_id
    """
    def __init__(self):
        self.functions          = {}                  # func_id -> info dict
        self.module_functions   = defaultdict(list)   # mod        -> [ids]
        self.ctor_by_class      = {}                  # class      -> func_id
        self.methods_by_class   = {}                  # cls.method -> func_id
        self.id_counter         = 0

    # ..........................................................
    def add_function(self, module_name, func_name,
                     file_path, lineno, end_lineno, class_name=None, param_order=None, param_types=None):

        func_id     = f"func_{self.id_counter}"
        self.id_counter += 1

        if class_name:                       # method
            full_name   = f"{module_name}.{class_name}.{func_name}"
            # simple_name = f"{module_name}.{func_name}"
            key         = f"{class_name}.{func_name}"
        else:                                # free function
            full_name   = f"{module_name}.{func_name}"
            # simple_name = full_name
            key         = None

        info = {
            "id"        : func_id,
            "name"      : func_name,
            "full_name" : full_name,
            "module"    : module_name,
            "class_name": class_name,        # ← keep the class!
            "file_path" : file_path,
            "lineno"    : lineno,
            "end_lineno": end_lineno,
            
            'short_description': "",
            'input_output_description': "", 
            'long_description': "",

            "callers"   : [],
            "callees"   : [],
            "segments"  : [],
            
            # for within function class method call
            "param_order"          : param_order or [],   # always a list
            "param_types"          : param_types or {},   # always a dict
            "inferred_param_types" : {},                 # to be filled later

        }

        #  ----  fast indexes  ----
        if class_name:
            if func_name == "__init__":
                self.ctor_by_class[class_name] = func_id
            self.methods_by_class[key] = func_id

        self.functions[func_id] = info
        self.module_functions[module_name].append(func_id)
        return func_id

    # ..........................................................
    def get_function_by_name(self, full_or_simple):
        
        for fid, finfo in self.functions.items():
            if finfo["full_name"] == full_or_simple:
            #    or finfo["simple_name"] == full_or_simple
                return fid, finfo
        return None, None

    def get_constructor(self, class_name):
        fid = self.ctor_by_class.get(class_name)
        return (fid, self.functions[fid]) if fid else (None, None)

    def get_method(self, class_name, method_name):
        fid = self.methods_by_class.get(f"{class_name}.{method_name}")
        return (fid, self.functions[fid]) if fid else (None, None)
    
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
        
    def _ann_to_str(self, ann):
        if isinstance(ann, std_ast.Name):            # Foo
            return ann.id
        if isinstance(ann, std_ast.Attribute):       # pkg.Foo
            return f"{self._ann_to_str(ann.value)}.{ann.attr}"
        if isinstance(ann, std_ast.Subscript):       # list[Foo]
            return self._ann_to_str(ann.value)
        if isinstance(ann, (std_ast.Constant, std_ast.Constant)):     # "Foo"
            logger.critical("YES")
            return ann.value if isinstance(ann, std_ast.Constant) else ann.s
        return ""

    
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
        param_order = []
        param_types = {}
        # positional / keyword‑only args
        for arg in node.args.args + node.args.kwonlyargs:
            param_order.append(arg.arg)
            if arg.annotation:
                # DemoApp.Foo → Foo
                param_types[arg.arg] = self._ann_to_str(arg.annotation).split(".")[-1]

        # *args / **kwargs (keep names for matching but no types)
        if node.args.vararg:
            param_order.append("*" + node.args.vararg.arg)
        if node.args.kwarg:
            param_order.append("**" + node.args.kwarg.arg)
            
        # Add function to registry
        self.registry.add_function(
            self.module_name, 
            node.name, 
            self.file_path,
            lineno,
            end_lineno,
            self.current_class,
            param_order=param_order,
            param_types=param_types,
        )
        
        # Visit function body
        self.generic_visit(node)
        
    def visit_If(self, node):
        """Handle if statements - looking for if __name__ == "__main__": blocks"""
        # Check if this is an if __name__ == "__main__" block
        if (isinstance(node.test, std_ast.Compare) and
            isinstance(node.test.left, std_ast.Name) and
            node.test.left.id == "__name__" and
            len(node.test.ops) == 1 and
            isinstance(node.test.ops[0], std_ast.Eq) and
            len(node.test.comparators) == 1 and
            isinstance(node.test.comparators[0], std_ast.Constant) and
            node.test.comparators[0].value == "__main__"):
            # This is a main block, register it as a function
            lineno = node.lineno
            end_lineno = get_node_end_lineno(node)
            
            # Add as a special function named "__main__"
            self.registry.add_function(
                self.module_name,
                "__main__",  # Special name for the main block
                self.file_path,
                lineno,
                end_lineno,
                None  # No class context for main block
            )
        
        # Continue visiting the if statement body
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
    """
    Understands                     Resolves to
        DemoApp()               →   DemoApp.__init__
        demo.run_demo()         →   DemoApp.run_demo
        self.helper(...)        →   CurrentClass.helper
    """
    def __init__(self, registry, function_id, module_name,
                 file_path, source_lines, function_info):
        self.registry        = registry
        self.function_id     = function_id
        self.module_name     = module_name
        self.file_path       = file_path
        self.source_lines    = source_lines

        self.import_tracker  = SimpleImportTracker()
        self.calls           = []
        self.segments        = []
        self.var_class_map   = {}                          # demo → DemoApp
        self.current_class   = function_info["class_name"] # None for free func

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = std_ast.parse(f.read())
        self.import_tracker.visit(tree)
        
        self.var_class_map = {
            **function_info.get("param_types", {}),
            **self.var_class_map
        }
        if self.current_class:
            self.var_class_map.setdefault("self", self.current_class)
            self.var_class_map.setdefault("cls",  self.current_class)


    # ..........................................................
    #   Track “demo = DemoApp()”
    # ..........................................................
    def visit_Assign(self, node):
        if isinstance(node.value, std_ast.Call):
            cls_name = self._get_call_name(node.value.func)
            if cls_name:
                cls_simple = cls_name.split(".")[-1]
                for tgt in node.targets:
                    if isinstance(tgt, std_ast.Name):
                        self.var_class_map[tgt.id] = cls_simple
        self.generic_visit(node)
        
        
    def visit_Call(self, node):
        """Handle function calls"""
        callee_name = self._get_call_name(node.func)
        # logger.critical(callee_name)
        if callee_name:
            # Look up the callee in the registry
            callee_id, callee_info = self.find_matching_function(callee_name)
            callee_info = self.registry.get_function_by_id(callee_id)
            if not callee_info:                # safety
                return

            # 1. positional arguments ------------------------------------------------
            for formal, actual in zip(callee_info["param_order"], node.args):
                # ignore *args / **kwargs markers in the formal list
                if formal.startswith("*"):
                    continue

                if isinstance(actual, std_ast.Name):
                    actual_name = actual.id
                    if actual_name in self.var_class_map:           # we know its class
                        cls = self.var_class_map[actual_name]
                        callee_info["inferred_param_types"][formal] = cls

            # 2. keyword arguments ---------------------------------------------------
            for kw in node.keywords:
                if kw.arg is None:          # **kwargs, skip
                    continue
                formal = kw.arg
                if isinstance(kw.value, std_ast.Name):
                    actual_name = kw.value.id
                    if actual_name in self.var_class_map:
                        cls = self.var_class_map[actual_name]
                        callee_info["inferred_param_types"][formal] = cls

            for formal, actual in zip(callee_info['param_order'], node.args):
                if isinstance(actual, std_ast.Name):
                    actual_var = actual.id
                    if actual_var in self.var_class_map:
                        # stash this for a later pass
                        callee_info.setdefault('inferred_param_types', {})[formal] = self.var_class_map[actual_var]
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
        # logger.critical(call_name)
        # --- 1. direct match (free function or full path) ------------------
        fid, finfo = self.registry.get_function_by_name(call_name)
        if fid:
            return fid, finfo

        # --- 2. imported “from x import foo” -------------------------------
        if "." not in call_name and call_name in self.import_tracker.from_imports:
            mod   = self.import_tracker.from_imports[call_name]
            return self.registry.get_function_by_name(f"{mod}.{call_name}")

        # --- 3. same‑module optimisation ----------------------------------
        if "." not in call_name:
            fid, finfo = self.registry.get_function_by_name(f"{self.module_name}.{call_name}")
            if fid:
                return fid, finfo

        # --- 4. class constructor  (DemoApp()) -----------------------------
        simple_cls = call_name.split(".")[-1]
        fid, finfo = self.registry.get_constructor(simple_cls)
        if fid:                                 # we already found a ctor
            return fid, finfo

        # --- 5. instance‑method  (demo.run_demo  /  self.helper) ----------
        if "." in call_name:
            base, method_chain = call_name.split(".", 1)

            # (a) resolve what *base* refers to
            target_cls = (
                self.var_class_map.get(base)            # demo.run_demo
                if base not in {"self", "cls"}           # handled next
                else self.current_class                  # self.helper / cls.helper
            )

            if not target_cls:
                return None, None

            # (b) only the **first** attribute after the base is the method name
            method_name = method_chain.split(".", 1)[0]

            return self.registry.get_method(target_cls, method_name)

        # --- 6. suffix heuristic (“helpers.validate_input”) ---------------
        for fid, finfo in self.registry.functions.items():
            if finfo["full_name"].endswith(call_name):
                if finfo["module"] in self.import_tracker.imported_modules:
                    return fid, finfo

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
        # logger.warning(start_line)
        # logger.warning(end_line)
        # logger.warning(content)
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
    # logger.warning(f"{start_line=}, {end_line=}")
    
    # Extract the function's own lines (this is used later for tokenizing comments)
    function_lines = source_lines[start_line-1:end_line]  # 0 is def
    # logger.warning(f"{function_lines[-2:]=}")
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
    call_map = {call['lineno']: call for call in call_segments}

    
    # Build a mapping for standalone comments: only include if it is truly standalone.
    comment_map = {}
    for comment in all_comments:
        # if comment['is_standalone']:
        comment_map[comment['lineno']] = comment
    # print("comment_map")
    # print(comment_map)
    logger.info(f"{call_map=}, {comment_map=}, {relative_end_line=}")
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
    logger.info(f"{len(segments)} SEGMENTS IDENTIFIED")
    
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
                    segment_abs_start <= component['end_lineno']):
                    logger.info(f"attaching call to component: {segment=}")
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
                logger.info(f"attaching call to component: {segment=}")
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
                logger.warning(f"spliting segment across component: {segment=}")
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
            logger.warning(f"SEGMENT NOT ATTACHED: {segment=}")
            # segment.pop('component_id', None)  # Remove any existing component_id
            segment['component_id'] = func_components[0]['id']
            final_segments.append(segment)
    
    # Ensure segments are sorted by starting line number
    final_segments.sort(key=lambda seg: seg['lineno'])
    
    return final_segments

def build_registry(project_root):
    """
    Scan an entire project to build a function registry with all functions
        
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
    
    logger.info(f"Found {registry.functions} functions")
    return registry

def build_function_LLM_analysis(registry):
    # Second pass: Use LLM to analyze functions and extract components
    print("Second pass: Analyzing functions with LLM...")
    
    set_api_key(os.environ.get("DEEPSEEK_API_KEY"), provider="deepseek")
    set_api_key(os.environ.get("GROQ_API_KEY"), provider="groq")
    
    for func_id, func_info in registry.functions.items():
        # Get function source code
        file_path = func_info['file_path']
        # Extract function content from the file based on line numbers
        # Note: lineno and end_lineno are absolute (file-based) line numbers
        logger.info(f"{func_id}, {func_info}")
        func_content = extract_function_content(file_path, func_info['lineno'], func_info['end_lineno'])
        
        try:
            # Call LLM to analyze the function
            analysis = analyze_function(func_content, func_info['full_name'], provider="groq")
            logger.info(f"{analysis=}")
            # Store LLM-generated metadata in function info
            func_info['short_description'] = analysis['short_description']
            func_info['input_output_description'] = analysis['input_output_description']
            func_info['long_description'] = analysis['long_description']
            
            # Process components
            components = []
            for i, comp in enumerate(analysis['components']):
                logger.info(f"{comp=}")
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
    return registry
            
# def build_segments_helper(registry):
#     # Third pass: Analyze function calls and build segments
#     logger.info("Third pass: Analyzing function calls and building segments...")
#     for func_id, func_info in registry.functions.items():
#         file_path = func_info['file_path']
#         module_name = func_info['module']
        
        
#         # Skip if file doesn't exist
#         if not os.path.exists(file_path):
#             continue
        
#         # Read the source code
#         with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
#             source_lines = f.readlines()
            
#         # Extract function body for analysis
#         function_body_lines = source_lines[func_info['lineno']-1:func_info['end_lineno']]
#         function_body = ''.join(function_body_lines)
        
#         # If function body is empty or just pass, skip call analysis
#         if not function_body.strip() or re.match(r'\s*pass\s*', function_body.strip()):
#             continue
        
#         # Parse the function body to find calls
#         try:
#             dedented = textwrap.dedent(function_body)
#             tree = std_ast.parse(dedented)
                
#             analyzer = CallAnalyzer(registry, func_id, module_name, file_path, function_body_lines, func_info)
#             analyzer.visit(tree)
            
#             # Process segments
#             call_segments = analyzer.segments
#             if func_info['name'] == 'main': 
#                 logger.info(f"{func_info=}\n{analyzer.calls=}\n{analyzer.segments=}")
#                 logger.info(f"Seg: {call_segments}")
#             all_segments = extract_segments(file_path, func_info, call_segments)
            
#             # Add segments to the function
#             func_info["segments"] = []
#             for segment in all_segments:
#                 registry.add_segment(func_id, segment)
                        
#         except Exception as e:
#             print(f"Error analyzing function {func_info['full_name']}: {e}")
#             traceback.print_exc()
#     return registry


def propagate_types(registry, max_rounds=5):
    for _round in range(max_rounds):
        changed = False
        for fid, finfo in registry.functions.items():
            for name, cls in list(finfo["inferred_param_types"].items()):
                if name not in finfo["param_types"]:
                    finfo["param_types"][name] = cls
                    changed = True
            finfo["inferred_param_types"].clear()
        if not changed:
            break
    return registry

def build_segments_helper(registry, function_ids: Optional[List[str]] = None):
    """Analyze function calls and build segments for a subset of functions.

    Parameters
    ----------
    registry : FunctionRegistry
        The registry containing all discovered functions.
    function_ids : list[str] | None, default None
        If provided, only the functions whose IDs appear in this list will be
        analyzed.  When *None* (default) the helper behaves exactly as before
        and iterates over **all** functions in the registry.  This makes the
        helper 100 % backward‑compatible with existing callers.
    """
    logger.info("Third pass: Analyzing function calls and building segments…")

    # Decide which (id, info) pairs we will iterate over
    if function_ids is None:
        items: Iterable[Tuple[str, dict]] = registry.functions.items()
    else:
        items = ((fid, registry.functions[fid]) for fid in function_ids)

    for func_id, func_info in items:
        file_path = func_info['file_path']
        module_name = func_info['module']

        # Skip if file doesn't exist
        if not os.path.exists(file_path):
            continue

        # Read the source code
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source_lines = f.readlines()

        # Extract function body for analysis
        function_body_lines = source_lines[func_info['lineno'] - 1: func_info['end_lineno']]
        function_body = ''.join(function_body_lines)

        # If function body is empty or just pass, skip call analysis
        if not function_body.strip() or re.match(r'\s*pass\s*', function_body.strip()):
            continue

        # Parse the function body to find calls
        try:
            dedented = textwrap.dedent(function_body)
            tree = std_ast.parse(dedented)

            analyzer = CallAnalyzer(
                registry,
                func_id,
                module_name,
                file_path,
                function_body_lines,
                func_info,
            )
            analyzer.visit(tree)

            # Process segments
            call_segments = analyzer.segments
            all_segments = extract_segments(file_path, func_info, call_segments)

            # Replace old segments with freshly‑computed ones
            func_info["segments"] = []
            for segment in all_segments:
                registry.add_segment(func_id, segment)

        except Exception as e:
            logger.error(f"Error analyzing function {func_info['full_name']}: {e}")
            traceback.print_exc()

    return registry


def build_segments(registry, batch_size: int = 50):
    """High‑level wrapper that invokes *build_segments_helper* in batches.

    Parameters
    ----------
    registry : FunctionRegistry
        The registry produced by *build_registry* / *build_function_LLM_analysis*.
    batch_size : int, default 50
        How many functions to process in one batch before releasing any large
        temporary objects to Python's garbage collector in order to reduce peak
        memory usage.  Tune this number based on available RAM.

    Returns
    -------
    FunctionRegistry
        The same registry instance, now populated with *segments* and updated
        type information.

    Notes
    -----
    •  The public signature still begins with *registry* so existing call‑sites
       (e.g. `registry = build_segments(registry)`) continue to work without
       modification.
    •  Two full passes (matching the original behaviour) are still performed so
       that type‑propagation remains deterministic.  However, each pass is now
       split into smaller chunks controlled by *batch_size*.
    """
    function_ids: List[str] = list(registry.functions.keys())

    for _ in range(2):  # retain original two‑round logic
        for i in range(0, len(function_ids), batch_size):
            batch = function_ids[i : i + batch_size]
            registry = build_segments_helper(registry, batch)

        # After finishing one full sweep over all batches propagate any newly
        # inferred parameter types so that the second sweep can take advantage
        # of them.
        registry = propagate_types(registry)

    return registry

# def find_entry_points(registry, entry_files):
#     """
#     Find entry points in the registry based on a list of entry files
    
#     Args:
#         registry: FunctionRegistry object
#         entry_files: List of file paths to treat as entries, can include
#                      file_path:function_name format
        
#     Returns:
#         List of function IDs that are entry points
#     """
#     entry_points = []
    
#     for entry_spec in entry_files:
#         # Check if entry spec includes a function name
#         if ':' in entry_spec:
#             file_path, function_name = entry_spec.split(':', 1)
            
#             # Handle special case for __main__
#             if function_name == '__main__':
#                 for func_id, func_info in registry.functions.items():
#                     # Look for all functions in this file
#                     if os.path.basename(func_info['file_path']) == file_path:
#                         # Check if it's a main function or in a main block
#                         if (func_info['name'] == 'main' or 
#                             func_info['full_name'].endswith('.main') or
#                             '__main__' in func_info['full_name']):
#                             entry_points.append(func_id)
#                             print(f"Found entry point: {func_info['full_name']} (main)")
#             else:
#                 # Find the specific function in this file
#                 found = False
#                 for func_id, func_info in registry.functions.items():
#                     # Match by file name and function name
#                     rel_path = os.path.basename(func_info['file_path'])
#                     if rel_path == file_path or rel_path == os.path.basename(file_path):
#                         if (func_info['name'] == function_name or 
#                             func_info['full_name'].endswith(f'.{function_name}')):
#                             entry_points.append(func_id)
#                             print(f"Found entry point: {func_info['full_name']}")
#                             found = True
                
#                 if not found:
#                     print(f"Warning: Could not find function {function_name} in {file_path}")
#         else:
#             # Treat the whole file as an entry point
#             file_path = entry_spec
#             file_count = 0
            
#             for func_id, func_info in registry.functions.items():
#                 rel_path = os.path.basename(func_info['file_path'])
#                 if rel_path == file_path or rel_path == os.path.basename(file_path):
#                     entry_points.append(func_id)
#                     print(f"Found entry point: {func_info['full_name']}")
#                     file_count += 1
            
#             if file_count == 0:
#                 print(f"Warning: Could not find any functions in {file_path}")
    
#     return entry_points

# def build_tree_from_function(registry, function_id, max_depth=3, current_depth=0):
#     """
#     Build a tree from a function node with segments
    
#     Args:
#         registry: FunctionRegistry object
#         function_id: ID of the function to use as root
#         max_depth: Maximum depth of the tree (excluding segments)
#         current_depth: Current depth (for recursion)
        
#     Returns:
#         Tree structure
#     """
#     if current_depth > max_depth or function_id is None:
#         return None
    
#     # Get function info
#     func_info = registry.get_function_by_id(function_id)
#     if not func_info:
#         return None
    
#     # Create node for this function
#     node = {
#         'id': function_id,
#         'name': func_info['name'],
#         'full_name': func_info['full_name'],
#         'file_path': func_info['file_path'],
#         'segments': func_info['segments'],
#         'children': []
#     }
    
#     # Add callees as children
#     if current_depth < max_depth:
#         for callee_id in func_info['callees']:
#             child_node = build_tree_from_function(
#                 registry, callee_id, max_depth, current_depth + 1
#             )
#             if child_node:
#                 node['children'].append(child_node)
    
#     return node


# def print_tree(node, max_level=2, current_level=0, prefix=""):
#     """
#     Print a tree with levels
    
#     Args:
#         node: Tree node to print
#         max_level: Maximum level to print (0=root, 1=segments, 2=callee functions, etc.)
#         current_level: Current level (for recursion)
#         prefix: Prefix string for indentation
#     """
#     if node is None:
#         return
    
#     # Print the current node
#     print(f"{prefix}└── {node['name']} ({node['full_name']})")
    
#     # If we're at the max level, stop
#     if current_level >= max_level:
#         return
    
#     # Print segments at level 1
#     if current_level + 1 <= max_level and 'segments' in node:
#         segment_prefix = prefix + "    "
#         for i, segment in enumerate(node['segments']):
#             seg_type = segment['type']
#             content = segment['content']
            
#             # Shorten long content
#             if len(content) > 100:
#                 content = content[:97] + "..."
            
#             # Print segment
#             if seg_type == 'call' and 'callee_name' in segment:
#                 print(f"{segment_prefix}├── [CALL] {segment['callee_name']}: {content}")
#             else:
#                 print(f"{segment_prefix}├── [{seg_type.upper()}] {content}")
    
#     # Print children at level 2+
#     if current_level + 2 <= max_level and 'children' in node:
#         child_prefix = prefix + "    "
#         for child in node['children']:
#             print_tree(child, max_level, current_level + 2, child_prefix)


# def print_function_info(registry, function_id):
#     """
#     Print detailed information about a function
    
#     Args:
#         registry: FunctionRegistry object
#         function_id: ID of the function to print
#     """
#     func_info = registry.get_function_by_id(function_id)
#     if not func_info:
#         print(f"Function {function_id} not found")
#         return
    
#     print("=" * 60)
#     print(f"FUNCTION: {func_info['full_name']}")
#     print(f"ID: {function_id}")
#     print(f"File: {func_info['file_path']}")
#     print(f"Lines: {func_info['lineno']} - {func_info['end_lineno']}")
    
#     # Print callers
#     print("\nCALLERS:")
#     if func_info['callers']:
#         for caller_id in func_info['callers']:
#             caller = registry.get_function_by_id(caller_id)
#             if caller:
#                 print(f"  - {caller['full_name']}")
#     else:
#         print("  None")
    
#     # Print callees
#     print("\nCALLEES:")
#     if func_info['callees']:
#         for callee_id in func_info['callees']:
#             callee = registry.get_function_by_id(callee_id)
#             if callee:
#                 print(f"  - {callee['full_name']}")
#     else:
#         print("  None")
    
#     # Print segments
#     print("\nSEGMENTS:")
#     for i, segment in enumerate(func_info['segments']):
#         seg_type = segment['type']
#         content = segment['content']
#         print(f"\n  {i+1}. [{seg_type.upper()}]")
#         print(f"     Line: {segment['lineno']}")
#         if seg_type == 'call' and 'callee_name' in segment:
#             print(f"     Calls: {segment['callee_name']}")
#         print("-" * 40)
        
#         # Print the content with line numbers
#         lines = content.split('\n')
#         for j, line in enumerate(lines):
#             print(f"     {j+1:3d} | {line}")
    
#     print("=" * 60)


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