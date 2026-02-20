"""
Lead service — save and update leads in Supabase
Called after every bot chat interaction that has requirements.
"""

import re
from db.connection import get_db_connection


def save_or_update_lead(customer_number: str, response: dict, status: str = None):
    """
    Insert lead if new, update if exists.
    Called after every bot interaction that has requirements.

    Args:
        customer_number: WhatsApp number of the customer
        response: Full bot response dict (from bot.chat())
        status: Lead status override. If None, determined from response.
    """
    try:
        req = response.get("customer_requirements")

        # Determine status from response if not provided
        if not status:
            if response.get("reply") == "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]":
                status = "products_shown"
            elif response.get("needs_handoff"):
                status = "follow_up"
            else:
                status = "requirements_collecting"

        # Extract fields safely
        quantity = req.get("quantity") if req else None
        budget   = req.get("budget")   if req else None
        location = req.get("location") if req else None
        timeline = req.get("timeline") if req else None
        last_msg = response.get("last_message", "")

        # Parse budget string to numeric (e.g. "₹50" → 50.0)
        budget_numeric = None
        if budget:
            numbers = re.findall(r'\d+\.?\d*', str(budget))
            if numbers:
                budget_numeric = float(numbers[0])

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if lead exists
                cursor.execute(
                    "SELECT id FROM leads WHERE customer_number = %s",
                    (customer_number,)
                )
                existing = cursor.fetchone()

                if existing:
                    # UPDATE existing lead — only overwrite non-null values
                    cursor.execute("""
                        UPDATE leads SET
                            quantity         = COALESCE(%s, quantity),
                            budget_per_piece = COALESCE(%s, budget_per_piece),
                            location         = COALESCE(%s, location),
                            timeline         = COALESCE(%s, timeline),
                            status           = %s,
                            last_message     = COALESCE(%s, last_message),
                            updated_at       = NOW()
                        WHERE customer_number = %s
                    """, (
                        quantity, budget_numeric, location, timeline,
                        status, last_msg, customer_number
                    ))
                    print(f"    📝 Lead updated: {customer_number} → {status}")
                else:
                    # INSERT new lead
                    cursor.execute("""
                        INSERT INTO leads
                            (customer_number, quantity, budget_per_piece,
                             location, timeline, status, last_message)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        customer_number, quantity, budget_numeric,
                        location, timeline, status, last_msg
                    ))
                    print(f"    📝 Lead created: {customer_number} → {status}")

                conn.commit()

    except Exception as e:
        print(f"    ⚠️  Lead save failed (non-critical): {e}")