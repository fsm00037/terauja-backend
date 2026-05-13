from database import engine
from sqlalchemy import text
import sqlite3
import os

print("--- Migrating PostgreSQL ---")
try:
    with engine.connect() as conn:
        try:
            conn.execute(text('ALTER TABLE aisuggestionlog ADD COLUMN models_used VARCHAR;'))
            conn.commit()
            print("Added 'models_used' to PostgreSQL")
        except Exception as e:
            conn.rollback()
            print(f"Skipped 'models_used' (might already exist): {e}")
            
        try:
            conn.execute(text('ALTER TABLE aisuggestionlog ADD COLUMN suggested_strategies VARCHAR;'))
            conn.commit()
            print("Added 'suggested_strategies' to PostgreSQL")
        except Exception as e:
            conn.rollback()
            print(f"Skipped 'suggested_strategies' (might already exist): {e}")
            
        try:
            conn.execute(text('ALTER TABLE aisuggestionlog ADD COLUMN selected_strategy VARCHAR;'))
            conn.commit()
            print("Added 'selected_strategy' to PostgreSQL")
        except Exception as e:
            conn.rollback()
            print(f"Skipped 'selected_strategy' (might already exist): {e}")
            
        try:
            conn.execute(text('ALTER TABLE aisuggestionlog ADD COLUMN parent_log_id INTEGER;'))
            conn.commit()
            print("Added 'parent_log_id' to PostgreSQL")
        except Exception as e:
            conn.rollback()
            print(f"Skipped 'parent_log_id' (might already exist): {e}")
except Exception as e:
    print(f"Error connecting to PostgreSQL: {e}")

print("\n--- Migrating SQLite ---")
db_path = 'psychology.db'
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute('ALTER TABLE aisuggestionlog ADD COLUMN models_used VARCHAR')
            print("Added 'models_used' to SQLite")
        except Exception as e:
            print(f"Skipped 'models_used' (might already exist): {e}")
            
        try:
            conn.execute('ALTER TABLE aisuggestionlog ADD COLUMN suggested_strategies VARCHAR')
            print("Added 'suggested_strategies' to SQLite")
        except Exception as e:
            print(f"Skipped 'suggested_strategies' (might already exist): {e}")
            
        try:
            conn.execute('ALTER TABLE aisuggestionlog ADD COLUMN selected_strategy VARCHAR')
            print("Added 'selected_strategy' to SQLite")
        except Exception as e:
            print(f"Skipped 'selected_strategy' (might already exist): {e}")
            
        try:
            conn.execute('ALTER TABLE aisuggestionlog ADD COLUMN parent_log_id INTEGER REFERENCES aisuggestionlog(id)')
            print("Added 'parent_log_id' to SQLite")
        except Exception as e:
            print(f"Skipped 'parent_log_id' (might already exist): {e}")
            
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error connecting to SQLite: {e}")
else:
    print(f"SQLite database not found at {db_path}")
