import sqlite3
import os

def migrate():
    db_path = "psychology.db"
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        # Try finding it in the parent directory just in case
        if os.path.exists("../psychology.db"):
            db_path = "../psychology.db"
        else:
            print("Could not locate psychology.db")
            return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print(f"Adding 'clinical_log' column to 'patient' table in {db_path}...")
        cursor.execute("ALTER TABLE patient ADD COLUMN clinical_log TEXT;")
        conn.commit()
        print("Migration successful: column 'clinical_log' added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e) or "already exists" in str(e).lower():
            print("Column 'clinical_log' already exists. No changes needed.")
        else:
            print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
