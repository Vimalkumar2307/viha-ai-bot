/**
 * VihaReturnGifts AI WhatsApp Bot v2.3
 * Main entry — WhatsApp connection + message routing
 */

require('dotenv').config();
const QRCode = require('qrcode');
const fs     = require('fs');
const path   = require('path');
const { Boom } = require('@hapi/boom');
const pino   = require('pino');
const axios  = require('axios');

// Our modules
const { chatWithLLM, checkLLMHealth, LLM_API_URL } = require('./llmClient');
const { startWebServer, updateBotState }            = require('./webInterface');
const { useSupabaseAuthState }                      = require('./authStateSupabase');
const { setSock, sendTextMessage, sendProductImages, alertWife } = require('../utils/messageHelper');
const { handleAdminCommand }                        = require('../commands/adminCommands');
const { registerScheduledJobs }                     = require('../jobs/scheduledJobs');

// Baileys
const {
    default: makeWASocket,
    DisconnectReason,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    useMultiFileAuthState
} = require('@whiskeysockets/baileys');

// ── Config ────────────────────────────────────────────────
const USE_LLM              = process.env.USE_LLM === 'true';
const MAX_RECONNECT_ATTEMPTS = 5;
const WIFE_NUMBER          = process.env.WIFE_NUMBER || '919865204829@s.whatsapp.net';
const ADMIN_PHONE          = (process.env.WIFE_NUMBER || '').split('@')[0];

// ── Wife LID ──────────────────────────────────────────────
let wifeLidJid = process.env.WIFE_LID_JID || null;
if (wifeLidJid) {
    console.log(`✅ Wife LID loaded from ENV: ${wifeLidJid}`);
} else {
    console.log(`⚠️  WIFE_LID_JID not set - will learn dynamically`);
}

function isAdminMessage(jid) {
    if (jid === WIFE_NUMBER)            return true;
    if (jid.includes(ADMIN_PHONE))      return true;
    if (wifeLidJid && jid === wifeLidJid) return true;
    return false;
}

// ── Bot state ─────────────────────────────────────────────
let sock               = null;
let reconnectAttempts  = 0;
const alertedCustomers         = new Set();
const lockedConversationsCache = new Set();
const userMessageQueues        = new Map();

// ── Startup banner ────────────────────────────────────────
console.log('='.repeat(50));
console.log('🤖 VihaReturnGifts AI WhatsApp Bot v2.3');
console.log('='.repeat(50));
console.log(`🔧 LLM Mode: ${USE_LLM ? '✅ ENABLED' : '❌ DISABLED'}`);
console.log(`🔗 LLM API: ${LLM_API_URL}`);
console.log('='.repeat(50));

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

// ── Lock conversation ─────────────────────────────────────
async function lockConversation(customerNumber) {
    try {
        await axios.post(`${process.env.LLM_API_URL}/lock_conversation`,
            { user_id: customerNumber },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );
        lockedConversationsCache.add(customerNumber);
        console.log(`✅ Conversation permanently locked for ${customerNumber}`);
        return true;
    } catch (error) {
        console.error('❌ Error locking conversation:', error.message);
        return false;
    }
}

