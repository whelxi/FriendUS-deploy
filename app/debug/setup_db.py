import sys
import os
import sqlite3

# --- 1. FIX IMPORTS ---
# Get the directory where this script is located (app/debug)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up two levels to reach the project root (FriendUS/)
project_root = os.path.abspath(os.path.join(current_dir, '../../'))
# Add the root to sys.path so Python can find the 'app' package
sys.path.append(project_root)

# Now we can import from app
from app import app, db

print(f"--- Running setup from root: {project_root} ---")

# --- 2. CREATE MISSING TABLES ---
print("\n--- Checking/Creating missing tables... ---")
with app.app_context():
    db.create_all()
    print("Tables checked.")

# --- 3. UPDATE EXISTING TABLES ---
print("\n--- Updating existing tables... ---")

# Use the absolute path to ensure we edit the correct database file in the root
db_path = os.path.join(project_root, 'friendus.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List of updates needed
updates = [
    # Table Name,   Column Name,      Definition
    ('transaction', 'room_id',       'INTEGER REFERENCES room(id)'),
    ('transaction', 'outsider_id',   'INTEGER REFERENCES outsider(id)'),
    ('transaction', 'receiver_id',   'INTEGER REFERENCES user(id)'),
    ('post',        'media_filename','VARCHAR(100)'),
    ('user',        'image_file',    "VARCHAR(20) NOT NULL DEFAULT 'default.jpg'")
]

for table, col, definition in updates:
    try:
        print(f"Attempting to add '{col}' to '{table}'...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        print(f" -> Success: Added {col}")
    except sqlite3.OperationalError as e:
        if "duplicate" in str(e):
            print(f" -> Skipped: {col} already exists.")
        else:
            print(f" -> Note: {e}")

conn.commit()
conn.close()
print("\nDatabase update complete! You can now run app.py.")