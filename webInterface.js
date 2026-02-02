/**
 * Web Interface Module
 * Handles Express server and web interface
 */

const express = require('express');

const app = express();
const PORT = process.env.PORT || 3000;

// Shared state (passed from main bot)
let botState = {
    isReady: false,
    qrCodeData: '',
    reconnectAttempts: 0,
    lastConnected: null
};

/**
 * Update bot state from main bot
 */
function updateBotState(newState) {
    botState = { ...botState, ...newState };
}

/**
 * Home page - shows bot status or QR code
 */
app.get('/', (req, res) => {
    if (botState.isReady) {
        res.send(`
            <html>
                <head>
                    <title>WhatsApp Bot Status</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body { 
                            font-family: Arial, sans-serif; 
                            text-align: center; 
                            padding: 20px; 
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }
                        .container { 
                            max-width: 600px; 
                            background: white; 
                            padding: 40px; 
                            border-radius: 20px; 
                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        }
                        .status-online { color: #28a745; font-size: 1.2em; }
                        .badge { 
                            background: #28a745; 
                            color: white; 
                            padding: 8px 16px; 
                            border-radius: 20px; 
                            display: inline-block;
                            margin: 10px 0;
                        }
                        .btn { 
                            background: #667eea; 
                            color: white; 
                            padding: 12px 24px; 
                            border: none; 
                            border-radius: 8px; 
                            cursor: pointer; 
                            margin: 10px;
                            font-size: 16px;
                        }
                        .btn:hover { background: #5568d3; }
                        .info-box {
                            background: #f8f9fa;
                            padding: 20px;
                            border-radius: 10px;
                            margin: 20px 0;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>✅ Bot is Online!</h1>
                        <div class="badge">🤖 AI-Powered</div>
                        <p class="status-online">VihaReturnGifts AI Bot is active and ready</p>
                        <div class="info-box">
                            <h3>📊 Status</h3>
                            <p>Mode: LLM-Powered</p>
                            <p>Last connected: ${botState.lastConnected || new Date().toLocaleString()}</p>
                        </div>
                        <button class="btn" onclick="location.reload()">🔄 Refresh Status</button>
                    </div>
                </body>
            </html>
        `);
    } else if (botState.qrCodeData) {
        res.send(`
            <html>
                <head>
                    <title>Scan QR Code</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body { 
                            font-family: Arial, sans-serif; 
                            text-align: center; 
                            padding: 20px; 
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }
                        .container { 
                            max-width: 600px; 
                            background: white; 
                            padding: 40px; 
                            border-radius: 20px; 
                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        }
                        .qr-code { 
                            max-width: 300px; 
                            margin: 20px auto; 
                            border: 3px solid #667eea; 
                            border-radius: 15px; 
                            padding: 10px;
                            background: white;
                        }
                        .warning { 
                            background: #fff3cd; 
                            padding: 15px; 
                            border-radius: 10px; 
                            margin: 20px 0;
                            border-left: 4px solid #ffc107;
                        }
                        .instructions { 
                            text-align: left; 
                            background: #e7f3ff; 
                            padding: 20px; 
                            border-radius: 10px; 
                            margin: 20px 0;
                            border-left: 4px solid #667eea;
                        }
                        .instructions ol { margin: 10px 0; padding-left: 20px; }
                        .instructions li { margin: 8px 0; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>📱 Scan QR Code</h1>
                        <p>Connect your WhatsApp to the AI bot</p>
                        <div class="instructions">
                            <h3>📋 How to connect:</h3>
                            <ol>
                                <li>Open WhatsApp on your phone</li>
                                <li>Tap Menu (⋮) or Settings</li>
                                <li>Tap "Linked Devices"</li>
                                <li>Tap "Link a Device"</li>
                                <li>Point your phone at this screen</li>
                            </ol>
                        </div>
                        <div id="qr-container">
                            <img src="${botState.qrCodeData}" alt="QR Code" class="qr-code">
                        </div>
                        <div class="warning">
                            <p><strong>⚠️ Important:</strong> QR code expires in 20 seconds. Page will refresh automatically.</p>
                        </div>
                    </div>
                    <script>
                        setTimeout(() => location.reload(), 15000);
                    </script>
                </body>
            </html>
        `);
    } else {
        res.send(`
            <html>
                <head>
                    <title>Bot Starting</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body { 
                            font-family: Arial, sans-serif; 
                            text-align: center; 
                            padding: 20px; 
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }
                        .container { 
                            max-width: 600px; 
                            background: white; 
                            padding: 40px; 
                            border-radius: 20px; 
                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        }
                        .spinner { 
                            border: 4px solid #f3f3f3; 
                            border-top: 4px solid #667eea; 
                            border-radius: 50%; 
                            width: 50px; 
                            height: 50px; 
                            animation: spin 1s linear infinite; 
                            margin: 20px auto;
                        }
                        @keyframes spin { 
                            0% { transform: rotate(0deg); } 
                            100% { transform: rotate(360deg); } 
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>🔄 Starting Bot...</h1>
                        <div class="spinner"></div>
                        <p>Initializing WhatsApp connection...</p>
                        <p><small>This may take a few seconds</small></p>
                    </div>
                    <script>
                        setTimeout(() => location.reload(), 3000);
                    </script>
                </body>
            </html>
        `);
    }
});

/**
 * Health check endpoint
 */
app.get('/health', (req, res) => {
    res.json({
        status: botState.isReady ? 'ready' : 'initializing',
        mode: 'LLM',
        timestamp: new Date().toISOString(),
        reconnectAttempts: botState.reconnectAttempts
    });
});

/**
 * API endpoint - Bot stats
 */
app.get('/api/stats', (req, res) => {
    res.json({
        isReady: botState.isReady,
        hasQR: !!botState.qrCodeData,
        reconnectAttempts: botState.reconnectAttempts,
        lastConnected: botState.lastConnected,
        uptime: process.uptime()
    });
});

/**
 * Start the Express server
 */
function startWebServer() {
    app.listen(PORT, () => {
        console.log(`🌐 Web interface: http://localhost:${PORT}`);
        console.log(`📊 Health check: http://localhost:${PORT}/health`);
        console.log(`📈 Stats API: http://localhost:${PORT}/api/stats`);
    });
}

module.exports = {
    startWebServer,
    updateBotState
};