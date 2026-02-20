"""
VihaReturnGifts AI Bot — Python Service
Version: 5.0 - Modular architecture

Entry point for FastAPI application.
Run with: uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import bot
from complete_bot import ProductionVihaBot

# Import services
from services.lock_service import load_locked_conversations_from_db

# Import routers
from api.chat import router as chat_router, set_bot
from api.conversations import router as conversations_router
from api.leads import router as leads_router
from api.analytics import router as analytics_router

# ============================================================
# APP INIT
# ============================================================

app = FastAPI(
    title="VihaReturnGifts AI Bot API",
    version="5.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ROUTERS
# ============================================================

app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(leads_router)
app.include_router(analytics_router)

# ============================================================
# BOT SINGLETON
# Initialized once at startup, injected into chat router
# ============================================================

bot = ProductionVihaBot()
set_bot(bot)  # Inject into chat.py

# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Validate environment and load locked conversations from Supabase"""
    print("\n" + "="*70)
    print("🔍 VALIDATING PRODUCTION ENVIRONMENT")
    print("="*70)

    db_url   = os.getenv("SUPABASE_DB_URL")
    groq_key = os.getenv("GROQ_API_KEY")

    if not db_url:
        raise ValueError("SUPABASE_DB_URL environment variable is required")
    if not groq_key:
        raise ValueError("GROQ_API_KEY environment variable is required")

    print(f"✅ Database URL: {db_url[:50]}...{db_url[-20:]}")
    print(f"✅ Groq API Key: {groq_key[:20]}...")

    # Load locked conversations from Supabase into memory cache
    load_locked_conversations_from_db()

    print("="*70 + "\n")


# ============================================================
# HEALTH ENDPOINTS
# ============================================================

@app.get("/health")
async def health():
    from services.lock_service import locked_conversations_cache
    return {
        "status":               "healthy",
        "version":              "5.0",
        "locked_conversations": len(locked_conversations_cache),
        "timestamp":            datetime.now().isoformat()
    }


@app.get("/health-check")
@app.head("/health-check")
async def health_check():
    from services.lock_service import locked_conversations_cache
    from db.connection import get_db_connection
    try:
        db_url = os.getenv("SUPABASE_DB_URL")
        if not db_url:
            return {"status": "unhealthy", "error": "SUPABASE_DB_URL not configured"}

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM checkpoints")
                checkpoint_count = cursor.fetchone()[0]

        return {
            "status":               "healthy",
            "timestamp":            datetime.now().isoformat(),
            "database_connected":   True,
            "checkpoint_count":     checkpoint_count,
            "locked_conversations": len(locked_conversations_cache),
            "groq_api_configured":  bool(os.getenv("GROQ_API_KEY"))
        }

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting VihaReturnGifts AI Bot API v5.0...")
    uvicorn.run(app, host="0.0.0.0", port=8000)