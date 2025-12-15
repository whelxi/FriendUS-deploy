import sqlite3

# Connect to the database
conn = sqlite3.connect('friendus.db')
cursor = conn.cursor()

try:
    # Run the SQL command to add the new column
    print("Attempting to add 'media_filename' column...")
    cursor.execute("ALTER TABLE post ADD COLUMN media_filename VARCHAR(100)")
    conn.commit()
    print("Success! Column added.")
except sqlite3.OperationalError as e:
    print(f"Error: {e}")
    print("The column might already exist, or the database is locked.")
finally:
    conn.close()