// ── Process message with LLM ──────────────────────────────
async function processMessageWithLLM(jid, messageText, userId, pushName = '') {
    try {
        if (!USE_LLM) {
            await sendTextMessage(jid, "Our team will contact you shortly. 😊");
            return;
        }

        const llmResponse = await chatWithLLM(messageText, userId, pushName);

        if (!llmResponse) {
            console.log('❌ LLM API failed - Handing off to human');
            const customerNumber = jid.split('@')[0];
            if (!alertedCustomers.has(customerNumber)) {
                await alertWife(customerNumber, messageText, 'BOT_ERROR', pushName);
                alertedCustomers.add(customerNumber);
            }
            await sendTextMessage(jid, "Our team will contact you shortly. Thank you! 🙏");
            return;
        }

        if (llmResponse.locked) {
            console.log('🔒 Conversation LOCKED - bot staying SILENT\n');
            return;
        }

        // Priority 1: Product images
        if (llmResponse.reply === '[SEND_PRODUCT_IMAGES_WITH_SUMMARY]') {
            console.log('🎯 Product image marker detected!');
            if (llmResponse.products && llmResponse.products.length > 0) {
                const requirementsSummary = llmResponse.requirements_summary || '';
                await sendProductImages(jid, llmResponse.products, requirementsSummary);
                console.log('✅ All images sent\n');

                const customerNumber = jid.split('@')[0];
                if (!alertedCustomers.has(customerNumber)) {
                    alertedCustomers.add(customerNumber);
                    // Wait 5 seconds for session to stabilize before alerting wife
                    setTimeout(async () => {
                        await alertWife(customerNumber, llmResponse, 'PRODUCTS_SHOWN', pushName);
                    }, 5000);
                }
            } else {
                await sendTextMessage(jid, "Let me check available options for you...");
            }
            return;
        }

        // Priority 2: Handoff
        if (llmResponse.needs_handoff) {
            console.log('🚨 HUMAN HANDOFF TRIGGERED');
            const replyText = llmResponse.reply;
            if (replyText !== null && replyText !== undefined) {
                await sendTextMessage(jid, replyText);
            } else {
                console.log('🔇 SILENT HANDOFF');
            }

            const customerNumber = userId;
            if (!alertedCustomers.has(customerNumber)) {
                await alertWife(customerNumber, llmResponse, 'NEEDS_HELP', pushName);
                alertedCustomers.add(customerNumber);
            } else {
                console.log(`🔕 Already alerted, bot staying silent\n`);
            }
            return;
        }

        // Priority 3: Normal response
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
            if (!alertedCustomers.has(customerNumber)) {
                await alertWife(customerNumber, { last_message: messageText.substring(0, 100) }, 'BOT_ERROR');
                alertedCustomers.add(customerNumber);
            }
        } catch (alertError) {
            console.error('❌ Failed to send error alert:', alertError.message);
        }
    }
}

// ── Handle incoming message ───────────────────────────────
async function handleIncomingMessage(message) {
    try {
        const jid       = message.key.remoteJid;
        const isFromMe  = message.key.fromMe;

        console.log(`\n${'='.repeat(70)}`);
        console.log(`📨 INCOMING MESSAGE DEBUG`);
        console.log(`   JID: "${jid}"`);
        console.log(`   isFromMe: ${isFromMe}`);
        console.log(`   isAdminMessage: ${isAdminMessage(jid)}`);
        console.log(`${'='.repeat(70)}\n`);

        // Skip groups and broadcasts
        if (jid.includes('@g.us') || jid.includes('status@broadcast')) return;

        // Skip messages without content (reactions, receipts, notifications)
        if (!message.message) {
            console.log('⚠️ No message content — skipping');
            return;
        }

        // ── Admin commands ────────────────────────────────
        if (isAdminMessage(jid) && !isFromMe) {

            // Dynamic LID learning
            if (jid.includes('@lid')) {
                if (!wifeLidJid) {
                    wifeLidJid = jid;
                    console.log(`✅ Learned wife's LID JID: ${wifeLidJid}`);
                    console.log(`   💡 Add to Render ENV: WIFE_LID_JID=${wifeLidJid}`);
                } else if (jid !== wifeLidJid) {
                    console.log(`⚠️  Wife's LID CHANGED! Old: ${wifeLidJid} → New: ${jid}`);
                    console.log(`   ⚠️  Update WIFE_LID_JID in Render ENV to: ${jid}`);
                    wifeLidJid = jid;
                }
            }

            console.log(`✅ MESSAGE FROM WIFE DETECTED`);

            let messageText = '';
            if (message.message?.conversation) {
                messageText = message.message.conversation;
            } else if (message.message?.extendedTextMessage?.text) {
                messageText = message.message.extendedTextMessage.text;
            }

            const msg      = messageText.trim();
            const msgUpper = msg.toUpperCase();

            console.log(`   Original: "${msg}"`);
            console.log(`   Uppercase: "${msgUpper}"`);

            if (!msg || msg === '') {
                console.log('⚠️ Empty admin message — skipping');
                return;
            }

            await handleAdminCommand(msgUpper, msg, jid, alertedCustomers, lockedConversationsCache);
            return;
        }

        // ── Wife sent message to customer → lock ──────────
        if (isFromMe) {
            const customerNumber = jid.split('@')[0];
            if (isAdminMessage(jid)) return;

            // Skip bot's own number to prevent self-locking
            const BOT_NUMBER = process.env.BOT_NUMBER || '';
            if (BOT_NUMBER && customerNumber === BOT_NUMBER) {
                console.log('⚠️ Skipping — bot own number, not a customer');
                return;
            }

            if (lockedConversationsCache.has(customerNumber)) {
                console.log(`🔕 Already locked ${customerNumber} in this session, skipping`);
                return;
            }

            console.log(`\n🔒 WIFE INTERRUPTED - Locking conversation permanently`);
            console.log(`   Customer: ${customerNumber}`);

            await lockConversation(customerNumber);
            lockedConversationsCache.add(customerNumber);
            alertedCustomers.delete(customerNumber);

            console.log(`✅ Bot will NEVER respond to this customer again (Until unlocked)\n`);
            return;
        }

        // ── Customer message ──────────────────────────────
        let messageText = '';

        if (message.message.imageMessage) {
            const caption = message.message.imageMessage.caption || '';
            const userId  = jid.split('@')[0];
            console.log(`\n📸 IMAGE DETECTED from ${userId}, Caption: "${caption}"`);
            messageText = `[IMAGE_SENT]${caption ? ': ' + caption : ''}`;
        } else {
            if (message.message.conversation) {
                messageText = message.message.conversation;
            } else if (message.message.extendedTextMessage) {
                messageText = message.message.extendedTextMessage.text;
            }
        }

        if (!messageText || messageText.trim() === '') {
            console.log('⚠️  Empty message, skipping');
            return;
        }

        const userId = jid.split('@')[0];
        console.log(`\n📨 From: ${userId}`);
        console.log(`💬 Message: ${messageText}`);

        // ── Smart message batching ────────────────────────
        if (!userMessageQueues.has(userId)) {
            userMessageQueues.set(userId, {
                messages: [], timeoutId: null, jid: jid,
                isFirstMessage: true, pushName: message.pushName || ''
            });
        }

        const queue          = userMessageQueues.get(userId);
        const timeoutDuration = queue.isFirstMessage ? 60000 : 10000;

        queue.messages.push(messageText);

        if (queue.isFirstMessage) {
            console.log('⏰ First message - waiting 60 seconds for full requirements...');
        } else {
            console.log('🔄 Message added to batch, resetting 10-second timer...');
        }

        if (queue.timeoutId) clearTimeout(queue.timeoutId);

        queue.timeoutId = setTimeout(async () => {
            const messageCount    = queue.messages.length;
            const combinedMessage = queue.messages.join('\n');

            console.log(`⏱️  Processed after ${timeoutDuration/1000}s - ${messageCount} messages combined`);
            console.log(`📋 Combined: ${combinedMessage.length > 100 ? combinedMessage.substring(0, 100) + '...' : combinedMessage}`);

            queue.messages  = [];
            queue.timeoutId = null;

            if (queue.isFirstMessage) {
                queue.isFirstMessage = false;
                console.log('✅ Switching to 10-second timeout for subsequent messages');
            }

            await processMessageWithLLM(jid, combinedMessage, userId, queue.pushName);
        }, timeoutDuration);

    } catch (error) {
        console.error('❌ Error handling message:', error);
    }
}

