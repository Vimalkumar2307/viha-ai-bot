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
const axios = require('axios');
const cron = require('node-cron');

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
const ADMIN_PHONE = (process.env.WIFE_NUMBER || '').split('@')[0]; // 919865204829

// ✅ Load wife's LID from ENV (primary), fallback to dynamic learning
let wifeLidJid = process.env.WIFE_LID_JID || null;

if (wifeLidJid) {
    console.log(`✅ Wife LID loaded from ENV: ${wifeLidJid}`);
} else {
    console.log(`⚠️  WIFE_LID_JID not set - will learn dynamically on first message from wife`);
}

function isAdminMessage(jid) {
    if (jid === WIFE_NUMBER) return true;
    if (jid.includes(ADMIN_PHONE)) return true;
    if (wifeLidJid && jid === wifeLidJid) return true;
    return false;
}

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

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

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

async function sendImageMessage(jid, imageUrl, caption) {
    try {
        if (!imageUrl || imageUrl.trim() === '') {
            console.log('⚠️ No image URL provided, sending text only');
            return await sendTextMessage(jid, caption);
        }
        console.log(`📸 Attempting to send image: ${imageUrl.substring(0, 50)}...`);
        await sock.sendMessage(jid, { image: { url: imageUrl }, caption: caption });
        console.log(`✅ Image sent successfully`);
        return true;
    } catch (error) {
        console.error('❌ Error sending image:', error.message);
        const fallbackMsg = `${caption}\n\n(Image temporarily unavailable)`;
        console.log('⚠️ Falling back to text-only message');
        return await sendTextMessage(jid, fallbackMsg);
    }
}

async function sendProductImages(jid, products, requirementsSummary) {
    try {
        console.log(`📸 Sending requirements summary + ${products.length} product images...`);
        if (requirementsSummary) {
            await sendTextMessage(jid, requirementsSummary);
            await sleep(1000);
        }
        for (let i = 0; i < products.length; i++) {
            const product = products[i];
            const caption = `${i + 1}. ${product.name}\n₹${product.price}/piece`;
            await sendImageMessage(jid, product.image_url, caption);
            if (i < products.length - 1) await sleep(800);
        }
        await sleep(1000);
        await sendTextMessage(jid, "Please let us know which one you are interested. We can proceed further.");
        console.log(`✅ Sent all ${products.length} product images with summary and closing message`);
        console.log(`🤝 Conversation handed off to human`);
        return true;
    } catch (error) {
        console.error('❌ Error sending product images:', error.message);
        return false;
    }
}

async function alertWife(customerNumber, llmResponse, reason = 'NEEDS_HELP', pushName = '') {
    try {
        let alertMessage = '';

        if (reason === 'NEEDS_HELP' || reason === 'PRODUCTS_SHOWN') {
            alertMessage = `🔔 *CUSTOMER NEEDS HELP*\n\n`;
            alertMessage += `Customer: +${customerNumber}\n`;
            alertMessage += pushName ? `Name: ${pushName}\n\n` : `\n`;

            if (llmResponse.customer_requirements) {
                const req = llmResponse.customer_requirements;
                alertMessage += `📋 *Customer Requirements:*\n`;
                if (req.quantity) alertMessage += `Quantity: ${req.quantity} pieces\n`;
                if (req.budget_per_piece) alertMessage += `Budget: ₹${req.budget_per_piece} per piece\n`;
                if (req.location) alertMessage += `Location: ${req.location}\n`;
                if (req.timeline) alertMessage += `When needed: ${req.timeline}\n`;
                alertMessage += `\n`;
            }

            if (llmResponse.handoff_reason) alertMessage += `${llmResponse.handoff_reason}\n\n`;

            alertMessage += `Please follow up with this customer.\n\n`;
            alertMessage += `━━━━━━━━━━━━━━━━━━\n`;
            alertMessage += `💡 *Quick Actions:*\n`;
            alertMessage += `\n💡 *To reset this chat, reply:*\n`;
            alertMessage += `RESET ${customerNumber}\n\n`;
            alertMessage += `*To unlock chat, reply:*\n`;
            alertMessage += `UNLOCK ${customerNumber}`;
            alertMessage += `\nThank you! 🙏`;

        } else if (reason === 'BOT_ERROR') {
            alertMessage = `⚠️ *BOT ERROR - CUSTOMER NEEDS HELP*\n\n`;
            alertMessage += `Customer: +${customerNumber}\n\n`;
            if (llmResponse.handoff_reason) alertMessage += `${llmResponse.handoff_reason}\n\n`;
            if (llmResponse.last_message) alertMessage += `Last Message:\n"${llmResponse.last_message}"\n\n`;
            alertMessage += `Bot failed to respond. Please take over immediately.`;
        }

        await sendTextMessage(WIFE_NUMBER, alertMessage);
        console.log('✅ Alert sent to wife');
        console.log(`📋 Customer: +${customerNumber}`);
        return true;
    } catch (error) {
        console.error('❌ Failed to send alert to wife:', error.message);
        return false;
    }
}

// Track alerted customers to prevent spam
const alertedCustomers = new Set();

// Track locked conversations in this session
const lockedConversationsCache = new Set();

// Store pending messages for each user
const userMessageQueues = new Map();

/**
 * Parse date range from admin command message
 * Supports:
 *   "SUMMARY"              → today
 *   "SUMMARY 7"            → last 7 days
 *   "SUMMARY 12/02 19/02"  → date range
 *   "SUMMARY 12/02/2026 19/02/2026" → date range with year
 */
function parseDateRange(parts) {
    const today = new Date();

    const formatDate = (d) => d.toISOString().split('T')[0]; // "2026-02-19"

    const parseDate = (str) => {
        // Handle dd/mm or dd/mm/yyyy
        const parts = str.split('/');
        if (parts.length >= 2) {
            const day   = parseInt(parts[0]);
            const month = parseInt(parts[1]) - 1;
            const year  = parts[2] ? parseInt(parts[2]) : today.getFullYear();
            return new Date(year, month, day);
        }
        return null;
    };

    // No argument → today
    if (parts.length === 1) {
        return {
            start_date: formatDate(today),
            end_date:   formatDate(today),
            label:      `Today (${today.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })})`
        };
    }

    // Single number → last N days
    if (parts.length === 2 && !isNaN(parts[1])) {
        const days  = parseInt(parts[1]);
        const start = new Date(today);
        start.setDate(today.getDate() - (days - 1));
        return {
            start_date: formatDate(start),
            end_date:   formatDate(today),
            label:      `Last ${days} day(s)`
        };
    }

    // Single date → that day only
    if (parts.length === 2 && parts[1].includes('/')) {
        const date = parseDate(parts[1]);
        if (date && !isNaN(date)) {
            return {
                start_date: formatDate(date),
                end_date:   formatDate(date),
                label:      parts[1]
            };
        }
        return { error: `❌ Invalid date format.\n\nCorrect formats:\nSUMMARY 19/02 → single day\nSUMMARY 12/02 19/02 → date range\nSUMMARY 7 → last 7 days` };
    }

    // Two dates → date range
    // Two dates → date range
    if (parts.length === 3) {
        const start = parseDate(parts[1]);
        const end   = parseDate(parts[2]);
        if (start && end && !isNaN(start) && !isNaN(end)) {
            if (end < start) {
                return { error: `❌ End date cannot be before start date.\n\nCorrect format:\nSUMMARY 12/02 19/02` };
            }
            return {
                start_date: formatDate(start),
                end_date:   formatDate(end),
                label:      `${parts[1]} to ${parts[2]}`
            };
        }
        // Invalid date format
        return { error: `❌ Invalid date format.\n\nCorrect formats:\nSUMMARY → today\nSUMMARY 7 → last 7 days\nSUMMARY 12/02 19/02 → date range\nSUMMARY 12/02/2026 19/02/2026 → with year` };
    }

    // Unknown format
    if (parts.length > 1) {
        return { error: `❌ Invalid format.\n\nCorrect formats:\nSUMMARY → today\nSUMMARY 7 → last 7 days\nSUMMARY 12/02 19/02 → date range` };
    }

    // Fallback → today
    return {
        start_date: formatDate(today),
        end_date:   formatDate(today),
        label:      'Today'
    };
}

