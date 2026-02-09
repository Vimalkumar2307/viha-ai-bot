/**
 * VihaReturnGifts AI WhatsApp Bot v2.2
 * • Removed occasion logic
 * • Direct image sending via WhatsApp
 */

require('dotenv').config();
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');
const { Boom } = require('@hapi/boom');
const pino = require('pino');

// Import our modules
const { chatWithLLM, checkLLMHealth, LLM_API_URL } = require('./llmClient');
const { startWebServer, updateBotState } = require('./webInterface');
const { useSupabaseAuthState } = require('./authStateSupabase');

// Import Baileys
const {
    default: makeWASocket,
    DisconnectReason,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    useMultiFileAuthState
} = require('@whiskeysockets/baileys');

// Configuration
const USE_LLM = process.env.USE_LLM === "true";
const MAX_RECONNECT_ATTEMPTS = 5;
const WIFE_NUMBER = process.env.WIFE_NUMBER || '919865204829@s.whatsapp.net';

// Bot state
let sock = null;
let reconnectAttempts = 0;

// Startup banner
console.log('='.repeat(50));
console.log('🤖 VihaReturnGifts AI WhatsApp Bot v2.2');
console.log('='.repeat(50));
console.log(`🔧 LLM Mode: ${USE_LLM ? '✅ ENABLED' : '❌ DISABLED'}`);
console.log(`🔗 LLM API: ${LLM_API_URL}`);
console.log(`📸 Image Sending: ✅ ENABLED`);
console.log('='.repeat(50));


/**
 * Helper to add delay between messages
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Send text message to WhatsApp user
 */
async function sendTextMessage(jid, text) {
    try {
        if (!text || typeof text !== 'string' || text.trim() === '') {
            console.log('❌ Invalid text provided');
            return false;
        }

        await sock.sendMessage(jid, { text: text.trim() });
        console.log(`📤 Sent text to ${jid.split('@')[0]}`);
        return true;
        
    } catch (error) {
        console.error('❌ Error sending message:', error.message);
        return false;
    }
}

/**
 * Send image with caption to WhatsApp user
 */
async function sendImageMessage(jid, imageUrl, caption) {
    try {
        // Validate image URL
        if (!imageUrl || imageUrl.trim() === '') {
            console.log('⚠️ No image URL provided, sending text only');
            return await sendTextMessage(jid, caption);
        }
        
        // Try sending image
        console.log(`📸 Attempting to send image: ${imageUrl.substring(0, 50)}...`);
        
        await sock.sendMessage(jid, {
            image: { url: imageUrl },
            caption: caption
        });
        
        console.log(`✅ Image sent successfully`);
        return true;
        
    } catch (error) {
        console.error('❌ Error sending image:', error.message);
        
        // FALLBACK: Send text-only message with product details
        const fallbackMsg = `${caption}\n\n(Image temporarily unavailable)`;
        console.log('⚠️ Falling back to text-only message');
        
        return await sendTextMessage(jid, fallbackMsg);
    }
}

/**
 * ENHANCED: Send product images with retry logic
 */
/**
 * Send multiple product images - NO selection prompt (wife takes over)
 */
/**
 * ✅ NEW: Send requirements summary, then products, then closing message
 */
async function sendProductImages(jid, products, requirementsSummary) {
    try {
        console.log(`📸 Sending requirements summary + ${products.length} product images...`);
        
        // ✅ STEP 1: Send requirements summary with "Here are X options"
        if (requirementsSummary) {
            await sendTextMessage(jid, requirementsSummary);
            await sleep(1000);
        }
        
        // ✅ STEP 2: Send all product images
        for (let i = 0; i < products.length; i++) {
            const product = products[i];
            const caption = `${i + 1}. ${product.name}\n₹${product.price}/piece`;
            
            await sendImageMessage(jid, product.image_url, caption);
            
            if (i < products.length - 1) {
                await sleep(800);
            }
        }
        
        // ✅ STEP 3: Send closing message after all images
        await sleep(1000);
        const closingMessage = "Please let us know which one you are interested. We can proceed further.";
        await sendTextMessage(jid, closingMessage);
        
        console.log(`✅ Sent all ${products.length} product images with summary and closing message`);
        console.log(`🤝 Conversation handed off to human`);
        return true;
        
    } catch (error) {
        console.error('❌ Error sending product images:', error.message);
        return false;
    }
}
/**
 * Send alert to wife with customer details
 */
