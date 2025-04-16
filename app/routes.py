from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, send_from_directory
from .models import Repository, Function, Segment, FunctionCall, FuncComponent
from sqlalchemy import func, desc
from . import db
import os

bp = Blueprint('main', __name__, url_prefix='/code')


@bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        repo_url = request.form['repo_url']
        entry_points = request.form.getlist('entry_points[]')
        
        # Validate input
        if not repo_url:
            return jsonify(error="Repository URL is required"), 400
        
        # Check if repository already exists
        existing_repo = Repository.query.filter_by(url=repo_url).first()
        if existing_repo:
            # Redirect to the existing repository tree view
            return jsonify(task_id="existing", repo_hash=existing_repo.id)
        
        # Import task here to avoid circular imports
        from .tasks import process_repo
        try:
            task = process_repo.delay(repo_url, entry_points)
            return jsonify(task_id=task.id)
        except Exception as e:
            current_app.logger.error(f"Error starting task: {str(e)}")
            return jsonify(error="Failed to process repository"), 500
    
    # Get all repositories for display
    repositories = Repository.query.order_by(Repository.parsed_at.desc()).all()
    return render_template('index.html', repositories=repositories)

@bp.route('/tree/<repo_hash>')
def show_tree(repo_hash):
    # Check if repository exists
    repo = Repository.query.get_or_404(repo_hash)
    
    # Get repository name from URL
    repo_name = repo.url.split('/')[-1]
    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]
    
    return render_template('tree.html', repo_hash=repo_hash, repo_name=repo_name, repo_url=repo.url)

@bp.route('/static/js/<path:filename>')
def serve_tree_js(filename):
    return send_from_directory(os.path.join(current_app.root_path, 'static/js'), filename)

@bp.route('/static/css/<path:filename>')
def css_files(filename):
    return send_from_directory(os.path.join(current_app.root_path, 'static/css'), filename)

@bp.route('/api/files/<repo_hash>')
def get_file_structure(repo_hash):
    """API endpoint to get the file structure of a repository"""
    # Get repository
    # repo = Repository.query.get_or_404(repo_hash)
    
    # Use your repo cache directory to walk the file system
    repos_dir = current_app.config.get('REPO_CACHE_DIR', '/tmp/repos')
    # repo_name = repo.url.split("/")[-1].replace(".git", "")
    repo_path = os.path.join(repos_dir, repo_hash)
    print(repo_path)
    # Build file structure
    file_structure = []
    for root, dirs, files in os.walk(repo_path):
        rel_path = os.path.relpath(root, repo_path)
        if rel_path != '.':
            file_structure.append({
                'path': rel_path,
                'is_dir': True
            })
        
        for file in files:
            if file.endswith('.py') or file.endswith('.js') or file.endswith('.html') or file.endswith('.css'):
                file_path = os.path.join(rel_path, file)
                if file_path.startswith('.'):
                    file_path = file_path[2:]
                file_structure.append({
                    'path': file_path,
                    'is_dir': False
                })
    
    return jsonify(file_structure)

