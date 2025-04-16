import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    CELERY_BROKER_URL = 'redis://localhost:6001/0'
    REPO_CACHE_DIR = os.environ.get('REPO_CACHE_DIR')
    MAX_ENTRY_POINTS = 10