async function handleIncomingMessage(message) {
    try {
        const jid = message.key.remoteJid;
        const isFromMe = message.key.fromMe;

        console.log(`\n${'='.repeat(70)}`);
        console.log(`📨 INCOMING MESSAGE DEBUG`);
        console.log(`   JID: "${jid}"`);
        console.log(`   isFromMe: ${isFromMe}`);
        console.log(`   WIFE_NUMBER: "${process.env.WIFE_NUMBER}"`);
        console.log(`   isAdminMessage: ${isAdminMessage(jid)}`);
        console.log(`   wifeLidJid: "${wifeLidJid}"`);
        console.log(`   !isFromMe: ${!isFromMe}`);
        console.log(`${'='.repeat(70)}\n`);

        // Skip groups and status broadcasts
        if (jid.includes('@g.us') || jid.includes('status@broadcast')) return;

        const ADMIN_NUMBER = process.env.WIFE_NUMBER;

        // ═══════════════════════════════════════════════════════════════
        // ADMIN COMMANDS
        // ═══════════════════════════════════════════════════════════════

        if (isAdminMessage(jid) && !isFromMe) {

            // ✅ Dynamic LID learning / change detection
            if (jid.includes('@lid')) {
                if (!wifeLidJid) {
                    // First time learning
                    wifeLidJid = jid;
                    console.log(`✅ Learned wife's LID JID: ${wifeLidJid}`);
                    console.log(`   💡 Add to Render ENV: WIFE_LID_JID=${wifeLidJid}`);
                } else if (jid !== wifeLidJid) {
                    // LID changed
                    console.log(`⚠️  Wife's LID CHANGED!`);
                    console.log(`   Old LID: ${wifeLidJid}`);
                    console.log(`   New LID: ${jid}`);
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

            const msg = messageText.trim();
            const msgUpper = msg.toUpperCase();

            console.log(`   Original: "${msg}"`);
            console.log(`   Uppercase: "${msgUpper}"`);

            // RESET COMMAND
            if (msgUpper.startsWith('RESET ') || msgUpper.startsWith('/RESET ')) {
                console.log(`✅✅✅ RESET COMMAND MATCHED!`);
                const customerNumber = msg.replace(/RESET\s+/i, '').replace(/\/RESET\s+/i, '').trim();

                console.log(`🔧 ADMIN: Reset conversation for ${customerNumber}`);

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/reset_conversation`,
                        { user_id: customerNumber },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    alertedCustomers.delete(customerNumber);
                    lockedConversationsCache.delete(customerNumber);

                    await sendTextMessage(jid,
                        `✅ Conversation reset successful!\n\n` +
                        `Customer: +${customerNumber}\n` +
                        `Deleted: ${response.data.deleted_checkpoints || 0} checkpoints\n\n` +
                        `Bot will start fresh on next message.`
                    );

                    console.log(`✅ Reset completed for ${customerNumber}\n`);
                } catch (error) {
                    console.error(`❌ Reset failed:`, error.message);
                    await sendTextMessage(jid, `❌ Reset failed: ${error.message}`);
                }
                return;
            }

            // UNLOCK COMMAND
            if (msgUpper.startsWith('UNLOCK ') || msgUpper.startsWith('/UNLOCK ')) {
                console.log(`✅✅✅ UNLOCK COMMAND MATCHED!`);
                const customerNumber = msg.replace(/UNLOCK\s+/i, '').replace(/\/UNLOCK\s+/i, '').trim();

                try {
                    await axios.post(
                        `${process.env.LLM_API_URL}/unlock_conversation`,
                        { user_id: customerNumber },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    alertedCustomers.delete(customerNumber);
                    lockedConversationsCache.delete(customerNumber);

                    await sendTextMessage(jid,
                        `✅ Conversation unlocked!\n\n` +
                        `Customer: +${customerNumber}\n` +
                        `Bot can now respond.`
                    );

                    console.log(`✅ Unlocked for ${customerNumber}\n`);
                } catch (error) {
                    console.error(`❌ Unlock failed:`, error.message);
                    await sendTextMessage(jid, `❌ Unlock failed: ${error.message}`);
                }
                return;
            }

            // LOCK COMMAND
            if (msgUpper.startsWith('LOCK ') || msgUpper.startsWith('/LOCK ')) {
                console.log(`✅✅✅ LOCK COMMAND MATCHED!`);
                
                const customerNumber = msg.replace(/LOCK\s+/i, '').replace(/\/LOCK\s+/i, '').trim();
                
                try {
                    await axios.post(
                        `${process.env.LLM_API_URL}/lock_conversation`,
                        { user_id: customerNumber },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );
                    
                    lockedConversationsCache.add(customerNumber);
                    alertedCustomers.add(customerNumber);
                    
                    await sendTextMessage(jid,
                        `🔒 Conversation locked!\n\n` +
                        `Contact: +${customerNumber}\n` +
                        `Bot will stay silent.\n\n` +
                        `To re-enable: UNLOCK ${customerNumber}`
                    );
                    
                    console.log(`✅ Locked for ${customerNumber}\n`);
                    
                } catch (error) {
                    console.error(`❌ Lock failed:`, error.message);
                    await sendTextMessage(jid, `❌ Lock failed: ${error.message}`);
                }
                return;
            }

            // LEADS COMMAND
            if (msgUpper.startsWith('LEADS ') || msgUpper === 'LEADS') {
                console.log(`✅✅✅ LEADS COMMAND MATCHED!`);
                
                // Extract days number (default 7)
                const parts = msg.trim().split(/\s+/);
                const days = parts[1] && !isNaN(parts[1]) ? parseInt(parts[1]) : 7;
                
                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/leads`,
                        { days: days },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );
                    
                    const data = response.data;
                    
                    if (data.total === 0) {
                        await sendTextMessage(jid, `📋 No leads in the last ${days} day(s).`);
                        return;
                    }
                    
                    // Format leads message
                    let leadsMsg = `📋 *Leads - Last ${days} day(s)*\n`;
                    leadsMsg += `Total: ${data.total}\n`;
                    leadsMsg += `━━━━━━━━━━━━━━━━━━\n\n`;
                    
                    data.leads.forEach((lead, index) => {
                        leadsMsg += `${index + 1}. +${lead.customer_number}\n`;
                        if (lead.quantity)  leadsMsg += `   Qty: ${lead.quantity} pcs\n`;
                        if (lead.budget)    leadsMsg += `   Budget: ${lead.budget}/pc\n`;
                        if (lead.location)  leadsMsg += `   Location: ${lead.location}\n`;
                        if (lead.timeline)  leadsMsg += `   When: ${lead.timeline}\n`;
                        leadsMsg += `   Status: ${lead.status}\n`;
                        leadsMsg += `   Last active: ${lead.updated_at}\n\n`;
                    });
                    
                    leadsMsg += `💡 INFO <number> for full details`;
                    
                    await sendTextMessage(jid, leadsMsg);
                    console.log(`✅ Leads sent for last ${days} days\n`);
                    
                } catch (error) {
                    console.error(`❌ Leads fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch leads: ${error.message}`);
                }
                return;
            }

            // SUMMARY COMMAND
            if (msgUpper.startsWith('SUMMARY') || msgUpper === 'SUMMARY') {
                console.log(`✅✅✅ SUMMARY COMMAND MATCHED!`);

                const parts = msg.trim().split(/\s+/);
                const dateRange = parseDateRange(parts);

                if (dateRange.error) {
                    await sendTextMessage(jid, dateRange.error);
                    return;
                }

                const { start_date, end_date, label } = dateRange;

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/summary`,
                        { start_date, end_date },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    const d = response.data;

                    if (d.status === 'error') {
                        await sendTextMessage(jid, `❌ Summary failed: ${d.message}`);
                        return;
                    }

                    // ── Overview section ──
                    let summaryMsg = `📊 *Summary - ${label}*\n\n`;
                    summaryMsg += `📥 New Leads: ${d.total}\n`;
                    summaryMsg += `📸 Products Shown: ${d.products_shown}\n`;
                    summaryMsg += `⚠️  Follow-up Pending: ${d.followup_pending}\n`;
                    summaryMsg += `🔒 Wife Handling: ${d.locked}\n`;
                    summaryMsg += `⏳ Incomplete: ${d.incomplete}\n\n`;

                    summaryMsg += `📍 Top Locations: ${d.top_locations}\n`;

                    // ── Lead details section ──
                    if (d.leads && d.leads.length > 0) {
                        summaryMsg += `\n━━━━━━━━━━━━━━━━━━\n`;
                        summaryMsg += `📋 *Lead Details:*\n\n`;

                        d.leads.forEach((lead, index) => {
                            const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
                            const budget   = lead.budget   ? `₹${lead.budget}/pc`   : 'Budget ?';
                            const when     = lead.timeline || 'Date ?';
                            const location = lead.location || 'Location ?';
                            const name = lead.push_name ? ` (${lead.push_name})` : '';
                            summaryMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
                            summaryMsg += `   ${qty} | ${budget} | ${when} | ${location}\n`;
                        });
                    } else {
                        summaryMsg += `\n━━━━━━━━━━━━━━━━━━\n`;
                        summaryMsg += `No leads found for this period.\n`;
                    }

                    summaryMsg += `━━━━━━━━━━━━━━━━━━\n`;
                    summaryMsg += `💡 FOLLOWUP for pending list\n`;
                    summaryMsg += `💡 HOTLEADS for big orders`;

                    await sendTextMessage(jid, summaryMsg);
                    console.log(`✅ Summary sent for ${label}\n`);

                } catch (error) {
                    console.error(`❌ Summary failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch summary: ${error.message}`);
                }
                return;
            }

            // PENDING COMMAND
            if (msgUpper.startsWith('PENDING') || msgUpper === 'PENDING') {
                console.log(`✅✅✅ PENDING COMMAND MATCHED!`);

                const parts = msg.trim().split(/\s+/);
                const dateRange = parseDateRange(parts);

                if (dateRange.error) {
                    await sendTextMessage(jid, dateRange.error);
                    return;
                }

                const { start_date, end_date, label } = dateRange;

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/pending`,
                        { start_date, end_date },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    const d = response.data;

                    if (d.status === 'error') {
                        await sendTextMessage(jid, `❌ Pending fetch failed: ${d.message}`);
                        return;
                    }

                    if (d.total === 0) {
                        await sendTextMessage(jid,
                            `⏳ No pending leads for ${label}.`
                        );
                        return;
                    }

                    let pendingMsg = `⏳ *Pending - ${label}*\n`;
                    pendingMsg += `Total: ${d.total}\n`;
                    pendingMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

                    d.leads.forEach((lead, index) => {
                        const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
                        const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
                        const when     = lead.timeline || 'Date ?';
                        const location = lead.location || 'Location ?';
                        const missing  = lead.missing.length > 0
                            ? `Missing: ${lead.missing.join(', ')}`
                            : 'All details collected';

                        const name = lead.push_name ? ` (${lead.push_name})` : '';
                        pendingMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
                        pendingMsg += `   ${qty} | ${budget} | ${when} | ${location}\n`;
                        pendingMsg += `   ⚠️ ${missing}\n\n`;
                    });

                    pendingMsg += `━━━━━━━━━━━━━━━━━━\n`;
                    pendingMsg += `💡 RESET <number> to restart conversation`;

                    await sendTextMessage(jid, pendingMsg);
                    console.log(`✅ Pending sent for ${label}\n`);

                } catch (error) {
                    console.error(`❌ Pending fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch pending: ${error.message}`);
                }
                return;
            }

            // FOLLOWUP COMMAND
            if (msgUpper.startsWith('FOLLOWUP') || msgUpper === 'FOLLOWUP') {
                console.log(`✅✅✅ FOLLOWUP COMMAND MATCHED!`);

                const parts = msg.trim().split(/\s+/);

                // Check if second argument is silent_days (single number)
                // FOLLOWUP 2 → silent for 2+ days (no date filter)
                let silent_days = 1;
                let dateRange;

                if (parts.length === 2 && !isNaN(parts[1]) && !parts[1].includes('/')) {
                    // FOLLOWUP 2 → last N silent days, today's date range
                    silent_days = parseInt(parts[1]);
                    dateRange = parseDateRange([parts[0]]); // today
                } else {
                    // FOLLOWUP / FOLLOWUP 19/02 / FOLLOWUP 12/02 19/02
                    dateRange = parseDateRange(parts);
                }

                if (dateRange.error) {
                    await sendTextMessage(jid, dateRange.error);
                    return;
                }

                const { start_date, end_date, label } = dateRange;

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/followup`,
                        { start_date, end_date, silent_days },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    const d = response.data;

                    if (d.status === 'error') {
                        await sendTextMessage(jid, `❌ Followup fetch failed: ${d.message}`);
                        return;
                    }

                    if (d.total === 0) {
                        await sendTextMessage(jid,
                            `✅ No follow-ups needed for ${label}.`
                        );
                        return;
                    }

                    let followupMsg = `⚠️ *Follow-up Needed - ${label}*\n`;
                    followupMsg += `Total: ${d.total}\n`;
                    followupMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

                    d.leads.forEach((lead, index) => {
                        const qty      = lead.quantity ? `${lead.quantity} pcs`  : 'Qty ?';
                        const budget   = lead.budget   ? `${lead.budget}/pc`     : 'Budget ?';
                        const when     = lead.timeline || 'Date ?';
                        const location = lead.location || 'Location ?';
                        const silent   = lead.silent_for === 0
                            ? 'today'
                            : lead.silent_for === 1
                                ? '1 day ago'
                                : `${lead.silent_for} days ago`;

                        const name = lead.push_name ? ` (${lead.push_name})` : '';
                        followupMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
                        followupMsg += `   ${qty} | ${budget} | ${when} | ${location}\n`;
                        followupMsg += `   🔕 Silent for: ${silent}\n\n`;
                    });

                    followupMsg += `━━━━━━━━━━━━━━━━━━\n`;
                    followupMsg += `💡 LOCK <number> to silence bot\n`;
                    followupMsg += `💡 RESET <number> to restart conversation`;

                    await sendTextMessage(jid, followupMsg);
                    console.log(`✅ Followup sent for ${label}\n`);

                } catch (error) {
                    console.error(`❌ Followup fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch followup: ${error.message}`);
                }
                return;
            }

            // HOTLEADS COMMAND
            if (msgUpper.startsWith('HOTLEADS') || msgUpper === 'HOTLEADS') {
                console.log(`✅✅✅ HOTLEADS COMMAND MATCHED!`);

                const parts = msg.trim().split(/\s+/);

                // Parse min_quantity and date range
                // HOTLEADS              → qty≥100, last 7 days
                // HOTLEADS 50           → qty≥50,  last 7 days
                // HOTLEADS 50 7         → qty≥50,  last 7 days
                // HOTLEADS 50 19/02     → qty≥50,  single day
                // HOTLEADS 50 12/02 19/02 → qty≥50, date range

                let min_quantity = 100;
                let dateRangeParts = [parts[0]]; // default → no date args

                if (parts.length >= 2 && !isNaN(parts[1]) && !parts[1].includes('/')) {
                    // Second arg is quantity threshold
                    min_quantity = parseInt(parts[1]);

                    if (parts.length >= 3) {
                        // Remaining args are date range
                        dateRangeParts = [parts[0], ...parts.slice(2)];
                    }
                    // else: no date args → default last 7 days
                } else if (parts.length >= 2) {
                    // No quantity arg, date args start from index 1
                    dateRangeParts = parts;
                }

                const dateRange = parseDateRange(dateRangeParts);

                if (dateRange.error) {
                    await sendTextMessage(jid, dateRange.error);
                    return;
                }

                const { start_date, end_date, label } = dateRange;

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/hotleads`,
                        { start_date, end_date, min_quantity },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    const d = response.data;

                    if (d.status === 'error') {
                        await sendTextMessage(jid, `❌ Hotleads fetch failed: ${d.message}`);
                        return;
                    }

                    if (d.total === 0) {
                        await sendTextMessage(jid,
                            `🔥 No hot leads (≥${min_quantity} pcs) for ${label}.`
                        );
                        return;
                    }

                    let hotMsg = `🔥 *Hot Leads - ${label} (≥${min_quantity} pcs)*\n`;
                    hotMsg += `Total: ${d.total}\n`;
                    hotMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

                    d.leads.forEach((lead, index) => {
                        const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
                        const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
                        const when     = lead.timeline || 'Date ?';
                        const location = lead.location || 'Location ?';

                        const name = lead.push_name ? ` (${lead.push_name})` : '';
                        hotMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
                        hotMsg += `   ${qty} | ${budget} | ${when} | ${location}\n`;
                        hotMsg += `   Status: ${lead.status}\n\n`;
                    });

                    hotMsg += `━━━━━━━━━━━━━━━━━━\n`;
                    hotMsg += `💡 INFO <number> for full details\n`;
                    hotMsg += `💡 LOCK <number> to silence bot`;

                    await sendTextMessage(jid, hotMsg);
                    console.log(`✅ Hotleads sent for ${label}, min qty: ${min_quantity}\n`);

                } catch (error) {
                    console.error(`❌ Hotleads fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch hotleads: ${error.message}`);
                }
                return;
            }

            // LOCKED COMMAND
            if (msgUpper.startsWith('LOCKED') || msgUpper === 'LOCKED') {
                console.log(`✅✅✅ LOCKED COMMAND MATCHED!`);

                const parts = msg.trim().split(/\s+/);
                const dateRange = parseDateRange(parts);

                if (dateRange.error) {
                    await sendTextMessage(jid, dateRange.error);
                    return;
                }

                const { start_date, end_date, label } = dateRange;

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/locked`,
                        { start_date, end_date },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    const d = response.data;

                    if (d.status === 'error') {
                        await sendTextMessage(jid, `❌ Failed: ${d.message}`);
                        return;
                    }

                    if (d.total === 0) {
                        await sendTextMessage(jid,
                            `🔓 No locked conversations for ${label}.`
                        );
                        return;
                    }

                    let lockedMsg = `🔒 *Locked Conversations - ${label}*\n`;
                    lockedMsg += `Total: ${d.total}\n`;
                    lockedMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

                    d.leads.forEach((lead, index) => {
                        const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
                        const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
                        const location = lead.location || 'Location ?';
                        
                        const name = lead.push_name ? ` (${lead.push_name})` : '';
                        lockedMsg += `${index + 1}. +${lead.customer_number}${name}\n`
                        lockedMsg += `   ${qty} | ${budget} | ${location}\n`;
                        lockedMsg += `   Locked at: ${lead.locked_at}\n\n`;
                    });

                    lockedMsg += `━━━━━━━━━━━━━━━━━━\n`;
                    lockedMsg += `💡 UNLOCK <number> to re-enable bot\n`;
                    lockedMsg += `💡 RESET <number> to clear conversation`;

                    await sendTextMessage(jid, lockedMsg);
                    console.log(`✅ Locked list sent for ${label}\n`);

                } catch (error) {
                    console.error(`❌ Locked fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch locked list: ${error.message}`);
                }
                return;
            }

            // INFO COMMAND
            if (msgUpper.startsWith('INFO ') || msgUpper.startsWith('/INFO ')) {
                console.log(`✅✅✅ INFO COMMAND MATCHED!`);
                
                const customerNumber = msg.replace(/INFO\s+/i, '').replace(/\/INFO\s+/i, '').trim();
                
                try {
                    const response = await axios.get(
                        `${process.env.LLM_API_URL}/lead_info/${customerNumber}`,
                        { timeout: 10000 }
                    );
                    
                    const data = response.data;
                    
                    if (data.status === 'not_found') {
                        await sendTextMessage(jid, `❌ No lead found for +${customerNumber}`);
                        return;
                    }
                    
                    const lead = data.lead;
                    
                    let infoMsg = `📋 *Customer Info*\n\n`;
                    infoMsg += `📱 +${lead.customer_number}\n\n`;
                    infoMsg += lead.push_name ? `👤 ${lead.push_name}\n\n` : `\n`;
                    infoMsg += `*Requirements:*\n`;
                    infoMsg += lead.quantity  ? `Qty: ${lead.quantity} pcs\n`    : `Qty: Not provided\n`;
                    infoMsg += lead.budget    ? `Budget: ${lead.budget}/pc\n`     : `Budget: Not provided\n`;
                    infoMsg += lead.location  ? `Location: ${lead.location}\n`    : `Location: Not provided\n`;
                    infoMsg += lead.timeline  ? `When: ${lead.timeline}\n`        : `When: Not provided\n`;
                    infoMsg += `\n*Status:* ${lead.status}\n`;
                    infoMsg += lead.last_message ? `*Last message:* "${lead.last_message}"\n` : '';
                    infoMsg += `\n*First contact:* ${lead.created_at ? new Date(lead.created_at).toLocaleString('en-IN') : '-'}\n`;
                    infoMsg += `*Last active:* ${lead.updated_at ? new Date(lead.updated_at).toLocaleString('en-IN') : '-'}\n`;
                    infoMsg += `\n━━━━━━━━━━━━━━━━━━\n`;
                    infoMsg += `RESET ${lead.customer_number}`;
                    
                    await sendTextMessage(jid, infoMsg);
                    console.log(`✅ Info sent for ${customerNumber}\n`);
                    
                } catch (error) {
                    console.error(`❌ Info fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch info: ${error.message}`);
                }
                return;
            }

            // STATUS COMMAND
            if (msgUpper === 'STATUS' || msgUpper === '/STATUS') {
                const uptime = Math.floor(process.uptime());
                const hours = Math.floor(uptime / 3600);
                const minutes = Math.floor((uptime % 3600) / 60);

                await sendTextMessage(jid,
                `🤖 *Admin Commands*\n\n` +
                `📝 *RESET <number>*\n` +
                `   Reset customer conversation\n` +
                `   Example: RESET 919942463672\n\n` +
                `🔓 *UNLOCK <number>*\n` +
                `   Unlock locked conversation\n` +
                `   Example: UNLOCK 919942463672\n\n` +
                `🔒 *LOCK <number>*\n` +
                `   Silence bot for a contact\n` +
                `   Example: LOCK 919942463672\n\n` +
                `📋 *LEADS <days>*\n` +
                `   Show leads for last N days\n` +
                `   Example: LEADS 7\n\n` +
                `📊 *SUMMARY <days or date range>*\n` +
                `   Business overview\n` +
                `   Example: SUMMARY / SUMMARY 7 / SUMMARY 12/02 19/02\n\n` +
                `⏳ *PENDING <days or date range>*\n` +
                `   Incomplete conversations\n` +
                `   Example: PENDING / PENDING 7 / PENDING 12/02 19/02\n\n` +
                `⚠️ *FOLLOWUP <days or date range>*\n` +
                `   Leads silent after seeing products\n` +
                `   Example: FOLLOWUP / FOLLOWUP 2 / FOLLOWUP 12/02 19/02\n\n` +
                `🔥 *HOTLEADS <min_qty> <days or date range>*\n` +
                `   High quantity leads\n` +
                `   Example: HOTLEADS / HOTLEADS 50 / HOTLEADS 50 12/02 19/02\n\n` +
                `🔒 *LOCKED <days or date range>*\n` +
                `   Show locked conversations\n` +
                `   Example: LOCKED / LOCKED 7 / LOCKED 12/02 19/02\n\n` +
                `🔍 *INFO <number>*\n` +
                `   Show customer details\n` +  
                `   Example: INFO 919942463672\n\n` +
                `📊 *STATUS*\n` +
                `   Show bot status\n\n` +
                `💡 All commands work in any case: RESET, Reset, reset`
            );
                console.log(`✅ STATUS sent\n`);
                return;
            }

            // HELP COMMAND
            if (msgUpper === 'HELP' || msgUpper === '/HELP' || msgUpper === 'COMMANDS') {
                await sendTextMessage(jid,
                    `🤖 *Admin Commands*\n\n` +
                    `📝 *RESET <number>*\n` +
                    `   Example: RESET 919942463672\n\n` +
                    `🔓 *UNLOCK <number>*\n` +
                    `   Example: UNLOCK 919942463672\n\n` +
                    `🔒 *LOCK <number>*\n` +
                    `   Example: LOCK 919942463672\n\n` +
                    `📊 *SUMMARY <days or date range>*\n` +
                    `   Example: SUMMARY / SUMMARY 7 / SUMMARY 12/02 19/02\n\n` +
                    `📋 *LEADS <days>*\n` +
                    `   Example: LEADS 7\n\n` +
                    `🔍 *INFO <number>*\n` +
                    `   Example: INFO 919942463672\n\n` +
                    `⏳ *PENDING <days or date range>*\n` +
                    `   Example: PENDING / PENDING 7 / PENDING 12/02 19/02\n\n` +
                    `⚠️ *FOLLOWUP <days or date range>*\n` +
                    `   Example: FOLLOWUP / FOLLOWUP 2 / FOLLOWUP 12/02 19/02\n\n` +
                    `🔥 *HOTLEADS <min_qty> <days or date range>*\n` +
                    `   Example: HOTLEADS / HOTLEADS 50 / HOTLEADS 50 12/02 19/02\n\n` +
                    `🔒 *LOCKED <days or date range>*\n` +
                    `   Example: LOCKED / LOCKED 7 / LOCKED 12/02 19/02\n\n` +
                    `📊 *STATUS*\n` +
                    `   Show bot status\n\n` +
                    `💡 All commands work in any case: RESET, Reset, reset`
                );
                console.log(`✅ HELP sent\n`);
                return;
            }

            // UPCOMING COMMAND
            if (msgUpper.startsWith('UPCOMING') || msgUpper === 'UPCOMING') {
                console.log(`✅✅✅ UPCOMING COMMAND MATCHED!`);

                const parts = msg.trim().split(/\s+/);
                const daysAhead = parts[1] && !isNaN(parts[1]) ? parseInt(parts[1]) : 7;

                try {
                    const response = await axios.post(
                        `${process.env.LLM_API_URL}/upcoming_events`,
                        { days_ahead: daysAhead },
                        { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
                    );

                    const d = response.data;

                    if (d.total === 0) {
                        await sendTextMessage(jid, `📅 No upcoming events in next ${daysAhead} days.`);
                        return;
                    }

                    let upcomingMsg = `📅 *Upcoming Events - Next ${daysAhead} days*\n`;
                    upcomingMsg += `Total: ${d.total}\n`;
                    upcomingMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

                    d.leads.forEach((lead, index) => {
                        const name     = lead.push_name ? ` (${lead.push_name})` : '';
                        const qty      = lead.quantity  ? `${lead.quantity} pcs` : 'Qty ?';
                        const budget   = lead.budget    ? `${lead.budget}/pc`    : 'Budget ?';
                        const location = lead.location  || 'Location ?';
                        upcomingMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
                        upcomingMsg += `   ${qty} | ${budget} | ${location}\n`;
                        upcomingMsg += `   🎯 Event: ${lead.event_date} (${lead.days_remaining} days away)\n`;
                        upcomingMsg += `   📅 Enquired: ${lead.enquired_on}\n\n`;
                    });

                    upcomingMsg += `━━━━━━━━━━━━━━━━━━\n`;
                    upcomingMsg += `💡 INFO <number> for full details\n`;
                    upcomingMsg += `💡 LOCK <number> to silence bot`;

                    await sendTextMessage(jid, upcomingMsg);
                    console.log(`✅ Upcoming events sent\n`);

                } catch (error) {
                    console.error(`❌ Upcoming events fetch failed:`, error.message);
                    await sendTextMessage(jid, `❌ Failed to fetch upcoming events: ${error.message}`);
                }
                return;
            }

            // No command matched - don't process as customer
            console.log(`⚠️⚠️⚠️ NO ADMIN COMMAND MATCHED! Message: "${msg}"`);
            return;
        }

        // ═══════════════════════════════════════════════════════════════
        // END ADMIN COMMANDS
        // ═══════════════════════════════════════════════════════════════

        // If WIFE sends message to customer, LOCK that conversation
        if (isFromMe) {
            const customerNumber = jid.split('@')[0];

            if (isAdminMessage(jid)) return;

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

        // Extract message text
        let messageText = '';

        if (message.message.imageMessage) {
            const caption = message.message.imageMessage.caption || '';
            const userId = jid.split('@')[0];
            console.log(`\n📸 IMAGE DETECTED from ${userId}, Caption: "${caption}"`);
            messageText = `[IMAGE_SENT]${caption ? ': ' + caption : ''}`;
            console.log(`   📦 Forwarding to Python: "${messageText}"`);
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

        // SMART MESSAGE BATCHING WITH DYNAMIC TIMEOUT
        if (!userMessageQueues.has(userId)) {
            userMessageQueues.set(userId, { messages: [], timeoutId: null, jid: jid, isFirstMessage: true, pushName: message.pushName || '' });
        }

        const queue = userMessageQueues.get(userId);
        queue.messages.push(messageText);

        const timeoutDuration = queue.isFirstMessage ? 60000 : 10000;

        if (queue.isFirstMessage) {
            console.log('⏰ First message - waiting 60 seconds for full requirements...');
        } else {
            console.log('🔄 Message added to batch, resetting 10-second timer...');
        }

        if (queue.timeoutId) clearTimeout(queue.timeoutId);

        queue.timeoutId = setTimeout(async () => {
            const messageCount = queue.messages.length;
            console.log(`⏱️  Processed after ${timeoutDuration/1000}s - ${messageCount} messages combined`);
            console.log(`\n✅ Customer stopped typing, processing ${messageCount} message(s)`);

            const combinedMessage = queue.messages.join('\n');
            console.log(`📋 Combined: ${combinedMessage.length > 100 ? combinedMessage.substring(0, 100) + '...' : combinedMessage}`);

            queue.messages = [];
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

        // Priority 1: Product Images with Summary
        if (llmResponse.reply === "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]") {
            console.log('🎯 Product image marker detected!');
            console.log('🔍 DEBUG: Full llmResponse:', JSON.stringify(llmResponse, null, 2));

            if (llmResponse.products && llmResponse.products.length > 0) {
                const requirementsSummary = llmResponse.requirements_summary || "";
                await sendProductImages(jid, llmResponse.products, requirementsSummary);
                console.log('✅ All images sent\n');

                const customerNumber = jid.split('@')[0];
                if (!alertedCustomers.has(customerNumber)) {
                    console.log('🔍 DEBUG: About to call alertWife with:', {
                        customerNumber,
                        customer_requirements: llmResponse.customer_requirements,
                        handoff_reason: llmResponse.handoff_reason
                    });
                    await alertWife(customerNumber, llmResponse, 'PRODUCTS_SHOWN', pushName);
                    alertedCustomers.add(customerNumber);
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

            if (replyText === null || replyText === undefined) {
                console.log('🔇 SILENT HANDOFF');
            } else {
                await sendTextMessage(jid, replyText);
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

        // Priority 3: Normal Response
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

async function lockConversation(customerNumber) {
    try {
        const LLM_API_URL = process.env.LLM_API_URL;
        if (!LLM_API_URL) {
            console.error('❌ LLM_API_URL not configured');
            return false;
        }
        await axios.post(`${LLM_API_URL}/lock_conversation`, { user_id: customerNumber }, {
            timeout: 10000,
            headers: { 'Content-Type': 'application/json' }
        });
        lockedConversationsCache.add(customerNumber);
        console.log(`✅ Conversation permanently locked for ${customerNumber}`);
        return true;
    } catch (error) {
        console.error('❌ Error locking conversation:', error.message);
        return false;
    }
}

async function initializeWhatsAppClient() {
    try {
        console.log('🔄 Initializing WhatsApp client...');

        const logger = pino({ level: 'silent' });
        const SUPABASE_DB_URL = process.env.SUPABASE_DB_URL;
        const IS_PRODUCTION = !!process.env.RENDER_SERVICE_NAME;

        let state, saveCreds, savePhoneNumber, clearSessionLock;

        if (SUPABASE_DB_URL && IS_PRODUCTION) {
            console.log('🗄️  Using Supabase for auth storage (production mode)');
            const authState = await useSupabaseAuthState(SUPABASE_DB_URL);
            state = authState.state;
            saveCreds = authState.saveCreds;
            savePhoneNumber = authState.savePhoneNumber;
            clearSessionLock = authState.clearSessionLock;
        } else {
            console.log('📁 Using file-based auth storage (development mode)');
            const authFolder = path.join(__dirname, 'auth_info');
            if (!fs.existsSync(authFolder)) fs.mkdirSync(authFolder, { recursive: true });
            const fileAuth = await useMultiFileAuthState(authFolder);
            state = fileAuth.state;
            saveCreds = fileAuth.saveCreds;
            savePhoneNumber = null;
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
                    ? lastDisconnect.error.output.statusCode : null;

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
                    setTimeout(() => initializeWhatsAppClient(), 5000);
                } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                    console.log('❌ Max reconnection attempts reached. Please restart manually.');
                } else {
                    console.log('⏳ Waiting for new connection...');
                }
            }

            if (connection === 'open') {
                console.log('✅ WhatsApp connected successfully!');

                if (savePhoneNumber && state.creds.me?.id) {
                    const phoneNumber = state.creds.me.id.split(':')[0];
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
        if (isHealthy) {
            console.log('✅ LLM API is healthy');
        } else {
            console.log('⚠️  LLM API is not responding');
        }
    }
}

// ============================================================
// MORNING BRIEFING — 8:00 AM IST
// Shows yesterday's pending followups and incomplete leads
// ============================================================
async function sendMorningBriefing() {
    try {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = yesterday.toISOString().split('T')[0];

        const [followupRes, pendingRes, upcomingRes] = await Promise.all([
            axios.post(
                `${process.env.LLM_API_URL}/followup`,
                { start_date: yesterdayStr, end_date: yesterdayStr, silent_days: 1 },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            ),
            axios.post(
                `${process.env.LLM_API_URL}/pending`,
                { start_date: yesterdayStr, end_date: yesterdayStr },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            ),
            axios.post(
                `${process.env.LLM_API_URL}/upcoming_events`,
                { days_ahead: 10 },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            )
        ]);

        const f = followupRes.data;
        const p = pendingRes.data;
        const u = upcomingRes.data;

        if (f.total === 0 && p.total === 0 && u.total === 0) {
            console.log('✅ No morning briefing needed - nothing pending');
            return;
        }

        const dateLabel = yesterday.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });

        let msg = `☀️ *Good Morning! Briefing - ${dateLabel}*\n\n`;

        if (u.total > 0) {
            msg += `🎯 *Upcoming Events - Next 10 Days: ${u.total}*\n`;
            msg += `(Follow up to convert!)\n\n`;
            u.leads.forEach((lead, i) => {
                const name     = lead.push_name ? ` (${lead.push_name})` : '';
                const qty      = lead.quantity  ? `${lead.quantity} pcs` : 'Qty ?';
                const budget   = lead.budget    ? `${lead.budget}/pc`    : 'Budget ?';
                const location = lead.location  || 'Location ?';
                msg += `${i + 1}. +${lead.customer_number}${name}\n`;
                msg += `   ${qty} | ${budget} | ${location}\n`;
                msg += `   🎯 Event: ${lead.event_date} (${lead.days_remaining} days away!)\n`;
                msg += `   📅 Enquired: ${lead.enquired_on}\n\n`;
            });
        }

        if (f.total > 0) {
            msg += `⚠️ *Customers to Follow Up: ${f.total}*\n`;
            msg += `(Saw products but went silent)\n\n`;
            f.leads.forEach((lead, i) => {
                const name     = lead.push_name ? ` (${lead.push_name})` : '';
                const qty      = lead.quantity  ? `${lead.quantity} pcs` : 'Qty ?';
                const budget   = lead.budget    ? `${lead.budget}/pc`    : 'Budget ?';
                const location = lead.location  || 'Location ?';
                msg += `${i + 1}. +${lead.customer_number}${name}\n`;
                msg += `   ${qty} | ${budget} | ${location}\n`;
                msg += `   🔕 Silent: ${lead.silent_for} day(s)\n\n`;
            });
        }

        if (p.total > 0) {
            msg += `⏳ *Incomplete Conversations: ${p.total}*\n`;
            msg += `(Still collecting requirements)\n\n`;
            p.leads.forEach((lead, i) => {
                const name     = lead.push_name ? ` (${lead.push_name})` : '';
                const qty      = lead.quantity  ? `${lead.quantity} pcs` : 'Qty ?';
                const location = lead.location  || 'Location ?';
                const missing  = lead.missing.length > 0
                    ? `Missing: ${lead.missing.join(', ')}`
                    : '';
                msg += `${i + 1}. +${lead.customer_number}${name}\n`;
                msg += `   ${qty} | ${location}\n`;
                if (missing) msg += `   ⚠️ ${missing}\n`;
                msg += `\n`;
            });
        }

        msg += `━━━━━━━━━━━━━━━━━━\n`;
        msg += `💡 UPCOMING 30 for next 30 days\n`;
        msg += `💡 FOLLOWUP for full list\n`;
        msg += `💡 SUMMARY for today's overview\n`;
        msg += `Have a productive day! 💪`;

        await sendTextMessage(WIFE_NUMBER, msg);
        console.log('✅ Morning briefing sent to wife');

    } catch (error) {
        console.error('❌ Morning briefing failed:', error.message);
    }
}