@bp.route('/api/file', methods=['GET'])
def get_file_content():
    """
    API endpoint to get file content from a local repository
    
    Parameters:
    - path: Path to the file (relative or absolute)
    - repo_hash: Optional repository hash to locate the file in a specific repo
    - line_start: Optional starting line (1-indexed)
    - line_end: Optional ending line (1-indexed)
    
    Returns:
        File content as text
    """
    file_path = request.args.get('path')
    repo_hash = request.args.get('repo_hash')
    line_start = request.args.get('line_start', type=int)
    line_end = request.args.get('line_end', type=int)

    if not file_path:
        return jsonify({"error": "File path is required"}), 400
    
    try:
        # If repo_hash is provided, try to find the file in that repository
        if repo_hash:
            repo = Repository.query.get(repo_hash)
            if not repo:
                return jsonify({"error": f"Repository with hash {repo_hash} not found"}), 404
                
            # Use REPO_CACHE_DIR from config
            repos_dir = current_app.config.get('REPO_CACHE_DIR', '/tmp/repos')
            repo_name = repo.url.split("/")[-1].replace(".git", "")
            repo_path = os.path.join(repos_dir, repo_name)
            
            # Check if the file path is absolute
            if os.path.isabs(file_path):
                # Make sure it's within the repo path for security
                if not file_path.startswith(repo_path):
                    # Try to find the file in the repo by relative path
                    rel_path = os.path.basename(file_path)
                    for root, _, files in os.walk(repo_path):
                        if rel_path in files:
                            file_path = os.path.join(root, rel_path)
                            break
                    else:
                        # If we can't find the file by name, use the original path
                        # but make sure it's accessible
                        if not os.path.exists(file_path) or not os.access(file_path, os.R_OK):
                            return jsonify({"error": "File not found or not accessible"}), 404
            else:
                # If it's a relative path, join with repo path
                file_path = os.path.join(repo_path, file_path)
        
        # Security check: verify file exists and is readable
        if not os.path.exists(file_path) or not os.access(file_path, os.R_OK):
            return jsonify({"error": "File not found or not accessible"}), 404
            
        # Read the file content
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            if line_start and line_end:
                # Skip to the start line (1-indexed to 0-indexed)
                for _ in range(line_start - 1):
                    f.readline()
                
                # Read the requested lines
                lines = []
                for _ in range(line_end - line_start + 1):
                    line = f.readline()
                    if not line:  # EOF
                        break
                    lines.append(line)
                
                content = ''.join(lines)
            else:
                content = f.read()
                
        return content
            
    except Exception as e:
        current_app.logger.error(f"Error reading file: {str(e)}")
        return jsonify({"error": f"Error reading file: {str(e)}"}), 500
    
@bp.route('/api/functions/<repo_hash>/entries')
def get_entry_functions(repo_hash):
    """Get all entry point functions for a repository"""
    # Verify repository exists
    repo = Repository.query.get_or_404(repo_hash)
    
    # Get functions marked as entry points
    entry_functions = Function.query.filter_by(repo_id=repo_hash, is_entry=True).all()
    
    # If no specific entry points are marked, get functions from repository entry_points
    if not entry_functions and repo.entry_points:
        # Convert entry point IDs to full IDs with repo hash
        entry_point_ids = []
        for entry_id in repo.entry_points:
            if ":" not in entry_id:
                entry_point_ids.append(f"{repo_hash}:{entry_id}")
            else:
                entry_point_ids.append(entry_id)
        
        entry_functions = Function.query.filter(Function.id.in_(entry_point_ids)).all()
    
    # Return as JSON
    return jsonify([{
        'id': func.id,
        'name': func.name,
        'full_name': func.full_name,
        'file_path': func.file_path,
        'module_name': func.module_name,
        'is_entry': True
    } for func in entry_functions])

@bp.route('/api/functions/<repo_hash>/all')
def get_all_functions(repo_hash):
    """Get all functions for a repository"""
    # Verify repository exists
    repo = Repository.query.get_or_404(repo_hash)
    
    # Get all functions for this repository
    functions = Function.query.filter_by(repo_id=repo_hash).all()
    
    # Return as JSON
    return jsonify([{
        'id': func.id,
        'name': func.name,
        'full_name': func.full_name,
        'file_path': func.file_path,
        'module_name': func.module_name,
        'is_entry': func.is_entry,
        'short_description': func.short_description
    } for func in functions])
        
