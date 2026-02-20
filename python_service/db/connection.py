"""
Database connection helper
"""

import os
import psycopg


def get_db_connection():
    """Get a Supabase PostgreSQL connection"""
    db_url = os.getenv("SUPABASE_DB_URL")
    return psycopg.connect(db_url)