// ============================================================
// EVENING SUMMARY — 9:00 PM IST
// Shows today's full business summary
// ============================================================
async function sendEveningSummary() {
    try {
        const today = new Date().toISOString().split('T')[0];

        const [summaryRes, hotRes, followupRes] = await Promise.all([
            axios.post(
                `${process.env.LLM_API_URL}/summary`,
                { start_date: today, end_date: today },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            ),
            axios.post(
                `${process.env.LLM_API_URL}/hotleads`,
                { start_date: today, end_date: today, min_quantity: 100 },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            ),
            axios.post(
                `${process.env.LLM_API_URL}/followup`,
                { start_date: today, end_date: today, silent_days: 1 },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            )
        ]);

        const d = summaryRes.data;
        const h = hotRes.data;
        const f = followupRes.data;

        let msg = `🌟 *Evening Summary - ${d.start_date}*\n\n`;
        msg += `📥 Total Leads: ${d.total}\n`;
        msg += `📸 Products Shown: ${d.products_shown}\n`;
        msg += `⚠️  Follow-up Pending: ${d.followup_pending}\n`;
        msg += `🔒 Wife Handling: ${d.locked}\n`;
        msg += `⏳ Incomplete: ${d.incomplete}\n\n`;
        msg += `📍 Top Locations: ${d.top_locations}\n`;

        if (h.total > 0) {
            msg += `\n🔥 *Hot Leads Today (≥100 pcs): ${h.total}*\n`;
            h.leads.forEach((lead, i) => {
                const name = lead.push_name ? ` (${lead.push_name})` : '';
                msg += `   ${i + 1}. +${lead.customer_number}${name} - ${lead.quantity} pcs\n`;
            });
        }

        if (f.total > 0) {
            msg += `\n⚠️  *Customers to Follow Up: ${f.total}*\n`;
            f.leads.forEach((lead, i) => {
                const name = lead.push_name ? ` (${lead.push_name})` : '';
                msg += `   ${i + 1}. +${lead.customer_number}${name} - silent ${lead.silent_for} day(s)\n`;
            });
        }

        if (d.total === 0) {
            msg += `\nNo leads today. 😊\n`;
        }

        msg += `\n━━━━━━━━━━━━━━━━━━\n`;
        msg += `Good Night! 🌟 See you tomorrow!`;

        await sendTextMessage(WIFE_NUMBER, msg);
        console.log('✅ Night summary sent to wife');

    } catch (error) {
        console.error('❌ Night summary failed:', error.message);
    }
}

