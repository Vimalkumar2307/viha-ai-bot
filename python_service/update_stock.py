"""
Quick script to update stock availability
Usage: python update_stock.py
Not used now
"""

import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

def list_variants():
    """List all variants"""
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = psycopg.connect(db_url)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.name, pv.size, pv.type, pv.design_name, pv.is_available
        FROM product_variants pv
        JOIN products p ON p.id = pv.product_id
        ORDER BY p.name, pv.size, pv.design_name
    """)
    
    print("\n" + "=" * 70)
    print("📦 CURRENT PRODUCT VARIANTS")
    print("=" * 70)
    
    for row in cursor.fetchall():
        name, size, vtype, design, available = row
        
        display = f"{name} - {size}"
        if vtype:
            display += f" ({vtype})"
        if design:
            display += f" - {design}"
        
        status = "✅ Available" if available else "❌ Out of stock"
        print(f"{display}: {status}")
    
    cursor.close()
    conn.close()

def update_stock(product_id, size, type_val, design_name, is_available):
    """Update stock status for a specific variant"""
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = psycopg.connect(db_url)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE product_variants
        SET is_available = %s,
            stock_status = %s,
            updated_at = NOW()
        WHERE product_id = %s
          AND size = %s
          AND (type = %s OR (type IS NULL AND %s IS NULL))
          AND (design_name = %s OR (design_name IS NULL AND %s IS NULL))
    """, (
        is_available,
        'in_stock' if is_available else 'out_of_stock',
        product_id,
        size,
        type_val, type_val,
        design_name, design_name
    ))
    
    conn.commit()
    
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    
    if affected > 0:
        status = "✅ Available" if is_available else "❌ Out of stock"
        print(f"\n✅ Updated: {product_id} - {size} → {status}")
    else:
        print(f"\n❌ No matching variant found")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("📦 STOCK MANAGEMENT TOOL")
    print("=" * 70)
    
    # List all variants
    list_variants()
    
    print("\n" + "=" * 70)
    print("EXAMPLES:")
    print("=" * 70)
    
    print("\n# Mark big plain airtight container as out of stock:")
    print('update_stock("airtight_container", "big", None, "Plain", False)')
    
    print("\n# Mark it back in stock:")
    print('update_stock("airtight_container", "big", None, "Plain", True)')
    
    print("\n# Mark 5 inch cylinder jar as out of stock:")
    print('update_stock("pichwai_jar", "5 inch", "cylinder", None, False)')
    
    print("\n" + "=" * 70)
    
    # Example: Uncomment to use
    # update_stock("airtight_container", "big", None, "Plain", False)