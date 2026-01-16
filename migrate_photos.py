import sqlite3

def migrate():
    conn = sqlite3.connect("psychology.db")
    cursor = conn.cursor()
    
    # Add photo_url to psychologist table
    try:
        cursor.execute("ALTER TABLE psychologist ADD COLUMN photo_url VARCHAR")
        print("Added photo_url to psychologist table")
    except sqlite3.OperationalError as e:
        print(f"Psychologist table update skipped: {e}")

    # Add psychologist_photo to patient table
    try:
        cursor.execute("ALTER TABLE patient ADD COLUMN psychologist_photo VARCHAR")
        print("Added psychologist_photo to patient table")
    except sqlite3.OperationalError as e:
        print(f"Patient table update skipped: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
