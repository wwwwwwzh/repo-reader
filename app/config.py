import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://codeuser:<code_password>@localhost/code')
    CELERY_BROKER_URL = 'redis://localhost:6001/0'
    REPO_CACHE_DIR = '/home/webadmin/projects/code/repos'
    MAX_ENTRY_POINTS = 10