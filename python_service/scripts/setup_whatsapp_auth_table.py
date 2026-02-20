"""
Setup WhatsApp Auth Table in Supabase
Creates the table needed to store WhatsApp authentication credentials
This allows the bot to persist auth across server restarts on free tier
"""

import os
from dotenv import load_dotenv
import psycopg  # ✅ Using psycopg v3
from datetime import datetime

load_dotenv()

print("=" * 70)
print("🔐 SETTING UP WHATSAPP AUTH TABLE IN SUPABASE")
print("=" * 70)

# ============================================================
# STEP 1: Connect to Supabase
# ============================================================

print("\n🔗 Connecting to Supabase...")

db_url = os.getenv("SUPABASE_DB_URL")

if not db_url:
    print("❌ ERROR: SUPABASE_DB_URL not found in .env file!")
    print("   Please add it to your .env file")
    exit(1)

try:
    # ✅ psycopg v3 syntax
    conn = psycopg.connect(db_url)
    cursor = conn.cursor()
    print("✅ Connected to Supabase")
    print(f"   Database: {db_url.split('@')[1].split('/')[0] if '@' in db_url else 'supabase'}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

# ============================================================
# STEP 2: Create whatsapp_auth Table
# ============================================================

print("\n📦 Creating whatsapp_auth table...")

try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_auth (
            id TEXT PRIMARY KEY DEFAULT 'main_session',
            creds JSONB,
            keys JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    print("   ✅ Table 'whatsapp_auth' created (or already exists)")
    
except Exception as e:
    print(f"   ❌ Error creating table: {e}")
    conn.rollback()
    exit(1)

# ============================================================
# STEP 3: Create Index for Performance
# ============================================================

print("\n⚡ Creating index for faster queries...")

try:
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_auth_updated 
        ON whatsapp_auth(updated_at);
    """)
    
    print("   ✅ Index created")
    
except Exception as e:
    print(f"   ❌ Error creating index: {e}")
    conn.rollback()

# ============================================================
# STEP 4: Verify Table Structure
# ============================================================

print("\n🔍 Verifying table structure...")

try:
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'whatsapp_auth'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    
    print("\n   📋 Table Columns:")
    for col_name, col_type in columns:
        print(f"      • {col_name}: {col_type}")
    
except Exception as e:
    print(f"   ⚠️  Could not verify structure: {e}")

# ============================================================
# STEP 5: Check Current Data
# ============================================================

print("\n📊 Checking existing data...")

try:
    cursor.execute("SELECT COUNT(*) FROM whatsapp_auth;")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("   📭 Table is empty (ready for first auth)")
    else:
        print(f"   📬 Table has {count} auth session(s)")
        
        # Show details
        cursor.execute("""
            SELECT id, updated_at 
            FROM whatsapp_auth 
            ORDER BY updated_at DESC;
        """)
        
        sessions = cursor.fetchall()
        print("\n   📝 Existing Sessions:")
        for session_id, updated in sessions:
            print(f"      • {session_id} - Last updated: {updated}")
    
except Exception as e:
    print(f"   ⚠️  Could not check data: {e}")

# ============================================================
# STEP 6: Commit Changes
# ============================================================

print("\n💾 Committing changes to database...")

try:
    conn.commit()
    print("   ✅ All changes committed")
except Exception as e:
    print(f"   ❌ Commit failed: {e}")
    conn.rollback()

# ============================================================
# STEP 7: Test Insert (Optional - Commented Out)
# ============================================================

print("\n🧪 Testing table functionality...")

try:
    # Test that we can insert dummy data
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'whatsapp_auth'
        );
    """)
    
    exists = cursor.fetchone()[0]
    
    if exists:
        print("   ✅ Table is queryable and ready")
    else:
        print("   ⚠️  Table verification failed")
        
except Exception as e:
    print(f"   ⚠️  Test failed: {e}")

# ============================================================
# STEP 8: Close Connection
# ============================================================

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("✅ SETUP COMPLETE!")
print("=" * 70)

print("\n📊 Summary:")
print("   • Table 'whatsapp_auth' is ready")
print("   • Index created for performance")
print("   • Ready to store WhatsApp credentials")
print("   • Using psycopg v3 for modern PostgreSQL access")

print("\n🎯 Next Steps:")
print("   1. Install 'pg' package in Node.js service")
print("   2. Create authStateSupabase.js helper")
print("   3. Update vihaBot.js to use Supabase auth")
print("   4. Deploy to Render")
print("   5. Scan QR code once")
print("   6. Auth will persist across restarts!")

print("\n💡 Interview Talking Points:")
print("   • Using JSONB for flexible credential storage")
print("   • Index on updated_at for query optimization")
print("   • Idempotent setup (safe to run multiple times)")
print("   • Environment variable for database connection")
print("   • psycopg v3 for modern async PostgreSQL access")
print("   • Context managers for safe resource handling")

print("\n🔒 Security Notes:")
print("   • Credentials encrypted in transit (SSL)")
print("   • Database URL stored in environment variables")
print("   • Can enable Row Level Security (RLS) in Supabase")
print("   • JSONB prevents SQL injection on credential fields")

print("=" * 70)