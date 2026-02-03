#!/bin/bash

echo "=================================================="
echo "🚀 Starting Viha WhatsApp Bot - Combined Service"
echo "=================================================="

# Install Node.js dependencies
echo ""
echo "📦 Installing Node.js dependencies..."
cd node_service
npm install
cd ..

# Install Python dependencies
echo ""
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Start Python service in background
echo ""
echo "🔵 Starting Python FastAPI service on port 8000..."
cd python_service
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
cd node_service
export LLM_API_URL=http://127.0.0.1:8000
node vihaBot.js

# If Node.js exits, kill Python too
echo ""
echo "🛑 Stopping services..."
kill $PYTHON_PID