#!/bin/bash

echo "=================================================="
echo "🚀 Starting Viha WhatsApp Bot - Combined Service"
echo "=================================================="

# Start Python service in background
echo ""
echo "🔵 Starting Python FastAPI service on port 8000..."

# Change to python_service directory and start
cd python_service || { echo "❌ Failed to find python_service directory"; exit 1; }
python -m uvicorn bot_api:app --host 0.0.0.0 --port 8000 &
PYTHON_PID=$!
echo "✅ Python service started (PID: $PYTHON_PID)"
cd ..

# Wait for Python to be ready
echo ""
echo "⏳ Waiting for Python service to initialize..."
sleep 5

# Start Node.js service in foreground
echo ""
echo "🟢 Starting Node.js WhatsApp service..."
cd node_service || { echo "❌ Failed to find node_service directory"; exit 1; }
export LLM_API_URL=http://127.0.0.1:8000
node vihaBot.js

# If Node.js exits, kill Python too
echo ""
echo "🛑 Stopping services..."
kill $PYTHON_PID