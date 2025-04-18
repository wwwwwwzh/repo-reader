import sys
import os
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
# print(f"[wsgi] looking for .env at: {dotenv_path!r}")
# print(f"[wsgi] exists? {os.path.exists(dotenv_path)}")

# print("[wsgi] raw dotenv values:", dotenv_values(dotenv_path))
load_dotenv(dotenv_path, override=True)
# print("[wsgi] after load_dotenv, DATABASE_URL =", os.getenv("DATABASE_URL"))



# Add the application directory to Python path
sys.path.insert(0, '/home/webadmin/projects/code')

from app import create_app

application = create_app("")
application.config['APPLICATION_ROOT'] = '/code'

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5000)