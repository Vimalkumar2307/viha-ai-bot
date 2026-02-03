"""
Setup Supabase Database Tables
Creates all tables needed for the Viha bot
"""

import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

print("=" * 70)
print("🏗️  CREATING SUPABASE DATABASE TABLES")
print("=" * 70)

# Get connection
db_url = os.getenv("SUPABASE_DB_URL")
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

print("\n✅ Connected to Supabase")

# ============================================================
# TABLE 1: PRODUCTS
# ============================================================

print("\n📦 Creating 'products' table...")

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    image_url TEXT,
    min_order INTEGER,
    special_rule TEXT,
    unit TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
""")

print("   ✅ Products table created")

# ============================================================
# TABLE 2: PRICING TIERS
# ============================================================

print("\n💰 Creating 'pricing_tiers' table...")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pricing_tiers (
    id SERIAL PRIMARY KEY,
    product_id TEXT REFERENCES products(id) ON DELETE CASCADE,
    quantity_range TEXT NOT NULL,
    price_per_piece INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

print("   ✅ Pricing tiers table created")

# ============================================================
# TABLE 3: PRODUCT EMBEDDINGS (for RAG)
# ============================================================

print("\n🧠 Creating 'product_embeddings' table...")

cursor.execute("""
CREATE TABLE IF NOT EXISTS product_embeddings (
    product_id TEXT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    embedding BYTEA,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

print("   ✅ Product embeddings table created")

# ============================================================
# TABLE 4: CONVERSATIONS
# ============================================================

print("\n💬 Creating 'conversations' table...")

cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    user_id TEXT PRIMARY KEY,
    quantity INTEGER,
    budget_per_piece INTEGER,
    timeline TEXT,
    location TEXT,
    preferences TEXT,
    current_stage TEXT,
    needs_handoff BOOLEAN DEFAULT FALSE,
    recommended_products TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_message_at TIMESTAMP DEFAULT NOW()
);
""")

print("   ✅ Conversations table created")

# ============================================================
# TABLE 5: MESSAGES
# ============================================================

print("\n📨 Creating 'messages' table...")

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES conversations(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);
""")

print("   ✅ Messages table created")

# ============================================================
# CREATE INDEXES (for faster queries)
# ============================================================

print("\n⚡ Creating indexes for faster queries...")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_pricing_product_id 
ON pricing_tiers(product_id);
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_messages_user_id 
ON messages(user_id);
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_conversations_updated 
ON conversations(updated_at);
""")

print("   ✅ Indexes created")

# ============================================================
# COMMIT CHANGES
# ============================================================

conn.commit()
cursor.close()
conn.close()

print("\n" + "=" * 70)
print("✅ ALL TABLES CREATED SUCCESSFULLY!")
print("=" * 70)

print("\n📊 Tables created:")
print("   1. products - Your product catalog")
print("   2. pricing_tiers - Quantity-based pricing")
print("   3. product_embeddings - Image embeddings for RAG")
print("   4. conversations - Customer chat state")
print("   5. messages - Full chat history")

print("\n🎯 Next step: Migrate your 6 products from JSON to Supabase")
print("=" * 70)