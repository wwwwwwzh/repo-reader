# from . import create_app, db, celery
# from .models import Repository, Function, Segment, FunctionCall
# from ..utils.git_manager import GitManager
# import os
# from dulwich.repo import Repo
# import sys
# import logging
# import datetime

# # Import AST parser
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# try:
#     from app.utils.ast_parser import scan_project, find_entry_points
# except ImportError:
#     # For standalone running, import from the current directory
#     from utils.ast_parser import scan_project, find_entry_points

# app = create_app()

# @celery.task
# def process_repo(repo_url, entry_points):
#     with app.app_context():
#         try:
#             logging.info(f"Processing repository: {repo_url} with entry points: {entry_points}")
            
#             # Clone repo and get commit hash
#             git_manager = GitManager()
#             repo, repo_path = git_manager.clone(repo_url)
            
#             # Get repository's HEAD commit hash
#             repo_hash = repo.head().decode('utf-8')
            
#             # Scan project and build function registry
#             logging.info(f"Scanning project at {repo_path}")
#             registry = scan_project(repo_path)
#             logging.info(f"Found {len(registry.functions)} functions")
            
#             # Find entry point functions
#             entry_point_ids = []
#             if entry_points:
#                 entry_point_ids = find_entry_points(registry, entry_points)
#                 logging.info(f"Identified {len(entry_point_ids)} entry points: {entry_point_ids}")
            
#             # Create or update repository record
#             repo_record = Repository.query.get(repo_hash)
#             if not repo_record:
#                 repo_record = Repository(
#                     id=repo_hash,
#                     url=repo_url,
#                     entry_points=entry_point_ids,
#                     parsed_at=datetime.datetime.now()
#                 )
#                 db.session.add(repo_record)
#             else:
#                 repo_record.url = repo_url
#                 repo_record.entry_points = entry_point_ids
#                 repo_record.parsed_at = datetime.datetime.now()
            
#             db.session.commit()
            
#             # Process functions
#             function_count = 0
#             for func_id, func_info in registry.functions.items():
#                 # Create database ID by combining repo hash and function ID
#                 db_func_id = f"{repo_hash}:{func_id}"
                
#                 # Check if function is an entry point
#                 is_entry = func_id in entry_point_ids
                
#                 # Create or update function record
#                 func_record = Function.query.get(db_func_id)
#                 if func_record:
#                     # Update existing function
#                     func_record.name = func_info['name']
#                     func_record.full_name = func_info['full_name']
#                     func_record.file_path = func_info['file_path']
#                     func_record.lineno = func_info['lineno']
#                     func_record.end_lineno = func_info['end_lineno']
#                     func_record.is_entry = is_entry
#                     func_record.class_name = func_info.get('class_name')
#                     func_record.module_name = func_info['module']
#                 else:
#                     # Create new function record
#                     func_record = Function(
#                         id=db_func_id,
#                         repo_id=repo_hash,
#                         name=func_info['name'],
#                         full_name=func_info['full_name'],
#                         file_path=func_info['file_path'],
#                         lineno=func_info['lineno'],
#                         end_lineno=func_info['end_lineno'],
#                         is_entry=is_entry,
#                         class_name=func_info.get('class_name'),
#                         module_name=func_info['module']
#                     )
#                     db.session.add(func_record)
                
#                 function_count += 1
                
#                 # Commit every 50 functions to avoid overwhelming the database
#                 if function_count % 50 == 0:
#                     db.session.commit()
            
#             # Commit all functions
#             db.session.commit()
            
#             # Process segments
#             segment_count = 0
#             for func_id, func_info in registry.functions.items():
#                 db_func_id = f"{repo_hash}:{func_id}"
                
#                 # First delete existing segments for this function
#                 Segment.query.filter_by(function_id=db_func_id).delete()
                
#                 # Add segments
#                 for i, segment in enumerate(func_info.get('segments', [])):
#                     segment_id = f"{db_func_id}_segment_{i}"
#                     segment_type = segment['type']
                    
#                     # For call segments, set the target ID
#                     target_id = None
#                     if segment_type == 'call' and 'callee_id' in segment:
#                         target_id = f"{repo_hash}:{segment['callee_id']}"
                    
#                     # Create segment record
#                     segment_record = Segment(
#                         id=segment_id,
#                         function_id=db_func_id,
#                         type=segment_type,
#                         content=segment['content'],
#                         lineno=segment['lineno'],
#                         end_lineno=segment.get('end_lineno'),
#                         index=i,
#                         target_id=target_id,
#                         segment_data={
#                             'callee_name': segment.get('callee_name'),
#                             'is_standalone': segment.get('is_standalone', True)
#                         } if segment_type in ['call', 'comment'] else None
#                     )
#                     db.session.add(segment_record)
                    
#                     segment_count += 1
                    
#                     # Commit every 100 segments
#                     if segment_count % 100 == 0:
#                         db.session.commit()
            
#             # Commit all segments
#             db.session.commit()
            
#             # Process function calls
#             for func_id, func_info in registry.functions.items():
#                 db_func_id = f"{repo_hash}:{func_id}"
                
#                 # First delete existing call relationships for this function
#                 FunctionCall.query.filter_by(caller_id=db_func_id).delete()
                
#                 # Add call relationships
#                 for callee_id in func_info.get('callees', []):
#                     db_callee_id = f"{repo_hash}:{callee_id}"
                    
#                     # Create call record
#                     call_record = FunctionCall(
#                         caller_id=db_func_id,
#                         callee_id=db_callee_id,
#                         call_count=1  # We could enhance this by counting actual calls
#                     )
#                     db.session.add(call_record)
            
#             # Final commit for all call relationships
#             db.session.commit()
            
#             logging.info(f"Successfully processed repository {repo_url}")
#             return repo_hash
            
#         except Exception as e:
#             db.session.rollback()
#             logging.error(f"Error processing repo: {str(e)}", exc_info=True)
#             app.logger.error(f"Error processing repo: {str(e)}")
#             raise