"""
create_leads_table.py
Run this ONCE to create the leads table in Supabase.
Usage: python create_leads_table.py
"""

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def create_leads_table():
    db_url = os.getenv("SUPABASE_DB_URL")
    
    if not db_url:
        print("❌ SUPABASE_DB_URL not found in environment variables")
        print("   Make sure your .env file has SUPABASE_DB_URL set")
        return False
    
    try:
        print("🔄 Connecting to Supabase...")
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cursor:
                print("✅ Connected!")

                # ─────────────────────────────────────────
                # CREATE leads table
                # ─────────────────────────────────────────
                print("\n🔄 Creating leads table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS leads (
                        id                SERIAL PRIMARY KEY,
                        customer_number   TEXT NOT NULL,
                        quantity          INTEGER,
                        budget_per_piece  NUMERIC,
                        location          TEXT,
                        timeline          TEXT,
                        status            TEXT DEFAULT 'new',
                        last_message      TEXT,
                        created_at        TIMESTAMP DEFAULT NOW(),
                        updated_at        TIMESTAMP DEFAULT NOW()
                    );
                """)
                print("✅ leads table created!")

                # ─────────────────────────────────────────
                # CREATE indexes for fast querying
                # ─────────────────────────────────────────
                print("\n🔄 Creating indexes...")

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leads_customer 
                    ON leads(customer_number);
                """)
                print("✅ Index: customer_number")

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leads_created 
                    ON leads(created_at);
                """)
                print("✅ Index: created_at")

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leads_status 
                    ON leads(status);
                """)
                print("✅ Index: status")

                # ─────────────────────────────────────────
                # CREATE auto-update trigger for updated_at
                # ─────────────────────────────────────────
                print("\n🔄 Creating auto-update trigger for updated_at...")

                cursor.execute("""
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = NOW();
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql';
                """)

                cursor.execute("""
                    DROP TRIGGER IF EXISTS update_leads_updated_at ON leads;
                """)

                cursor.execute("""
                    CREATE TRIGGER update_leads_updated_at
                        BEFORE UPDATE ON leads
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column();
                """)
                print("✅ Auto-update trigger created!")

                # ─────────────────────────────────────────
                # COMMIT
                # ─────────────────────────────────────────
                conn.commit()

        print("\n" + "="*50)
        print("🎉 ALL DONE! leads table is ready.")
        print("="*50)
        print("\nTable columns:")
        print("  id               - Auto increment")
        print("  customer_number  - WhatsApp number")
        print("  quantity         - Pieces required")
        print("  budget_per_piece - Budget in ₹")
        print("  location         - Delivery location")
        print("  timeline         - When needed")
        print("  status           - new / requirements_collecting /")
        print("                     products_shown / locked / follow_up")
        print("  last_message     - Last message from customer")
        print("  created_at       - When lead was created")
        print("  updated_at       - Last activity (auto-updates)")
        print("\nNext step: Update bot_api.py to save leads automatically")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check SUPABASE_DB_URL in your .env file")
        print("  2. Make sure psycopg is installed: pip install psycopg")
        print("  3. Make sure Supabase project is active")
        return False


if __name__ == "__main__":
    create_leads_table()