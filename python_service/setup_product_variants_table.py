"""
Setup Product Variants Table in Supabase
Handles size, type, and design variations for products
"""

import os
from dotenv import load_dotenv
import psycopg

load_dotenv()

print("=" * 70)
print("🏗️  CREATING PRODUCT VARIANTS TABLE")
print("=" * 70)

db_url = os.getenv("SUPABASE_DB_URL")
conn = psycopg.connect(db_url)
cursor = conn.cursor()

print("\n✅ Connected to Supabase")

# ============================================================
# TABLE: PRODUCT VARIANTS
# ============================================================

print("\n📦 Creating 'product_variants' table...")

cursor.execute("""
CREATE TABLE IF NOT EXISTS product_variants (
    id SERIAL PRIMARY KEY,
    product_id TEXT REFERENCES products(id) ON DELETE CASCADE,
    
    -- Variant attributes
    size TEXT,
    type TEXT,
    design_name TEXT,
    
    -- Pricing (quantity-based)
    quantity_range TEXT NOT NULL,
    price_per_piece INTEGER NOT NULL,
    
    -- Image for this specific variant
    image_url TEXT NOT NULL,
    
    -- Availability
    is_available BOOLEAN DEFAULT TRUE,
    stock_status TEXT DEFAULT 'in_stock',
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Unique constraint
    UNIQUE(product_id, size, type, design_name, quantity_range)
);
""")

print("   ✅ Product variants table created")

# ============================================================
# CREATE INDEXES
# ============================================================

print("\n⚡ Creating indexes...")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_variants_product_id 
ON product_variants(product_id);
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_variants_available 
ON product_variants(is_available);
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_variants_price 
ON product_variants(price_per_piece);
""")

print("   ✅ Indexes created")

# ============================================================
# COMMIT
# ============================================================

conn.commit()
cursor.close()
conn.close()

print("\n" + "=" * 70)
print("✅ PRODUCT VARIANTS TABLE CREATED!")
print("=" * 70)

print("\n📊 Table Structure:")
print("   • id - Auto-increment primary key")
print("   • product_id - Links to products table")
print("   • size - e.g., '4 inch', '5 inch', 'small', 'big'")
print("   • type - e.g., 'jar', 'cylinder', 'matki'")
print("   • design_name - e.g., 'Floral', 'Geometric', 'Plain'")
print("   • quantity_range - e.g., '25-49 pieces'")
print("   • price_per_piece - Price for this variant")
print("   • image_url - Specific image for this variant")
print("   • is_available - Stock status")

print("\n🎯 Next step: Update products.json with variants")
print("=" * 70)