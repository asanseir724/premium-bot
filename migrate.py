from app import app, db
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# Add new columns to AdminUser model
with app.app_context():
    try:
        # Check if column exists first
        conn = db.engine.connect()
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='admin_user' AND column_name='api_key_hash'"))
        if result.rowcount == 0:
            print("Adding api_key_hash column to admin_user table...")
            conn.execute(text("ALTER TABLE admin_user ADD COLUMN api_key_hash VARCHAR(256)"))
            conn.commit()
            print("Added api_key_hash column successfully!")
        else:
            print("Column api_key_hash already exists in admin_user table.")

        # Add updated_at column if it doesn't exist
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='admin_user' AND column_name='updated_at'"))
        if result.rowcount == 0:
            print("Adding updated_at column to admin_user table...")
            conn.execute(text("ALTER TABLE admin_user ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()"))
            conn.commit()
            print("Added updated_at column successfully!")
        else:
            print("Column updated_at already exists in admin_user table.")
            
        conn.close()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")