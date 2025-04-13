import sys
import os

# Add the application directory to Python path
sys.path.insert(0, '/home/webadmin/projects/code')

from app import create_app

application = create_app()
application.config['APPLICATION_ROOT'] = '/code'

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5000)