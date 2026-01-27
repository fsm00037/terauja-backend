import sqlite3
import os

def migrate():
    db_path = "psychology.db"
    
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    tables = [
        "psychologist", "patient", "questionnaire", "assignment", 
        "questionnairecompletion", "session", "assessmentstat", 
        "note", "message", "aisuggestionlog", "auditlog", 
        "pushsubscription"
    ]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for table in tables:
        try:
            print(f"Adding deleted_at to {table}...")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TIMESTAMP;")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column deleted_at already exists in {table}.")
            else:
                print(f"Error updating table {table}: {e}")
    
    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