// ── WhatsApp client ───────────────────────────────────────
async function initializeWhatsAppClient() {
    try {
        console.log('🔄 Initializing WhatsApp client...');

        const logger = pino({ level: 'silent' });
        
        const SUPABASE_DB_URL = process.env.SUPABASE_DB_URL;
        const IS_PRODUCTION = !!process.env.RENDER_SERVICE_NAME;

        let state, saveCreds, savePhoneNumber, clearSessionLock;

        if (SUPABASE_DB_URL && IS_PRODUCTION) {
            console.log('🗄️  Using Supabase for auth storage (production mode)');
            const authState   = await useSupabaseAuthState(SUPABASE_DB_URL);
            state             = authState.state;
            saveCreds         = authState.saveCreds;
            savePhoneNumber   = authState.savePhoneNumber;
            clearSessionLock  = authState.clearSessionLock;
        } else {
            console.log('📁 Using file-based auth storage (development mode)');
            const authFolder = path.join(__dirname, 'auth_info');
            if (!fs.existsSync(authFolder)) fs.mkdirSync(authFolder, { recursive: true });
            const fileAuth   = await useMultiFileAuthState(authFolder);
            state            = fileAuth.state;
            saveCreds        = fileAuth.saveCreds;
            savePhoneNumber  = null;
            clearSessionLock = null;
        }

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
            getMessage: async (key) => {
                return undefined;
            }
        });

        // Inject sock into messageHelper
        setSock(sock);

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
                const statusCode = lastDisconnect?.error instanceof Boom
                    ? lastDisconnect.error.output.statusCode : null;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

                console.log('❌ Connection closed:', lastDisconnect?.error?.message || 'Unknown reason');
                updateBotState({ isReady: false, qrCodeData: '' });

                if (statusCode === DisconnectReason.loggedOut) {
                    console.log('🚪 User logged out manually from phone');
                    if (clearSessionLock) await clearSessionLock();

                    if (process.env.SUPABASE_DB_URL && process.env.RENDER_SERVICE_NAME) {
                        try {
                            const { Client } = require('pg');
                            const client = new Client({ connectionString: process.env.SUPABASE_DB_URL });
                            await client.connect();
                            await client.query('DELETE FROM whatsapp_auth WHERE id = $1', ['main_session']);
                            await client.end();
                            console.log('🧹 Auth cleared from Supabase');
                        } catch (error) {
                            console.error('❌ Error clearing Supabase auth:', error);
                        }
                    } else {
                        try {
                            const authFolder = path.join(__dirname, 'auth_info');
                            if (fs.existsSync(authFolder)) {
                                fs.readdirSync(authFolder).forEach(file => fs.unlinkSync(path.join(authFolder, file)));
                                console.log('🧹 Auth files cleared');
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
                    const delay = Math.min(5000 * reconnectAttempts, 30000);
                    setTimeout(async () => {
                        try {
                            await initializeWhatsAppClient();
                        } catch (err) {
                            console.error(`⚠️ Reconnect attempt ${reconnectAttempts} failed: ${err.message} — will retry`);
                        }
                    }, delay);
                 } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                    console.log('❌ Max reconnection attempts reached. Retrying in 5 minutes...');
                    reconnectAttempts = 0;
                    setTimeout(async () => {
                        try {
                            await initializeWhatsAppClient();
                        } catch (err) {
                            console.error('⚠️ Auto-recovery failed:', err.message);
                        }
                    }, 5 * 60 * 1000);
                } else {
                    console.log('⏳ Waiting for new connection...');
                }
            }

           if (connection === 'open') {
                console.log('✅ WhatsApp connected successfully!');
                setSock(sock);
                registerScheduledJobs();
                alertedCustomers.clear();
                console.log('🔄 Cleared alerted customers cache on reconnect');

                if (savePhoneNumber && state.creds.me?.id) {
                    const phoneNumber  = state.creds.me.id.split(':')[0];
                    await savePhoneNumber(phoneNumber);
                    const maskedNumber = phoneNumber.replace(/(\d{2})\d{6}(\d{4})/, '$1******$2');
                    console.log(`🔒 Session locked to: +${maskedNumber}`);
                    updateBotState({ isReady: true, qrCodeData: '', reconnectAttempts: 0, lastConnected: new Date().toLocaleString(), connectedPhone: maskedNumber });
                } else {
                    updateBotState({ isReady: true, qrCodeData: '', reconnectAttempts: 0, lastConnected: new Date().toLocaleString(), connectedPhone: 'Hidden' });
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

async function checkLLMOnStartup() {
    if (USE_LLM) {
        console.log('🔍 Checking LLM API health...');
        const isHealthy = await checkLLMHealth();
        console.log(isHealthy ? '✅ LLM API is healthy' : '⚠️  LLM API is not responding');
    }
}

// ── Main ──────────────────────────────────────────────────
let isInitializing = false;
let isInitialized  = false;

async function main() {
    if (isInitializing || isInitialized) {
        console.log('⚠️  Initialization already in progress or complete');
        return;
    }

    isInitializing = true;

    try {
        startWebServer();
        await checkLLMOnStartup();
        await initializeWhatsAppClient();
        // registerScheduledJobs() is called inside initializeWhatsAppClient on 'open' event

        isInitialized  = true;
        isInitializing = false;
    } catch (error) {
        console.error('❌ Fatal startup error:', error.message);
        isInitializing = false;
        console.log('🔄 Retrying startup in 15 seconds...');
        setTimeout(() => {
            isInitializing = false;
            isInitialized = false;
            main();
        }, 15000);
    }
}

process.on('SIGINT', () => {
    console.log('\n👋 Shutting down gracefully...');
    if (sock) sock.end();
    process.exit(0);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('⚠️ Unhandled rejection (caught):', reason?.message || reason);
    // Don't crash — just log it
});

process.on('uncaughtException', (error) => {
    console.error('⚠️ Uncaught exception (caught):', error.message);
    // Don't crash — just log it
});

if (require.main === module) {
    main();
}