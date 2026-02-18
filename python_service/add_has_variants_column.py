"""
Add has_variants column to products table
"""

import os
from dotenv import load_dotenv
import psycopg

load_dotenv()

print("=" * 70)
print("🔧 ADDING has_variants COLUMN TO PRODUCTS TABLE")
print("=" * 70)

db_url = os.getenv("SUPABASE_DB_URL")
conn = psycopg.connect(db_url)
cursor = conn.cursor()

print("\n✅ Connected to Supabase")

# Add has_variants column
print("\n📝 Adding has_variants column...")

try:
    cursor.execute("""
        ALTER TABLE products 
        ADD COLUMN IF NOT EXISTS has_variants BOOLEAN DEFAULT FALSE;
    """)
    
    print("   ✅ has_variants column added")
    
except Exception as e:
    print(f"   ⚠️  Column might already exist: {e}")

# Commit
conn.commit()

# Verify
cursor.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'products' 
    ORDER BY ordinal_position;
""")

print("\n📊 Current products table columns:")
for col_name, col_type in cursor.fetchall():
    print(f"   • {col_name}: {col_type}")

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("✅ COLUMN ADDED SUCCESSFULLY!")
print("=" * 70)
print("\n🎯 Next step: Run migrate_products_to_supabase_v2.py")
print("=" * 70)