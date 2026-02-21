"""
Leads endpoints
POST /leads       — leads for last N days
GET  /lead_info   — single customer details
"""

from fastapi import APIRouter
from datetime import datetime, timedelta
from models.schemas import LeadsRequest
from db.connection import get_db_connection

router = APIRouter()


# ============================================================
# LEADS LIST
# ============================================================

@router.post("/leads")
async def get_leads(request: LeadsRequest):
    """
    Return leads for the last N days.
    Called by Node when wife sends: LEADS 7
    """
    try:
        days  = max(1, min(request.days, 365))  # Clamp 1–365
        since = datetime.now() - timedelta(days=days)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        timeline,
                        status,
                        last_message,
                        created_at,
                        updated_at,
                        push_name
                    FROM leads
                    WHERE created_at >= %s
                    ORDER BY updated_at DESC
                """, (since,))
                rows = cursor.fetchall()

        if not rows:
            return {
                "status":  "success",
                "days":    days,
                "total":   0,
                "leads":   [],
                "message": f"No leads in the last {days} day(s)"
            }

        leads = []
        for row in rows:
            customer_number, quantity, budget, location, timeline, status, last_msg, created_at, updated_at, push_name = row
            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "timeline":        timeline,
                "location":        location,
                "status":          status,
                "updated_at":      updated_at.strftime("%d %b %H:%M") if updated_at else "-",
                "push_name": push_name or ""
            })

        return {
            "status": "success",
            "days":   days,
            "total":  len(leads),
            "leads":  leads
        }

    except Exception as e:
        print(f"❌ Leads fetch failed: {e}")
        return {"status": "error", "message": str(e), "leads": []}


# ============================================================
# SINGLE LEAD INFO
# ============================================================

@router.get("/lead_info/{customer_number}")
async def get_lead_info(customer_number: str):
    """
    Return full details for a single customer.
    Called by Node when wife sends: INFO 919942463672
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        timeline,
                        status,
                        last_message,
                        created_at,
                        updated_at,
                        push_name
                    FROM leads
                    WHERE customer_number = %s
                """, (customer_number,))
                row = cursor.fetchone()

        if not row:
            return {
                "status":  "not_found",
                "message": f"No lead found for {customer_number}"
            }

        customer_number, quantity, budget, location, timeline, status, last_msg, created_at, updated_at, push_name = row

        return {
            "status": "success",
            "lead": {
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{budget}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "status":          status,
                "last_message":    last_msg,
                "created_at":      created_at.isoformat() if created_at else None,
                "updated_at":      updated_at.isoformat() if updated_at else None,
                "push_name": push_name or ""
            }
        }

    except Exception as e:
        print(f"❌ Lead info fetch failed: {e}")
        return {"status": "error", "message": str(e)}