"""
Migrate Products from JSON to Supabase
Reads products.json and inserts into Supabase database
"""

import os
import json
from dotenv import load_dotenv
import psycopg2
from datetime import datetime

load_dotenv()

print("=" * 70)
print("📦 MIGRATING PRODUCTS FROM JSON TO SUPABASE")
print("=" * 70)

# ============================================================
# STEP 1: Load products.json
# ============================================================

print("\n📂 Loading products.json...")

# Find products.json (in parent directory)
json_path = os.path.join('..', 'products.json')

if not os.path.exists(json_path):
    # Try current directory
    json_path = 'products.json'

if not os.path.exists(json_path):
    print("❌ ERROR: products.json not found!")
    print("   Make sure products.json is in the project root")
    exit(1)

with open(json_path, 'r', encoding='utf-8') as f:
    products_data = json.load(f)

products = products_data['products']
print(f"✅ Loaded {len(products)} products from JSON")

# ============================================================
# STEP 2: Connect to Supabase
# ============================================================

print("\n🔗 Connecting to Supabase...")

db_url = os.getenv("SUPABASE_DB_URL")
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

print("✅ Connected to Supabase")

# ============================================================
# STEP 3: Clear existing data (if any)
# ============================================================

print("\n🧹 Clearing existing data...")

cursor.execute("DELETE FROM pricing_tiers;")
cursor.execute("DELETE FROM product_embeddings;")
cursor.execute("DELETE FROM products;")

print("✅ Old data cleared")

# ============================================================
# STEP 4: Insert products
# ============================================================

print("\n📦 Inserting products...")

for product in products:
    print(f"\n   Processing: {product['name']}")
    
    # Insert into products table
    cursor.execute("""
        INSERT INTO products (
            id, name, category, description, 
            image_url, min_order, special_rule, unit
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        product['id'],
        product['name'],
        product['category'],
        product.get('description', ''),
        product.get('image_url', ''),
        product['min_order'],
        product.get('special_rule'),
        product.get('unit')
    ))
    
    print(f"      ✅ Product inserted")
    
    # Insert pricing tiers
    for tier in product['pricing']:
        cursor.execute("""
            INSERT INTO pricing_tiers (
                product_id, quantity_range, price_per_piece
            ) VALUES (%s, %s, %s)
        """, (
            product['id'],
            tier['quantity_range'],
            tier['price_per_piece']
        ))
    
    print(f"      ✅ {len(product['pricing'])} pricing tier(s) inserted")

# ============================================================
# STEP 5: Commit changes
# ============================================================

conn.commit()

print("\n💾 All changes committed to database")

# ============================================================
# STEP 6: Verify migration
# ============================================================

print("\n🔍 Verifying migration...")

# Count products
cursor.execute("SELECT COUNT(*) FROM products;")
product_count = cursor.fetchone()[0]

# Count pricing tiers
cursor.execute("SELECT COUNT(*) FROM pricing_tiers;")
tier_count = cursor.fetchone()[0]

print(f"   ✅ Products in database: {product_count}")
print(f"   ✅ Pricing tiers in database: {tier_count}")

# Show sample data
cursor.execute("""
    SELECT p.name, p.category, pt.quantity_range, pt.price_per_piece
    FROM products p
    JOIN pricing_tiers pt ON p.id = pt.product_id
    LIMIT 3;
""")

print("\n📊 Sample data:")
for row in cursor.fetchall():
    print(f"   • {row[0]} ({row[1]}) - {row[2]}: ₹{row[3]}/piece")

# ============================================================
# STEP 7: Close connection
# ============================================================

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("✅ MIGRATION COMPLETE!")
print("=" * 70)

print(f"\n📊 Summary:")
print(f"   • {product_count} products migrated")
print(f"   • {tier_count} pricing tiers created")
print(f"   • All data verified in Supabase")

print("\n🎯 Next steps:")
print("   1. Generate image embeddings for RAG")
print("   2. Update bot to use Supabase")
print("=" * 70)