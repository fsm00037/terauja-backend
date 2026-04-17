"""
Migration script to add IA patient fields to the Patient table.
Run this once to add the new columns.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "psychology.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(patient)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "is_ia_patient" not in columns:
        print("Adding is_ia_patient column...")
        cursor.execute("ALTER TABLE patient ADD COLUMN is_ia_patient BOOLEAN DEFAULT 0")
    else:
        print("is_ia_patient column already exists")
    
    if "ia_patient_prompt" not in columns:
        print("Adding ia_patient_prompt column...")
        cursor.execute("ALTER TABLE patient ADD COLUMN ia_patient_prompt TEXT DEFAULT NULL")
    else:
        print("ia_patient_prompt column already exists")
    
    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
