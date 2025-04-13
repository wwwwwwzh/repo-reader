from app import create_app, db
import os

# Override the database URL if needed
os.environ['DATABASE_URL'] = 'postgresql://codeuser:<code_password>@localhost/code'

app = create_app()

with app.app_context():
    # Create all database tables
    db.create_all()
    print("Database tables created.")