from flask import Flask, url_for
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
import os
from dotenv import load_dotenv, dotenv_values
dotenv_path = "/home/webadmin/projects/code/.env"
# print(f"[wsgi] looking for .env at: {dotenv_path!r}")
# print(f"[wsgi] exists? {os.path.exists(dotenv_path)}")

# print("[wsgi] raw dotenv values:", dotenv_values(dotenv_path))
load_dotenv(dotenv_path, override=True)

db = SQLAlchemy()
celery = Celery()

def create_app(url_prefix="/code"):
    app = Flask(__name__, static_folder='static')
    app.config.from_object('app.config.Config')
    
    # Override database URL from environment if available
    # print(os.environ)
    if 'DATABASE_URL' in os.environ:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    
    db.init_app(app)
    
    # Configure Celery
    celery.conf.update(app.config)
    
    # Register blueprint with URL prefix if APPLICATION_ROOT is set
    from .routes import bp
    bp.url_prefix = url_prefix
    app.register_blueprint(bp)
    # print("🔍 Flask URL map:\n%s", app.url_map)
    # app_root = app.config.get('APPLICATION_ROOT', '')
    # if app_root:
    #     app.register_blueprint(bp, url_prefix=app_root)
    # else:
    #     app.register_blueprint(bp)
    
    # Add URL processor to handle the application root path in templates
    @app.context_processor
    def override_url_for():
        return dict(url_for=_generate_url_for_with_app_root)
    
    def _generate_url_for_with_app_root(*args, **kwargs):
        app_root = app.config.get('APPLICATION_ROOT', '')
        if app_root:
            # Only handle 'static' endpoint specially
            if args and args[0] == 'static':
                kwargs['_external'] = False
                return app_root + url_for(*args, **kwargs)
        return url_for(*args, **kwargs)
    
    return app