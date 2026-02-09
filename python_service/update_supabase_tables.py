import psycopg
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("SUPABASE_DB_URL")

conn = psycopg.connect(db_url)
cursor = conn.cursor()

# Add phone_number column to whatsapp_auth table
cursor.execute("""
    ALTER TABLE whatsapp_auth 
    ADD COLUMN IF NOT EXISTS phone_number TEXT,
    ADD COLUMN IF NOT EXISTS connected_at TIMESTAMP;
""")

conn.commit()
print("✅ Table updated with phone_number tracking")

cursor.close()
conn.close()