/**
 * ✅ NEW: Send detailed alert to wife with customer requirements and handoff reason
 */
async function alertWife(customerNumber, llmResponse, reason = 'NEEDS_HELP') {
    try {
        let alertMessage = '';
        
        // ✅ NEW: Build detailed alert with customer requirements
        if (reason === 'NEEDS_HELP' || reason === 'PRODUCTS_SHOWN') {
            alertMessage = `🔔 *CUSTOMER NEEDS HELP*\n\n`;
            alertMessage += `Customer: +${customerNumber}\n\n`;
            
            // ✅ Add customer requirements if available
            if (llmResponse.customer_requirements) {
                const req = llmResponse.customer_requirements;
                alertMessage += `📋 *Customer Requirements:*\n`;
                if (req.quantity) alertMessage += `Quantity: ${req.quantity} pieces\n`;
                if (req.budget_per_piece) alertMessage += `Budget: ₹${req.budget_per_piece} per piece\n`;
                if (req.location) alertMessage += `Location: ${req.location}\n`;
                if (req.timeline) alertMessage += `When needed: ${req.timeline}\n`;
                alertMessage += `\n`;
            }
            
            // ✅ Add handoff reason
            if (llmResponse.handoff_reason) {
                alertMessage += `${llmResponse.handoff_reason}\n\n`;
            }
            
            alertMessage += `Please follow up with this customer.\n\nThank you! 🙏`;
            
        } else if (reason === 'BOT_ERROR') {
            alertMessage = `⚠️ *BOT ERROR - CUSTOMER NEEDS HELP*\n\n`;
            alertMessage += `Customer: +${customerNumber}\n\n`;
            
            if (llmResponse.handoff_reason) {
                alertMessage += `${llmResponse.handoff_reason}\n\n`;
            }
            
            if (llmResponse.last_message) {
                alertMessage += `Last Message:\n"${llmResponse.last_message}"\n\n`;
            }
            
            alertMessage += `Bot failed to respond. Please take over immediately.`;
        }
        
        await sendTextMessage(WIFE_NUMBER, alertMessage);
        console.log('✅ Alert sent to wife with customer requirements and handoff reason');
        console.log(`📋 Customer: +${customerNumber}`);
        console.log(`⏸️  Bot will stay silent for this customer\n`);
        
        return true;
        
    } catch (error) {
        console.error('❌ Failed to send alert to wife:', error.message);
        return false;
    }
}
/**
 * Track which customers have already been alerted about
 * This prevents spamming wife with multiple alerts
 */
const alertedCustomers = new Set();

// ✅ NEW: Track locked conversations in this session (prevent spam)
const lockedConversationsCache = new Set();
/**
 * Handle incoming WhatsApp messages - FIXED alert spam
 */
// ===== SMART MESSAGE BATCHING SYSTEM =====

// Store pending messages for each user
const userMessageQueues = new Map(); // userId -> {messages: [], timeoutId: number, jid: string}

/**
 * Smart message accumulation
 * Keeps waiting as long as customer sends messages within 5 seconds
 */
/**
 * Handle incoming WhatsApp messages - ENHANCED with dynamic timeout
 */
