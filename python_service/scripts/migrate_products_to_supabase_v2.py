"""
Migrate Products with Variants to Supabase
Handles both regular products and products with variants
"""

import os
import json
from dotenv import load_dotenv
import psycopg

load_dotenv()

print("=" * 70)
print("📦 MIGRATING PRODUCTS WITH VARIANTS TO SUPABASE")
print("=" * 70)

# Load products.json
json_path = os.path.join('..', 'products.json')
if not os.path.exists(json_path):
    json_path = 'products.json'

with open(json_path, 'r', encoding='utf-8') as f:
    products_data = json.load(f)

products = products_data['products']
print(f"✅ Loaded {len(products)} products from JSON")

# Connect to Supabase
db_url = os.getenv("SUPABASE_DB_URL")
conn = psycopg.connect(db_url)
cursor = conn.cursor()

print("✅ Connected to Supabase")

# ============================================================
# CLEAR EXISTING DATA
# ============================================================

print("\n🧹 Clearing existing data...")
cursor.execute("DELETE FROM product_variants;")
cursor.execute("DELETE FROM pricing_tiers;")
cursor.execute("DELETE FROM products;")
print("   ✅ Old data cleared")

# ============================================================
# INSERT PRODUCTS
# ============================================================

print("\n📦 Inserting products...")

total_products = 0
total_variants = 0
total_regular_pricing = 0

for product in products:
    print(f"\n   Processing: {product['name']}")
    
    # Insert main product
    cursor.execute("""
        INSERT INTO products (
            id, name, category, description, 
            image_url, min_order, special_rule, unit,
            has_variants
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        product['id'],
        product['name'],
        product['category'],
        product.get('description', ''),
        product.get('image_url', ''),
        product['min_order'],
        product.get('special_rule'),
        product.get('unit'),
        product.get('has_variants', False)
    ))
    
    total_products += 1
    print(f"      ✅ Product inserted")
    
    # Check if has variants
    if product.get('has_variants'):
        # Insert variants
        for variant in product['variants']:
            size = variant.get('size')
            variant_type = variant.get('type')
            design_name = variant.get('design_name')
            image_url = variant.get('image_url')
            is_available = variant.get('is_available', True)
            stock_status = variant.get('stock_status', 'in_stock')
            
            for tier in variant['pricing']:
                cursor.execute("""
                    INSERT INTO product_variants (
                        product_id, size, type, design_name,
                        quantity_range, price_per_piece, image_url,
                        is_available, stock_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    product['id'],
                    size,
                    variant_type,
                    design_name,
                    tier['quantity_range'],
                    tier['price_per_piece'],
                    image_url,
                    is_available,
                    stock_status
                ))
                
                total_variants += 1
                
                # Build display name
                display_name = f"{size}"
                if variant_type:
                    display_name += f" ({variant_type})"
                if design_name:
                    display_name += f" - {design_name}"
                
                status_emoji = "✅" if is_available else "❌"
                print(f"      {status_emoji} {display_name} - {tier['quantity_range']}: ₹{tier['price_per_piece']}")
    else:
        # Regular product - insert pricing tiers
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
            
            total_regular_pricing += 1
            print(f"      ✅ {tier['quantity_range']}: ₹{tier['price_per_piece']}")

# ============================================================
# COMMIT
# ============================================================

conn.commit()

print("\n💾 All changes committed to database")

# ============================================================
# VERIFY
# ============================================================

print("\n🔍 Verifying migration...")

# Count products
cursor.execute("SELECT COUNT(*) FROM products;")
product_count = cursor.fetchone()[0]

# Count variants
cursor.execute("SELECT COUNT(*) FROM product_variants;")
variant_count = cursor.fetchone()[0]

# Count regular pricing
cursor.execute("SELECT COUNT(*) FROM pricing_tiers;")
pricing_count = cursor.fetchone()[0]

print(f"\n📊 Migration Summary:")
print(f"   • Products: {product_count}")
print(f"   • Variants: {variant_count}")
print(f"   • Regular pricing tiers: {pricing_count}")

# Show sample variants
cursor.execute("""
    SELECT p.name, pv.size, pv.type, pv.design_name, 
           pv.quantity_range, pv.price_per_piece, pv.is_available
    FROM product_variants pv
    JOIN products p ON p.id = pv.product_id
    ORDER BY p.name, pv.size
    LIMIT 5;
""")

print("\n📊 Sample variants:")
for row in cursor.fetchall():
    name, size, vtype, design, qty_range, price, available = row
    
    display = f"{name} - {size}"
    if vtype:
        display += f" ({vtype})"
    if design:
        display += f" - {design}"
    
    status = "✅" if available else "❌"
    print(f"   {status} {display} - {qty_range}: ₹{price}")

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("✅ MIGRATION COMPLETE!")
print("=" * 70)