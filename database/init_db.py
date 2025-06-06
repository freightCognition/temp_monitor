import sqlite3
import sys
import os

# Add src directory to Python path to import database module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.database import get_db_connection, create_tables, DATABASE_PATH, log_system_event

def initialize_database():
    """Initializes the database by creating tables if they don't exist."""
    print(f"Attempting to initialize database at: {DATABASE_PATH}")
    try:
        # The get_db_connection itself might create the file if it doesn't exist,
        # but create_tables handles the schema.
        with get_db_connection() as conn:
            create_tables(conn) # Ensures tables are created
        print("Database initialization successful. Tables are ready.")
        log_system_event("DATABASE_INIT", "Database initialized successfully.", "info")
        return True
    except sqlite3.Error as e:
        print(f"Failed to initialize database: {e}")
        # Optionally log to a file if DB logging isn't up yet
        return False
    except Exception as ex:
        print(f"An unexpected error occurred during database initialization: {ex}")
        return False

if __name__ == '__main__':
    print("Starting database initialization script...")
    if initialize_database():
        print("Script finished: Database initialized.")
    else:
        print("Script finished: Database initialization FAILED.")