async function handleIncomingMessage(message) {
    try {
        const jid = message.key.remoteJid;
        const isFromMe = message.key.fromMe;
        
        // Skip groups and status broadcasts
        if (jid.includes('@g.us') || jid.includes('status@broadcast')) {
            return;
        }
        
        // ===== If WIFE sends message, LOCK conversation =====
        if (isFromMe) {
            const customerNumber = jid.split('@')[0];
            
            // Don't lock if wife is messaging herself
            if (customerNumber === '919865204829') {
                return;
            }
            
            // ✅ FIX: Check if already locked in this session
            if (lockedConversationsCache.has(customerNumber)) {
                console.log(`🔕 Already locked ${customerNumber} in this session, skipping`);
                return;
            }
            
            console.log(`\n🔒 WIFE INTERRUPTED - Locking conversation permanently`);
            console.log(`   Customer: ${customerNumber}`);
            
            await lockConversation(customerNumber);
            
            // ✅ Add to cache to prevent duplicate locks
            lockedConversationsCache.add(customerNumber);
            
            // Remove from alerted set (wife is now handling)
            alertedCustomers.delete(customerNumber);
            
            console.log(`✅ Bot will NEVER respond to this customer again`);
            console.log(`   (Until manually unlocked)\n`);
            
            return;
        }
        
        // ===== MINIMAL IMAGE HANDLING - Just tag it for Python =====
        let messageText = '';
        
        if (message.message.imageMessage) {
            const caption = message.message.imageMessage.caption || '';
            const userId = jid.split('@')[0];
            
            console.log(`\n📸 IMAGE DETECTED from ${userId}`);
            console.log(`   Caption: "${caption}"`);
            
            // Format for Python to understand (let Python decide what to do)
            messageText = `[IMAGE_SENT]${caption ? ': ' + caption : ''}`;
            console.log(`   📦 Forwarding to Python: "${messageText}"`);
            
        } else {
            // Normal text extraction
            if (message.message.conversation) {
                messageText = message.message.conversation;
            } else if (message.message.extendedTextMessage) {
                messageText = message.message.extendedTextMessage.text;
            }
        }
        
        // Skip empty messages
        if (!messageText || messageText.trim() === '') {
            console.log('⚠️  Empty message, skipping');
            return;
        }
        
        const userId = jid.split('@')[0];
        
        console.log(`\n📨 From: ${userId}`);
        console.log(`💬 Message: ${messageText}`);
        
        // ===== REMOVED: All "pp" detection logic =====
        // ===== REMOVED: All image-specific alerts =====
        // Python will handle all business logic
        
        // ===== SMART MESSAGE BATCHING WITH DYNAMIC TIMEOUT =====
        
        // Get or create message queue for this user
        if (!userMessageQueues.has(userId)) {
            userMessageQueues.set(userId, {
                messages: [],
                timeoutId: null,
                jid: jid,
                isFirstMessage: true
            });
        }
        
        const queue = userMessageQueues.get(userId);
        
        // Add current message to queue
        queue.messages.push(messageText);
        
        // Determine timeout based on conversation state
        let timeoutDuration;
        
        if (queue.isFirstMessage) {
            // First message: Wait 60 seconds (1 minute)
            timeoutDuration = 60000;
            console.log('⏰ First message detected - waiting 60 seconds for full requirements...');
        } else {
            // Subsequent messages: Wait 10 seconds
            timeoutDuration = 10000;
            console.log('🔄 Message added to batch, resetting 10-second timer...');
        }
        
        // Clear previous timeout (if any)
        if (queue.timeoutId) {
            clearTimeout(queue.timeoutId);
        }
        
        // Set new timeout with dynamic duration
        queue.timeoutId = setTimeout(async () => {
            const messageCount = queue.messages.length;
            console.log(`⏱️  Processed after ${timeoutDuration/1000}s - ${messageCount} messages combined`);
            console.log(`\n✅ Customer stopped typing, processing ${messageCount} message(s)`);
            
            // Combine all messages
            const combinedMessage = queue.messages.join('\n');
            
            console.log(`📋 Combined message:`);
            if (combinedMessage.length > 100) {
                console.log(`   ${combinedMessage.substring(0, 100)}...`);
            } else {
                console.log(`   ${combinedMessage}`);
            }
            
            // Clear queue
            queue.messages = [];
            queue.timeoutId = null;
            
            // After processing first message, mark as no longer first
            if (queue.isFirstMessage) {
                queue.isFirstMessage = false;
                console.log('✅ First message processed - switching to 10-second timeout for subsequent messages');
            }
            
            // Forward to Python - it handles EVERYTHING
            await processMessageWithLLM(jid, combinedMessage, userId);
            
        }, timeoutDuration);
        
    } catch (error) {
        console.error('❌ Error handling message:', error);
    }
}

/**
 * Process message with LLM (separated for clarity)
 */