// ============================================================
// WEEKLY REPORT — Every Monday 8:00 AM IST
// ============================================================
async function sendWeeklyReport() {
    try {
        const today = new Date();
        const end = today.toISOString().split('T')[0];
        const start = new Date(today);
        start.setDate(today.getDate() - 6);
        const startStr = start.toISOString().split('T')[0];

        const [summaryRes, hotRes] = await Promise.all([
            axios.post(
                `${process.env.LLM_API_URL}/summary`,
                { start_date: startStr, end_date: end },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            ),
            axios.post(
                `${process.env.LLM_API_URL}/hotleads`,
                { start_date: startStr, end_date: end, min_quantity: 100 },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            )
        ]);

        const d = summaryRes.data;
        const h = hotRes.data;

        const startLabel = start.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
        const endLabel   = today.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });

        let msg = `📅 *Weekly Report*\n`;
        msg += `${startLabel} - ${endLabel}\n\n`;
        msg += `📥 Total Leads: ${d.total}\n`;
        msg += `📸 Products Shown: ${d.products_shown}\n`;
        msg += `⚠️  Follow-up Pending: ${d.followup_pending}\n`;
        msg += `🔒 Wife Handling: ${d.locked}\n`;
        msg += `⏳ Incomplete: ${d.incomplete}\n\n`;
        msg += `📍 Top Locations: ${d.top_locations}\n\n`;

        if (h.total > 0) {
            msg += `🔥 *Hot Leads This Week: ${h.total}*\n`;
            h.leads.forEach((lead, i) => {
                const name = lead.push_name ? ` (${lead.push_name})` : '';
                msg += `   ${i + 1}. +${lead.customer_number}${name} - ${lead.quantity} pcs\n`;
            });
            msg += `\n`;
        }

        msg += `━━━━━━━━━━━━━━━━━━\n`;
        msg += `Have a great week ahead! 💪`;

        await sendTextMessage(WIFE_NUMBER, msg);
        console.log('✅ Weekly report sent to wife');

    } catch (error) {
        console.error('❌ Weekly report failed:', error.message);
    }
}


