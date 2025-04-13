from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for,send_from_directory
from .models import Repository, Function, Segment, FunctionCall
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

@bp.route('/function-tree/<repo_hash>')
def show_function_tree(repo_hash):
    """Display the function tree view for a repository"""
    # Check if repository exists
    repo = Repository.query.get_or_404(repo_hash)
    
    # Get repository name from URL
    repo_name = repo.url.split('/')[-1]
    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]
    
    return render_template('function_tree.html', repo_hash=repo_hash, repo_name=repo_name, repo_url=repo.url)

@bp.route('/static/js/tree.js')
def serve_tree_js():
    return send_from_directory(os.path.join(current_app.root_path, 'static/js'), 'tree.js')

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
            'index': segment.index
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
        'segments': segments_data
    }
    
    return jsonify(function_data)

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