async function processMessageWithLLM(jid, messageText, userId) {
    try {
        // Check if LLM is enabled
        if (!USE_LLM) {
            await sendTextMessage(jid, "Our team will contact you shortly. 😊");
            console.log('⚠️  LLM disabled, sent maintenance message');
            return;
        }
        
        // Get LLM response
        const llmResponse = await chatWithLLM(messageText, userId);
        
        if (!llmResponse) {
            console.log('❌ LLM API failed - Handing off to human');
            const customerNumber = jid.split('@')[0];
            
            if (!alertedCustomers.has(customerNumber)) {
                await alertWife(customerNumber, messageText, 'BOT_ERROR');
                alertedCustomers.add(customerNumber);
                console.log(`📝 Added ${customerNumber} to alerted list`);
            } else {
                console.log(`🔕 Already alerted wife about ${customerNumber}, skipping notification`);
            }
            
            await sendTextMessage(jid, "Our team will contact you shortly. Thank you! 🙏");
            return;
        }
        
        // ===== Check if conversation is LOCKED =====
        if (llmResponse.locked) {
            console.log('🔒 Conversation is LOCKED by wife');
            console.log('🤐 Bot staying SILENT - wife is handling this customer\n');
            return;
        }

        // ===== Priority 1: Product Images with Summary =====
        if (llmResponse.reply === "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]") {
            console.log('🎯 Product image marker with summary detected!');
            console.log('🔍 DEBUG: Full llmResponse:', JSON.stringify(llmResponse, null, 2));
            
            if (llmResponse.products && llmResponse.products.length > 0) {
                const requirementsSummary = llmResponse.requirements_summary || "";
                console.log(`📸 Sending requirements summary + ${llmResponse.products.length} product images`);
                // console.log('🔍 DEBUG: Requirements summary:', requirementsSummary);
                // console.log('🔍 DEBUG: Customer requirements:', llmResponse.customer_requirements);
                // console.log('🔍 DEBUG: Handoff reason:', llmResponse.handoff_reason);
                
                // ✅ NEW: Pass requirements summary to sendProductImages
                await sendProductImages(jid, llmResponse.products, requirementsSummary);
                console.log('✅ All images sent with summary and closing message\n');
                
                // ✅ NEW: Alert wife with detailed customer requirements
                const customerNumber = jid.split('@')[0];
                if (!alertedCustomers.has(customerNumber)) {
                    console.log('🔍 DEBUG: About to call alertWife with:', {
                        customerNumber,
                        customer_requirements: llmResponse.customer_requirements,
                        handoff_reason: llmResponse.handoff_reason
                    });
                    await alertWife(customerNumber, llmResponse, 'PRODUCTS_SHOWN');
                    alertedCustomers.add(customerNumber);
                    console.log(`📝 Added ${customerNumber} to alerted list`);
                }
            } else {
                console.log('⚠️ No products found in response');
                await sendTextMessage(jid, "Let me check available options for you...");
            }
            return;
        }
        
        // ===== Priority 2: Handoff =====
        if (llmResponse.needs_handoff) {
            console.log('🚨 HUMAN HANDOFF TRIGGERED');
            
            const replyText = llmResponse.reply;
            
            if (replyText === null || replyText === undefined) {
                console.log('🔇 SILENT HANDOFF - No message to customer');
            } else {
                await sendTextMessage(jid, replyText);
                console.log('✅ Sent handoff message to customer');
            }
            
            const customerNumber = userId;
            if (!alertedCustomers.has(customerNumber)) {
                // ✅ NEW: Pass entire llmResponse to get customer_requirements and handoff_reason
                await alertWife(customerNumber, llmResponse, 'NEEDS_HELP');
                alertedCustomers.add(customerNumber);
                console.log(`📝 Added ${customerNumber} to alerted list`);
            } else {
                console.log(`🔕 Already alerted, bot staying silent\n`);
            }
            
            return;
        }
        
        // ===== Priority 3: Normal Response =====
        const replyText = llmResponse.reply;
        
        if (replyText && replyText.trim() !== '') {
            await sendTextMessage(jid, replyText);
            console.log('✅ Sent normal text response\n');
        } else {
            console.log('⚠️ Empty reply from bot');
        }
        
    } catch (error) {
        console.error('❌ Error processing message:', error);
        
        try {
            const customerNumber = jid.split('@')[0];
            const messageForAlert = messageText.substring(0, 100);
            
            if (!alertedCustomers.has(customerNumber)) {
                await alertWife(customerNumber, messageForAlert, 'BOT_ERROR');
                alertedCustomers.add(customerNumber);
                console.log(`📝 Added ${customerNumber} to alerted list`);
            } else {
                console.log(`🔕 Already alerted wife about ${customerNumber}, skipping error notification`);
            }
        } catch (alertError) {
            console.error('❌ Failed to send error alert:', alertError.message);
        }
    }
}

/**
 * Lock conversation - bot will never respond again
 */
