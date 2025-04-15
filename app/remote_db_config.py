# remote_db_config.py
# import os

# class Config:
#     # PostgreSQL connection for remote hosting server
#     REMOTE_DB_HOST = os.environ.get('REMOTE_DB_HOST', '159.223.132.83')
#     REMOTE_DB_PORT = os.environ.get('REMOTE_DB_PORT', '5432')
#     REMOTE_DB_USER = os.environ.get('REMOTE_DB_USER', 'codeuser')
#     REMOTE_DB_PASS = os.environ.get('REMOTE_DB_PASS', '<code_password>')
#     REMOTE_DB_NAME = os.environ.get('REMOTE_DB_NAME', 'code')
    
#     # Construct the SQLAlchemy URI
#     REMOTE_SQLALCHEMY_DATABASE_URI = f"postgresql://{REMOTE_DB_USER}:{REMOTE_DB_PASS}@{REMOTE_DB_HOST}:{REMOTE_DB_PORT}/{REMOTE_DB_NAME}"
    
#     # Local file storage path
#     REPO_CACHE_DIR = '/tmp/repos'
#     MAX_ENTRY_POINTS = 10