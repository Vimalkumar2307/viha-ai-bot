"""
FastAPI wrapper for complete bot with conversation locking
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from complete_bot import ProductionVihaBot
from datetime import datetime
import os

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize bot
bot = ProductionVihaBot()

# Store locked conversations (in production, use Redis or database)
locked_conversations = {}

class ChatRequest(BaseModel):
    user_id: str
    message: str

class LockRequest(BaseModel):
    user_id: str

@app.post("/lock_conversation")
async def lock_conversation(request: LockRequest):
    """
    Lock a conversation - bot will NEVER respond to this customer again
    (until manually unlocked)
    """
    user_id = request.user_id
    
    locked_conversations[user_id] = {
        "locked_at": datetime.now().isoformat(),
        "locked_by": "wife",
        "reason": "wife_interrupted"
    }
    
    print(f"\n{'='*70}")
    print(f"🔒 CONVERSATION PERMANENTLY LOCKED")
    print(f"   Customer: {user_id}")
    print(f"   Locked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Bot will stay SILENT for this customer")
    print(f"{'='*70}\n")
    
    return {
        "status": "success",
        "message": f"Conversation locked for {user_id}",
        "locked_at": locked_conversations[user_id]["locked_at"]
    }

@app.post("/unlock_conversation")
async def unlock_conversation(request: LockRequest):
    """
    Unlock a conversation - bot can respond again
    """
    user_id = request.user_id
    
    if user_id in locked_conversations:
        lock_info = locked_conversations[user_id]
        del locked_conversations[user_id]
        
        print(f"\n{'='*70}")
        print(f"🔓 CONVERSATION UNLOCKED")
        print(f"   Customer: {user_id}")
        print(f"   Was locked at: {lock_info['locked_at']}")
        print(f"   Bot can respond again")
        print(f"{'='*70}\n")
        
        return {
            "status": "success",
            "message": f"Conversation unlocked for {user_id}",
            "was_locked_at": lock_info["locked_at"]
        }
    else:
        return {
            "status": "not_locked",
            "message": f"Conversation was not locked for {user_id}"
        }
    
@app.post("/reset_conversation")
async def reset_conversation(request: LockRequest):
    """
    Reset a conversation - clears all checkpoint state from Supabase
    Bot will start fresh on next message (useful for testing)
    """
    user_id = request.user_id
    
    try:
        import psycopg
        
        db_url = os.getenv("SUPABASE_DB_URL")
        
        # Connect to Supabase
        conn = psycopg.connect(db_url)
        cursor = conn.cursor()
        
        # Delete all checkpoints for this specific user
        cursor.execute("""
            DELETE FROM checkpoints 
            WHERE thread_id = %s
        """, (user_id,))
        
        deleted_checkpoints = cursor.rowcount
        
        # Delete related checkpoint writes
        cursor.execute("""
            DELETE FROM checkpoint_writes 
            WHERE thread_id = %s
        """, (user_id,))
        
        deleted_writes = cursor.rowcount
        
        # Commit changes
        conn.commit()
        cursor.close()
        conn.close()
        
        # Also remove from locked conversations if present
        was_locked = False
        if user_id in locked_conversations:
            del locked_conversations[user_id]
            was_locked = True
        
        print(f"\n{'='*70}")
        print(f"🔄 CONVERSATION RESET COMPLETE")
        print(f"   Customer: {user_id}")
        print(f"   Deleted checkpoints: {deleted_checkpoints}")
        print(f"   Deleted writes: {deleted_writes}")
        print(f"   Was locked: {was_locked}")
        print(f"   Bot will start fresh on next message")
        print(f"{'='*70}\n")
        
        return {
            "status": "success",
            "message": f"Conversation reset for {user_id}. Bot will start fresh.",
            "reset_at": datetime.now().isoformat(),
            "deleted_checkpoints": deleted_checkpoints,
            "deleted_writes": deleted_writes,
            "was_locked": was_locked
        }
        
    except Exception as e:
        print(f"❌ Error resetting conversation: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "status": "error",
            "message": f"Failed to reset conversation: {str(e)}"
        }

@app.get("/locked_conversations")
async def get_locked_conversations():
    """
    Get list of all locked conversations
    """
    return {
        "locked_conversations": [
            {
                "user_id": user_id,
                "locked_at": info["locked_at"],
                "locked_by": info["locked_by"],
                "reason": info["reason"]
            }
            for user_id, info in locked_conversations.items()
        ],
        "total_locked": len(locked_conversations)
    }

@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat endpoint - checks if conversation is locked first"""
    try:
        # ===== PRIORITY CHECK: Is conversation locked? =====
        if request.user_id in locked_conversations:
            lock_info = locked_conversations[request.user_id]
            
            print(f"\n{'='*70}")
            print(f"🔒 LOCKED CONVERSATION - BOT STAYING SILENT")
            print(f"   Customer: {request.user_id}")
            print(f"   Locked since: {lock_info['locked_at']}")
            print(f"   Locked by: {lock_info['locked_by']}")
            print(f"   Message received: \"{request.message}\"")
            print(f"   Bot response: [SILENT]")
            print(f"{'='*70}\n")
            
            return {
                "status": "locked",
                "reply": None,
                "needs_handoff": False,
                "products": None,
                "locked": True,
                "locked_at": lock_info['locked_at'],
                "locked_by": lock_info['locked_by']
            }
        
        # ===== Normal chat flow if not locked =====
        print(f"\n{'='*70}")
        print(f"💬 API Request from: {request.user_id}")
        print(f"📩 Message: {request.message}")
        print(f"{'='*70}")
        
        response = bot.chat(request.user_id, request.message)

        # ✅ ADD DEBUG LOGGING
        print(f"\n🔍 DEBUG: Bot response keys: {response.keys()}")
        print(f"🔍 DEBUG: requirements_summary = {response.get('requirements_summary', 'NOT FOUND')}")
        print(f"🔍 DEBUG: customer_requirements = {response.get('customer_requirements', 'NOT FOUND')}")
        print(f"🔍 DEBUG: handoff_reason = {response.get('handoff_reason', 'NOT FOUND')}")

        return_data = {
            "status": "success",
            "reply": response["reply"],
            "needs_handoff": response["needs_handoff"],
            "products": response.get("products"),
            "requirements_summary": response.get("requirements_summary"),
            "customer_requirements": response.get("customer_requirements"),
            "handoff_reason": response.get("handoff_reason"),
            "locked": False,
            "customer_number": request.user_id,
            "last_message": request.message
        }

        print(f"🔍 DEBUG: Returning data with these keys: {return_data.keys()}")
        print(f"🔍 DEBUG: Return data: {return_data}\n")

        return return_data
        
    except Exception as e:
        print(f"❌ ERROR in chat endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "status": "error",
            "reply": None,
            "needs_handoff": True,
            "products": None,
            "locked": False,
            "customer_number": request.user_id,
            "last_message": request.message
        }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "3.0",
        "locked_conversations": len(locked_conversations),
        "available_endpoints": [
            "POST /chat - Send message to bot",
            "POST /lock_conversation - Lock conversation (wife takes over)",
            "POST /unlock_conversation - Unlock conversation",
            "POST /reset_conversation - Reset conversation (clear all state)",
            "GET /locked_conversations - List all locked conversations",
            "GET /health - Check API status"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Complete Bot API v3.0...")
    print("   • Conversation locking enabled")
    print("   • Wife can take over anytime")
    uvicorn.run(app, host="0.0.0.0", port=8000)