async function lockConversation(customerNumber) {
    try {
        const axios = require('axios');
        const LLM_API_URL = process.env.LLM_API_URL;
        
        // ✅ PRODUCTION: Validate LLM_API_URL exists
        if (!LLM_API_URL) {
            console.error('❌ LLM_API_URL not configured - cannot lock conversation');
            console.error('   Please set LLM_API_URL environment variable');
            return false;
        }
        
        // ✅ PRODUCTION: Add timeout and headers
        await axios.post(`${LLM_API_URL}/lock_conversation`, {
            user_id: customerNumber
        }, {
            timeout: 10000,  // 10 second timeout
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log(`✅ Conversation permanently locked for ${customerNumber}`);
        return true;
        
    } catch (error) {
        console.error('❌ Error locking conversation:', error.message);
        
        // ✅ PRODUCTION: More detailed error logging
        if (error.code === 'ECONNABORTED') {
            console.error('   Reason: Request timeout (Python service too slow)');
        } else if (error.code === 'ECONNREFUSED') {
            console.error('   Reason: Cannot connect to Python service');
            console.error(`   Check if ${process.env.LLM_API_URL} is accessible`);
        } else if (error.response) {
            console.error(`   HTTP Status: ${error.response.status}`);
        }
        
        return false;
    }
}
/**
 * Initialize WhatsApp client
 */
async function initializeWhatsAppClient() {
    try {
        console.log('🔄 Initializing WhatsApp client...');
        
        const logger = pino({ level: 'silent' });
        
        const SUPABASE_DB_URL = process.env.SUPABASE_DB_URL;
        const IS_PRODUCTION = !!process.env.RENDER_SERVICE_NAME;

        let state, saveCreds, savePhoneNumber, clearSessionLock; // ✅ Added new functions

        if (SUPABASE_DB_URL && IS_PRODUCTION) {
            console.log('🗄️  Using Supabase for auth storage (production mode)');
            const authState = await useSupabaseAuthState(SUPABASE_DB_URL);
            state = authState.state;
            saveCreds = authState.saveCreds;
            savePhoneNumber = authState.savePhoneNumber; // ✅ NEW
            clearSessionLock = authState.clearSessionLock; // ✅ NEW
            
        } else {
            console.log('📁 Using file-based auth storage (development mode)');
            const { useMultiFileAuthState } = require('@whiskeysockets/baileys');
            const authFolder = path.join(__dirname, 'auth_info');
            
            if (!fs.existsSync(authFolder)) {
                fs.mkdirSync(authFolder, { recursive: true });
            }
            
            const fileAuth = await useMultiFileAuthState(authFolder);
            state = fileAuth.state;
            saveCreds = fileAuth.saveCreds;
            savePhoneNumber = null; // Not used in dev mode
            clearSessionLock = null;
        }
        
        console.log('✅ Auth state loaded');
        
        const { version, isLatest } = await fetchLatestBaileysVersion();
        console.log(`📡 WhatsApp Web v${version.join('.')}, Latest: ${isLatest}`);
        
        sock = makeWASocket({
            version,
            logger,
            auth: {
                creds: state.creds,
                keys: makeCacheableSignalKeyStore(state.keys, logger)
            },
            browser: ['VihaReturnGifts', 'Chrome', '10.0'],
            generateHighQualityLinkPreview: true,
            defaultQueryTimeoutMs: 60000,
            getMessage: async () => ({ conversation: 'Hi' })
        });
        
        // ✅ Handle connection updates
        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                console.log('📱 QR Code generated');
                try {
                    const qrCodeData = await QRCode.toDataURL(qr, { width: 300 });
                    updateBotState({ qrCodeData, isReady: false });
                } catch (err) {
                    console.error('❌ QR generation error:', err);
                }
            }
            
            if (connection === 'close') {
                const shouldReconnect = lastDisconnect?.error instanceof Boom ? 
                    lastDisconnect.error.output.statusCode !== DisconnectReason.loggedOut : true;
                
                console.log('❌ Connection closed:', lastDisconnect?.error?.message || 'Unknown reason');
                
                updateBotState({ isReady: false, qrCodeData: '' });
                
                const statusCode = lastDisconnect?.error instanceof Boom 
                    ? lastDisconnect.error.output.statusCode 
                    : null;
                
                // ✅ ONLY clear auth on MANUAL logout
                if (statusCode === DisconnectReason.loggedOut) {
                    console.log('🚪 User logged out manually from phone');
                    
                    // ✅ Clear session lock
                    if (clearSessionLock) {
                        await clearSessionLock();
                    }
                    
                    // Clear auth from Supabase
                    if (process.env.SUPABASE_DB_URL && process.env.RENDER_SERVICE_NAME) {
                        try {
                            const { Client } = require('pg');
                            const client = new Client({ connectionString: process.env.SUPABASE_DB_URL });
                            await client.connect();
                            await client.query('DELETE FROM whatsapp_auth WHERE id = $1', ['main_session']);
                            await client.end();
                            console.log('🧹 Auth cleared from Supabase');
                            console.log('✅ Bot is now ready for new phone number to connect');
                        } catch (error) {
                            console.error('❌ Error clearing Supabase auth:', error);
                        }
                    } else {
                        try {
                            const authFolder = path.join(__dirname, 'auth_info');
                            if (fs.existsSync(authFolder)) {
                                const files = fs.readdirSync(authFolder);
                                files.forEach(file => fs.unlinkSync(path.join(authFolder, file)));
                                console.log('🧹 Auth files cleared');
                                console.log('✅ Bot is now ready for new phone number to connect');
                            }
                        } catch (error) {
                            console.error('❌ Error clearing auth:', error);
                        }
                    }       
                    
                    setTimeout(() => initializeWhatsAppClient(), 2000);
                    
                } else if (shouldReconnect && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    console.log(`🔄 Reconnecting... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
                    updateBotState({ reconnectAttempts });
                    setTimeout(() => initializeWhatsAppClient(), 5000);
                    
                } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                    console.log('❌ Max reconnection attempts reached');
                    console.log('💡 Please restart the bot manually');
                } else {
                    console.log('⏳ Waiting for new connection...');
                }
            }
            
            // ✅ Handle successful connection
            if (connection === 'open') {
                console.log('✅ WhatsApp connected successfully!');
                
                if (savePhoneNumber && state.creds.me?.id) {
                    const phoneNumber = state.creds.me.id.split(':')[0];
                    await savePhoneNumber(phoneNumber);
                    
                    const maskedNumber = phoneNumber.replace(/(\d{2})\d{6}(\d{4})/, '$1******$2');
                    console.log(`🔒 Session locked to: +${maskedNumber}`);
                    
                    updateBotState({ 
                        isReady: true, 
                        qrCodeData: '', 
                        reconnectAttempts: 0,
                        lastConnected: new Date().toLocaleString(),
                        connectedPhone: maskedNumber  // ← KEY LINE
                    });
                } else {
                    updateBotState({ 
                        isReady: true, 
                        qrCodeData: '', 
                        reconnectAttempts: 0,
                        lastConnected: new Date().toLocaleString(),
                        connectedPhone: 'Hidden'
                    });
                }
                
                console.log('👂 Bot is now listening for messages...\n');
                
                reconnectAttempts = 0;            
            }
        });
        
        sock.ev.on('creds.update', saveCreds);
        
        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type === 'notify' && messages[0]) {
                await handleIncomingMessage(messages[0]);
            }
        });
        
        return sock;
        
    } catch (error) {
        console.error('❌ Failed to initialize WhatsApp client:', error);
        throw error;
    }
}
/**
 * Check LLM health on startup
 */
async function checkLLMOnStartup() {
    if (USE_LLM) {
        console.log('🔍 Checking LLM API health...');
        const isHealthy = await checkLLMHealth();
        if (isHealthy) {
            console.log('✅ LLM API is healthy');
        } else {
            console.log('⚠️  LLM API is not responding');
            console.log('💡 Make sure Python API is running: python bot_api.py');
        }
    }
}

/**
 * Main startup function
 */
let isInitializing = false;
let isInitialized = false;

async function main() {
    if (isInitializing || isInitialized) {
        console.log('⚠️  Initialization already in progress or complete');
        return;
    }
    
    isInitializing = true;
    
    try {
        // Start web interface
        startWebServer();
        
        // Check LLM health
        await checkLLMOnStartup();
        
        // Initialize WhatsApp
        await initializeWhatsAppClient();
        
        isInitialized = true;
        isInitializing = false;
        
    } catch (error) {
        console.error('❌ Fatal error:', error);
        isInitializing = false;
        process.exit(1);
    }
}

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('\n👋 Shutting down gracefully...');
    if (sock) {
        sock.end();
    }
    process.exit(0);
});

// ✅ Only start if run directly (not imported)
if (require.main === module) {
    main();
}