@bp.route('/api/functions/<repo_hash>/<function_id>')
def get_function_details(repo_hash, function_id):
    """Get detailed information about a function including its segments"""
    # Handle case when function_id doesn't have repo_hash prefix
    if ":" not in function_id:
        full_function_id = f"{repo_hash}:{function_id}"
    else:
        full_function_id = function_id
    
    # Get function
    function = Function.query.get_or_404(full_function_id)
    
    # Get all segments for this function
    segments = Segment.query.filter_by(function_id=full_function_id).order_by(Segment.index).all()
    
    # Prepare segments data
    segments_data = []
    for segment in segments:
        segment_data = {
            'id': segment.id,
            'type': segment.type,
            'content': segment.content,
            'lineno': segment.lineno,
            'end_lineno': segment.end_lineno,
            'index': segment.index,
            'func_component_id': segment.func_component_id
        }
        
        # Add target function info for call segments
        if segment.type == 'call' and segment.target_id:
            target = Function.query.get(segment.target_id)
            if target:
                segment_data['target_function'] = {
                    'id': target.id,
                    'name': target.name,
                    'full_name': target.full_name,
                    'file_path': target.file_path,
                    'lineno': target.lineno,
                    'end_lineno': target.end_lineno,
                    'class_name': target.class_name,
                    'module_name': target.module_name
                }
        
        segments_data.append(segment_data)
    
    # Prepare function data
    function_data = {
        'id': function.id,
        'name': function.name,
        'full_name': function.full_name,
        'file_path': function.file_path,
        'lineno': function.lineno,
        'end_lineno': function.end_lineno,
        'is_entry': function.is_entry,
        'class_name': function.class_name,
        'module_name': function.module_name,
        'short_description': function.short_description,
        'input_output_description': function.input_output_description,
        'long_description': function.long_description,
        'segments': segments_data
    }
    
    return jsonify(function_data)

@bp.route('/api/functions/<repo_hash>/<function_id>/components')
def get_function_components(repo_hash, function_id):
    """Get all components for a function"""
    # Handle case when function_id doesn't have repo_hash prefix
    if ":" not in function_id:
        full_function_id = f"{repo_hash}:{function_id}"
    else:
        full_function_id = function_id
    
    # Get function
    function = Function.query.get_or_404(full_function_id)
    
    # Get all components for this function
    components = FuncComponent.query.filter_by(function_id=full_function_id).order_by(FuncComponent.index).all()
    
    # Prepare components data
    components_data = []
    for component in components:
        component_data = {
            'id': component.id,
            'name': component.name,
            'short_description': component.short_description,
            'long_description': component.long_description,
            'start_lineno': component.start_lineno,
            'end_lineno': component.end_lineno,
            'index': component.index
        }
        
        components_data.append(component_data)
    
    return jsonify(components_data)

@bp.route('/api/functions/<repo_hash>/<function_id>/callees')
def get_function_callees(repo_hash, function_id):
    """Get all functions called by this function"""
    # Handle case when function_id doesn't have repo_hash prefix
    if ":" not in function_id:
        full_function_id = f"{repo_hash}:{function_id}"
    else:
        full_function_id = function_id
    
    # Get function
    function = Function.query.get_or_404(full_function_id)
    
    # Query function calls
    callees = db.session.query(Function).join(
        FunctionCall, Function.id == FunctionCall.callee_id
    ).filter(
        FunctionCall.caller_id == full_function_id
    ).all()
    
    # Return as JSON
    return jsonify([{
        'id': func.id,
        'name': func.name,
        'full_name': func.full_name,
        'file_path': func.file_path,
        'module_name': func.module_name
    } for func in callees])

@bp.route('/api/repositories')
def get_repositories():
    """API endpoint to get all repositories"""
    repositories = Repository.query.order_by(Repository.parsed_at.desc()).all()
    return jsonify([{
        'id': repo.id,
        'url': repo.url,
        'parsed_at': repo.parsed_at.isoformat() if repo.parsed_at else None,
        'name': repo.url.split('/')[-1].replace('.git', '')
    } for repo in repositories])

@bp.route('/api/repository/<repo_hash>')
def get_repository_info(repo_hash):
    """Get detailed information about a repository"""
    repo = Repository.query.get_or_404(repo_hash)
    
    # Count functions for this repository
    function_count = Function.query.filter_by(repo_id=repo_hash).count()
    
    # Get entry points if available
    entry_points = repo.entry_points if repo.entry_points else []
    
    return jsonify({
        'id': repo.id,
        'url': repo.url,
        'parsed_at': repo.parsed_at.isoformat() if repo.parsed_at else None,
        'entry_points': entry_points,
        'function_count': function_count,
        'name': repo.url.split('/')[-1].replace('.git', '')
    })