// ============================================================
// MONTHLY REPORT — 1st of every month 8:00 AM IST
// ============================================================
async function sendMonthlyReport() {
    try {
        // Last month start and end
        const today = new Date();
        const firstDayThisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        const lastDayLastMonth  = new Date(firstDayThisMonth - 1);
        const firstDayLastMonth = new Date(lastDayLastMonth.getFullYear(), lastDayLastMonth.getMonth(), 1);

        const startStr = firstDayLastMonth.toISOString().split('T')[0];
        const endStr   = lastDayLastMonth.toISOString().split('T')[0];

        const [summaryRes, hotRes] = await Promise.all([
            axios.post(
                `${process.env.LLM_API_URL}/summary`,
                { start_date: startStr, end_date: endStr },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            ),
            axios.post(
                `${process.env.LLM_API_URL}/hotleads`,
                { start_date: startStr, end_date: endStr, min_quantity: 100 },
                { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
            )
        ]);

        const d = summaryRes.data;
        const h = hotRes.data;

        const monthName = firstDayLastMonth.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });

        let msg = `🗓️ *Monthly Report - ${monthName}*\n\n`;
        msg += `📥 Total Leads: ${d.total}\n`;
        msg += `📸 Products Shown: ${d.products_shown}\n`;
        msg += `⚠️  Follow-up Pending: ${d.followup_pending}\n`;
        msg += `🔒 Wife Handling: ${d.locked}\n`;
        msg += `⏳ Incomplete: ${d.incomplete}\n\n`;
        msg += `📍 Top Locations: ${d.top_locations}\n\n`;

        if (h.total > 0) {
            msg += `🔥 *Hot Leads This Month: ${h.total}*\n`;
            h.leads.forEach((lead, i) => {
                const name = lead.push_name ? ` (${lead.push_name})` : '';
                msg += `   ${i + 1}. +${lead.customer_number}${name} - ${lead.quantity} pcs\n`;
            });
            msg += `\n`;
        }

        // Conversion rate
        const conversionRate = d.total > 0
            ? Math.round((d.products_shown / d.total) * 100)
            : 0;
        msg += `📊 *Conversion Rate: ${conversionRate}%*\n`;
        msg += `(Leads that saw products)\n\n`;

        msg += `━━━━━━━━━━━━━━━━━━\n`;
        msg += `Great work last month! 🌟 Keep it up!`;

        await sendTextMessage(WIFE_NUMBER, msg);
        console.log('✅ Monthly report sent to wife');

    } catch (error) {
        console.error('❌ Monthly report failed:', error.message);
    }
}

