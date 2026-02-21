"""
Analytics endpoints
POST /summary   — business overview for date range
POST /pending   — incomplete conversations
POST /followup  — leads silent after products shown
POST /hotleads  — high quantity leads
POST /locked    — locked conversations for date range
"""

from fastapi import APIRouter
from datetime import datetime, timedelta
from models.schemas import (
    SummaryRequest, PendingRequest,
    FollowupRequest, HotleadsRequest, LockedRequest,
    UpcomingEventsRequest
)
from db.connection import get_db_connection

router = APIRouter()


# ============================================================
# SUMMARY
# ============================================================

@router.post("/summary")
async def get_summary(request: SummaryRequest):
    """
    Return business summary for a date range.
    Default: today
    """
    try:
        # Parse dates
        start = (
            datetime.strptime(request.start_date, "%Y-%m-%d")
            if request.start_date
            else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = (
            datetime.strptime(request.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if request.end_date
            else datetime.now().replace(hour=23, minute=59, second=59)
        )

        with get_db_connection() as conn:
            with conn.cursor() as cursor:

                # Overview counts
                cursor.execute("""
                    SELECT
                        COUNT(*)                                                          AS total,
                        COUNT(*) FILTER (WHERE status = 'products_shown')                AS products_shown,
                        COUNT(*) FILTER (WHERE status = 'locked')                        AS locked,
                        COUNT(*) FILTER (WHERE status = 'requirements_collecting')       AS incomplete,
                        COUNT(*) FILTER (
                            WHERE status = 'products_shown'
                            AND updated_at < NOW() - INTERVAL '1 day'
                        )                                                                 AS followup_pending
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                """, (start, end))
                overview = cursor.fetchone()
                total, products_shown, locked, incomplete, followup_pending = overview

                # Averages (quantity > 0 only)
                cursor.execute("""
                    SELECT
                        ROUND(AVG(quantity))         AS avg_qty,
                        ROUND(AVG(budget_per_piece)) AS avg_budget
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                      AND quantity > 0
                """, (start, end))
                avgs = cursor.fetchone()
                avg_qty, avg_budget = avgs if avgs else (None, None)

                # Top locations
                cursor.execute("""
                    SELECT location, COUNT(*) AS cnt
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                      AND location IS NOT NULL
                    GROUP BY location
                    ORDER BY cnt DESC
                    LIMIT 3
                """, (start, end))
                top_locations = cursor.fetchall()

                # Lead details sorted by priority
                cursor.execute("""
                    SELECT
                        customer_number, quantity, budget_per_piece,
                        timeline, location, status, updated_at, push_name
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                    ORDER BY
                        CASE status
                            WHEN 'products_shown' THEN
                                CASE WHEN updated_at < NOW() - INTERVAL '1 day'
                                     THEN 1 ELSE 3 END
                            WHEN 'requirements_collecting' THEN 2
                            WHEN 'new'                     THEN 4
                            WHEN 'locked'                  THEN 5
                            ELSE 6
                        END,
                        quantity DESC NULLS LAST
                """, (start, end))
                leads_rows = cursor.fetchall()

        # Build leads list
        leads = []
        for row in leads_rows:
            customer_number, quantity, budget, timeline, location, status, updated_at, push_name = row
            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "timeline":        timeline,
                "location":        location,
                "status":          status,
                "updated_at":      updated_at.strftime("%d %b %H:%M") if updated_at else "-",
                "push_name":        push_name or ""
            })

        locations_str = ", ".join(
            f"{loc}({cnt})" for loc, cnt in top_locations
        ) if top_locations else "No data"

        return {
            "status":           "success",
            "start_date":       start.strftime("%d %b %Y"),
            "end_date":         end.strftime("%d %b %Y"),
            "total":            total,
            "products_shown":   products_shown,
            "locked":           locked,
            "incomplete":       incomplete,
            "followup_pending": followup_pending,
            "avg_quantity":     int(avg_qty)    if avg_qty    else None,
            "avg_budget":       int(avg_budget) if avg_budget else None,
            "top_locations":    locations_str,
            "leads":            leads
        }

    except Exception as e:
        print(f"❌ Summary failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ============================================================
# PENDING
# ============================================================

@router.post("/pending")
async def get_pending(request: PendingRequest):
    """
    Return leads with incomplete requirements.
    Default: today
    """
    try:
        start = (
            datetime.strptime(request.start_date, "%Y-%m-%d")
            if request.start_date
            else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = (
            datetime.strptime(request.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if request.end_date
            else datetime.now().replace(hour=23, minute=59, second=59)
        )

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        timeline,
                        created_at,
                        updated_at,
                        push_name
                    FROM leads
                    WHERE status = 'requirements_collecting'
                      AND created_at BETWEEN %s AND %s
                    ORDER BY quantity DESC NULLS LAST
                """, (start, end))
                rows = cursor.fetchall()

        if not rows:
            return {
                "status":  "success",
                "total":   0,
                "leads":   [],
                "message": "No pending leads for this period"
            }

        leads = []
        for row in rows:
            customer_number, quantity, budget, location, timeline, created_at, updated_at, push_name = row

            missing = []
            if not quantity: missing.append("quantity")
            if not budget:   missing.append("budget")
            if not timeline: missing.append("timeline")
            if not location: missing.append("location")

            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "missing":         missing,
                "created_at":      created_at.strftime("%d %b %H:%M") if created_at else "-",
                "updated_at":      updated_at.strftime("%d %b %H:%M") if updated_at else "-",
                "push_name":       push_name or ""
            })

        return {
            "status": "success",
            "total":  len(leads),
            "leads":  leads
        }

    except Exception as e:
        print(f"❌ Pending fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ============================================================
# FOLLOWUP
# ============================================================

@router.post("/followup")
async def get_followup(request: FollowupRequest):
    """
    Return leads where products were shown but customer went silent.
    Default: silent for 1+ day
    """
    try:
        start = (
            datetime.strptime(request.start_date, "%Y-%m-%d")
            if request.start_date
            else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = (
            datetime.strptime(request.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if request.end_date
            else datetime.now().replace(hour=23, minute=59, second=59)
        )

        silent_cutoff = datetime.now() - timedelta(days=request.silent_days)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        timeline,
                        created_at,
                        updated_at,
                        push_name
                    FROM leads
                    WHERE status = 'products_shown'
                      AND updated_at < %s
                      AND created_at BETWEEN %s AND %s
                    ORDER BY updated_at ASC
                """, (silent_cutoff, start, end))
                rows = cursor.fetchall()

        if not rows:
            return {
                "status":  "success",
                "total":   0,
                "leads":   [],
                "message": "No follow-up needed for this period"
            }

        leads = []
        for row in rows:
            customer_number, quantity, budget, location, timeline, created_at, updated_at, push_name = row
            silent_for = (datetime.now() - updated_at).days if updated_at else 0

            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "silent_for":      silent_for,
                "created_at":      created_at.strftime("%d %b %H:%M") if created_at else "-",
                "updated_at":      updated_at.strftime("%d %b %H:%M") if updated_at else "-",
                "push_name":       push_name or ""
            })

        return {
            "status":      "success",
            "total":       len(leads),
            "silent_days": request.silent_days,
            "leads":       leads
        }

    except Exception as e:
        print(f"❌ Followup fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ============================================================
# HOTLEADS
# ============================================================

@router.post("/hotleads")
async def get_hotleads(request: HotleadsRequest):
    """
    Return high quantity leads.
    Default: quantity >= 100, last 7 days
    """
    try:
        start = (
            datetime.strptime(request.start_date, "%Y-%m-%d")
            if request.start_date
            else (datetime.now() - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = (
            datetime.strptime(request.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if request.end_date
            else datetime.now().replace(hour=23, minute=59, second=59)
        )

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
                        created_at,
                        updated_at,
                        push_name
                    FROM leads
                    WHERE quantity >= %s
                      AND created_at BETWEEN %s AND %s
                    ORDER BY quantity DESC
                """, (request.min_quantity, start, end))
                rows = cursor.fetchall()

        if not rows:
            return {
                "status":       "success",
                "total":        0,
                "leads":        [],
                "min_quantity": request.min_quantity,
                "message":      f"No hot leads (≥{request.min_quantity} pcs) for this period"
            }

        leads = []
        for row in rows:
            customer_number, quantity, budget, location, timeline, status, created_at, updated_at, push_name = row
            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "status":          status,
                "created_at":      created_at.strftime("%d %b %H:%M") if created_at else "-",
                "updated_at":      updated_at.strftime("%d %b %H:%M") if updated_at else "-",
                "push_name":       push_name or ""
            })

        return {
            "status":       "success",
            "total":        len(leads),
            "min_quantity": request.min_quantity,
            "leads":        leads
        }

    except Exception as e:
        print(f"❌ Hotleads fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ============================================================
# LOCKED (date range view)
# ============================================================

@router.post("/locked")
async def get_locked(request: LockedRequest):
    """
    Return locked conversations for a date range.
    Default: last 30 days
    """
    try:
        start = (
            datetime.strptime(request.start_date, "%Y-%m-%d")
            if request.start_date
            else (datetime.now() - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = (
            datetime.strptime(request.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if request.end_date
            else datetime.now().replace(hour=23, minute=59, second=59)
        )

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        updated_at,
                        push_name
                    FROM leads
                    WHERE status = 'locked'
                      AND updated_at BETWEEN %s AND %s
                    ORDER BY updated_at DESC
                """, (start, end))
                rows = cursor.fetchall()

        if not rows:
            return {
                "status":  "success",
                "total":   0,
                "leads":   [],
                "message": "No locked conversations for this period"
            }

        leads = []
        for row in rows:
            customer_number, quantity, budget, location, updated_at, push_name = row
            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "location":        location,
                "locked_at":       updated_at.strftime("%d %b %H:%M") if updated_at else "-",
                "push_name":       push_name or ""
            })

        return {
            "status": "success",
            "total":  len(leads),
            "leads":  leads
        }

    except Exception as e:
        print(f"❌ Locked fetch failed: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================
# UPCOMING EVENTS
# ============================================================

@router.post("/upcoming_events")
async def get_upcoming_events(request: UpcomingEventsRequest):
    try:
        today = datetime.now().date()
        target = today + timedelta(days=request.days_ahead)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number, push_name, quantity,
                        budget_per_piece, location, timeline,
                        event_date, status, created_at
                    FROM leads
                    WHERE event_date BETWEEN %s AND %s
                      AND status != 'locked'
                    ORDER BY event_date ASC
                """, (today, target))
                rows = cursor.fetchall()

        if not rows:
            return {
                "status":     "success",
                "total":      0,
                "leads":      [],
                "days_ahead": request.days_ahead
            }

        leads = []
        for row in rows:
            customer_number, push_name, quantity, budget, location, timeline, event_date, status, created_at = row
            days_remaining = (event_date - today).days

            leads.append({
                "customer_number": customer_number,
                "push_name":       push_name or "",
                "quantity":        quantity,
                "budget":          f"₹{int(budget)}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "event_date":      event_date.strftime("%d %b %Y") if event_date else None,
                "days_remaining":  days_remaining,
                "status":          status,
                "enquired_on":     created_at.strftime("%d %b") if created_at else "-"
            })

        return {
            "status":     "success",
            "total":      len(leads),
            "days_ahead": request.days_ahead,
            "leads":      leads
        }

    except Exception as e:
        print(f"❌ Upcoming events fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}