let isInitializing = false;
let isInitialized = false;

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

         // ── Scheduled messages ────────────────────────
        // Morning briefing — 8:00 AM IST
        cron.schedule('0 8 * * *', async () => {
            console.log('⏰ Sending morning briefing to wife...');
            await sendMorningBriefing();
        }, { timezone: "Asia/Kolkata" });
        console.log('✅ Morning briefing scheduled at 8:00 AM IST');

        // Evening summary — 9:00 PM IST
        cron.schedule('0 21 * * *', async () => {
            console.log('⏰ Sending evening summary to wife...');
            await sendEveningSummary();
        }, { timezone: "Asia/Kolkata" });
        console.log('✅ Evening summary scheduled at 9:00 PM IST');

        // Weekly report — Every Monday 8:00 AM IST
        cron.schedule('0 8 * * 1', async () => {
            console.log('⏰ Sending weekly report to wife...');
            await sendWeeklyReport();
        }, { timezone: "Asia/Kolkata" });
        console.log('✅ Weekly report scheduled every Monday 8:00 AM IST');

        // Monthly report — 1st of every month 8:00 AM IST
        cron.schedule('0 8 1 * *', async () => {
            console.log('⏰ Sending monthly report to wife...');
            await sendMonthlyReport();
        }, { timezone: "Asia/Kolkata" });
        console.log('✅ Monthly report scheduled on 1st of every month 8:00 AM IST');
        // ─────────────────────────────────────────────

        isInitialized = true;
        isInitializing = false;
    } catch (error) {
        console.error('❌ Fatal error:', error);
        isInitializing = false;
        process.exit(1);
    }
}

process.on('SIGINT', () => {
    console.log('\n👋 Shutting down gracefully...');
    if (sock) sock.end();
    process.exit(0);
});

if (require.main === module) {
    main();
}