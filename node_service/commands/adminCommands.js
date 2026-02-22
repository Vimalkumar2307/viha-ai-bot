/**
 * Admin command handlers
 * All commands sent by wife via WhatsApp
 */

const axios = require('axios');
const { sendTextMessage } = require('../utils/messageHelper');
const { parseDateRange }  = require('../utils/dateHelper');

// ============================================================
// RESET
// ============================================================
async function handleReset(jid, msg, alertedCustomers, lockedConversationsCache) {
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
}


// ============================================================
// UNLOCK
// ============================================================
async function handleUnlock(jid, msg, alertedCustomers, lockedConversationsCache) {
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
}


// ============================================================
// LOCK
// ============================================================
async function handleLock(jid, msg, alertedCustomers, lockedConversationsCache) {
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
}


// ============================================================
// LEADS
// ============================================================
async function handleLeads(jid, msg) {
    const parts = msg.trim().split(/\s+/);
    const days  = parts[1] && !isNaN(parts[1]) ? parseInt(parts[1]) : 7;

    try {
        const response = await axios.post(
            `${process.env.LLM_API_URL}/leads`,
            { days },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );

        const data = response.data;

        if (data.total === 0) {
            await sendTextMessage(jid, `📋 No leads in the last ${days} day(s).`);
            return;
        }

        let leadsMsg = `📋 *Leads - Last ${days} day(s)*\n`;
        leadsMsg += `Total: ${data.total}\n`;
        leadsMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

        data.leads.forEach((lead, index) => {
            const name = lead.push_name ? ` (${lead.push_name})` : '';
            leadsMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
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
}


// ============================================================
// SUMMARY
// ============================================================
async function handleSummary(jid, msg) {
    const parts     = msg.trim().split(/\s+/);
    const dateRange = parseDateRange(parts);

    if (dateRange.error) { await sendTextMessage(jid, dateRange.error); return; }

    const { start_date, end_date, label } = dateRange;

    try {
        const response = await axios.post(
            `${process.env.LLM_API_URL}/summary`,
            { start_date, end_date },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );

        const d = response.data;
        if (d.status === 'error') { await sendTextMessage(jid, `❌ Summary failed: ${d.message}`); return; }

        let summaryMsg = `📊 *Summary - ${label}*\n\n`;
        summaryMsg += `📥 New Leads: ${d.total}\n`;
        summaryMsg += `📸 Products Shown: ${d.products_shown}\n`;
        summaryMsg += `⚠️  Follow-up Pending: ${d.followup_pending}\n`;
        summaryMsg += `🔒 Wife Handling: ${d.locked}\n`;
        summaryMsg += `⏳ Incomplete: ${d.incomplete}\n\n`;
        summaryMsg += `📍 Top Locations: ${d.top_locations}\n`;

        if (d.leads && d.leads.length > 0) {
            summaryMsg += `\n━━━━━━━━━━━━━━━━━━\n`;
            summaryMsg += `📋 *Lead Details:*\n\n`;
            d.leads.forEach((lead, index) => {
                const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
                const budget   = lead.budget   ? `₹${lead.budget}/pc`   : 'Budget ?';
                const when     = lead.timeline || 'Date ?';
                const location = lead.location || 'Location ?';
                const name     = lead.push_name ? ` (${lead.push_name})` : '';
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
}


// ============================================================
// PENDING
// ============================================================
async function handlePending(jid, msg) {
    const parts     = msg.trim().split(/\s+/);
    const dateRange = parseDateRange(parts);

    if (dateRange.error) { await sendTextMessage(jid, dateRange.error); return; }

    const { start_date, end_date, label } = dateRange;

    try {
        const response = await axios.post(
            `${process.env.LLM_API_URL}/pending`,
            { start_date, end_date },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );

        const d = response.data;
        if (d.status === 'error') { await sendTextMessage(jid, `❌ Pending fetch failed: ${d.message}`); return; }
        if (d.total === 0)        { await sendTextMessage(jid, `⏳ No pending leads for ${label}.`); return; }

        let pendingMsg = `⏳ *Pending - ${label}*\n`;
        pendingMsg += `Total: ${d.total}\n`;
        pendingMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

        d.leads.forEach((lead, index) => {
            const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
            const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
            const when     = lead.timeline || 'Date ?';
            const location = lead.location || 'Location ?';
            const missing  = lead.missing.length > 0 ? `Missing: ${lead.missing.join(', ')}` : 'All details collected';
            const name     = lead.push_name ? ` (${lead.push_name})` : '';
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
}


// ============================================================
// FOLLOWUP
// ============================================================
async function handleFollowup(jid, msg) {
    const parts = msg.trim().split(/\s+/);

    let silent_days = 1;
    let dateRange;

    if (parts.length === 2 && !isNaN(parts[1]) && !parts[1].includes('/')) {
        silent_days = parseInt(parts[1]);
        dateRange   = parseDateRange([parts[0]]);
    } else {
        dateRange = parseDateRange(parts);
    }

    if (dateRange.error) { await sendTextMessage(jid, dateRange.error); return; }

    const { start_date, end_date, label } = dateRange;

    try {
        const response = await axios.post(
            `${process.env.LLM_API_URL}/followup`,
            { start_date, end_date, silent_days },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );

        const d = response.data;
        if (d.status === 'error') { await sendTextMessage(jid, `❌ Followup fetch failed: ${d.message}`); return; }
        if (d.total === 0)        { await sendTextMessage(jid, `✅ No follow-ups needed for ${label}.`); return; }

        let followupMsg = `⚠️ *Follow-up Needed - ${label}*\n`;
        followupMsg += `Total: ${d.total}\n`;
        followupMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

        d.leads.forEach((lead, index) => {
            const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
            const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
            const when     = lead.timeline || 'Date ?';
            const location = lead.location || 'Location ?';
            const silent   = lead.silent_for === 0 ? 'today' : lead.silent_for === 1 ? '1 day ago' : `${lead.silent_for} days ago`;
            const name     = lead.push_name ? ` (${lead.push_name})` : '';
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
}


// ============================================================
// HOTLEADS
// ============================================================
async function handleHotleads(jid, msg) {
    const parts = msg.trim().split(/\s+/);

    let min_quantity   = 100;
    let dateRangeParts = [parts[0]];

    if (parts.length >= 2 && !isNaN(parts[1]) && !parts[1].includes('/')) {
        min_quantity = parseInt(parts[1]);
        if (parts.length >= 3) dateRangeParts = [parts[0], ...parts.slice(2)];
    } else if (parts.length >= 2) {
        dateRangeParts = parts;
    }

    const dateRange = parseDateRange(dateRangeParts);
    if (dateRange.error) { await sendTextMessage(jid, dateRange.error); return; }

    const { start_date, end_date, label } = dateRange;

    try {
        const response = await axios.post(
            `${process.env.LLM_API_URL}/hotleads`,
            { start_date, end_date, min_quantity },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );

        const d = response.data;
        if (d.status === 'error') { await sendTextMessage(jid, `❌ Hotleads fetch failed: ${d.message}`); return; }
        if (d.total === 0)        { await sendTextMessage(jid, `🔥 No hot leads (≥${min_quantity} pcs) for ${label}.`); return; }

        let hotMsg = `🔥 *Hot Leads - ${label} (≥${min_quantity} pcs)*\n`;
        hotMsg += `Total: ${d.total}\n`;
        hotMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

        d.leads.forEach((lead, index) => {
            const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
            const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
            const when     = lead.timeline || 'Date ?';
            const location = lead.location || 'Location ?';
            const name     = lead.push_name ? ` (${lead.push_name})` : '';
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
}


// ============================================================
// LOCKED
// ============================================================
async function handleLocked(jid, msg) {
    const parts     = msg.trim().split(/\s+/);
    const dateRange = parseDateRange(parts);

    if (dateRange.error) { await sendTextMessage(jid, dateRange.error); return; }

    const { start_date, end_date, label } = dateRange;

    try {
        const response = await axios.post(
            `${process.env.LLM_API_URL}/locked`,
            { start_date, end_date },
            { timeout: 10000, headers: { 'Content-Type': 'application/json' } }
        );

        const d = response.data;
        if (d.status === 'error') { await sendTextMessage(jid, `❌ Failed: ${d.message}`); return; }
        if (d.total === 0)        { await sendTextMessage(jid, `🔓 No locked conversations for ${label}.`); return; }

        let lockedMsg = `🔒 *Locked Conversations - ${label}*\n`;
        lockedMsg += `Total: ${d.total}\n`;
        lockedMsg += `━━━━━━━━━━━━━━━━━━\n\n`;

        d.leads.forEach((lead, index) => {
            const qty      = lead.quantity ? `${lead.quantity} pcs` : 'Qty ?';
            const budget   = lead.budget   ? `${lead.budget}/pc`    : 'Budget ?';
            const location = lead.location || 'Location ?';
            const name     = lead.push_name ? ` (${lead.push_name})` : '';
            lockedMsg += `${index + 1}. +${lead.customer_number}${name}\n`;
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
}


// ============================================================
// INFO
// ============================================================
async function handleInfo(jid, msg) {
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
        infoMsg += `📱 +${lead.customer_number}\n`;
        infoMsg += lead.push_name ? `👤 ${lead.push_name}\n\n` : `\n`;
        infoMsg += `*Requirements:*\n`;
        infoMsg += lead.quantity  ? `Qty: ${lead.quantity} pcs\n`   : `Qty: Not provided\n`;
        infoMsg += lead.budget    ? `Budget: ${lead.budget}/pc\n`    : `Budget: Not provided\n`;
        infoMsg += lead.location  ? `Location: ${lead.location}\n`   : `Location: Not provided\n`;
        infoMsg += lead.timeline  ? `When: ${lead.timeline}\n`       : `When: Not provided\n`;
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
}


// ============================================================
// UPCOMING
// ============================================================
async function handleUpcoming(jid, msg) {
    const parts     = msg.trim().split(/\s+/);
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
}


// ============================================================
// STATUS
// ============================================================
async function handleStatus(jid) {
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
        `📅 *UPCOMING <days>*\n` +
        `   Show upcoming events\n` +
        `   Example: UPCOMING 7 / UPCOMING 30\n\n` +
        `📊 *STATUS*\n` +
        `   Show bot status\n\n` +
        `💡 All commands work in any case: RESET, Reset, reset`
    );
    console.log(`✅ STATUS sent\n`);
}


// ============================================================
// HELP
// ============================================================
async function handleHelp(jid) {
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
        `📅 *UPCOMING <days>*\n` +
        `   Example: UPCOMING 7 / UPCOMING 30\n\n` +
        `📊 *STATUS*\n` +
        `   Show bot status\n\n` +
        `💡 All commands work in any case: RESET, Reset, reset`
    );
    console.log(`✅ HELP sent\n`);
}


// ============================================================
// MAIN ROUTER — called from vihaBot.js
// ============================================================
async function handleAdminCommand(msgUpper, msg, jid, alertedCustomers, lockedConversationsCache) {
    if (msgUpper.startsWith('RESET ')      || msgUpper.startsWith('/RESET '))    return await handleReset(jid, msg, alertedCustomers, lockedConversationsCache);
    if (msgUpper.startsWith('UNLOCK ')     || msgUpper.startsWith('/UNLOCK '))   return await handleUnlock(jid, msg, alertedCustomers, lockedConversationsCache);
    if (msgUpper.startsWith('LOCK ')       || msgUpper.startsWith('/LOCK '))     return await handleLock(jid, msg, alertedCustomers, lockedConversationsCache);
    if (msgUpper.startsWith('LEADS')       || msgUpper === 'LEADS')              return await handleLeads(jid, msg);
    if (msgUpper.startsWith('SUMMARY')     || msgUpper === 'SUMMARY')            return await handleSummary(jid, msg);
    if (msgUpper.startsWith('PENDING')     || msgUpper === 'PENDING')            return await handlePending(jid, msg);
    if (msgUpper.startsWith('FOLLOWUP')    || msgUpper === 'FOLLOWUP')           return await handleFollowup(jid, msg);
    if (msgUpper.startsWith('HOTLEADS')    || msgUpper === 'HOTLEADS')           return await handleHotleads(jid, msg);
    if (msgUpper.startsWith('LOCKED')      || msgUpper === 'LOCKED')             return await handleLocked(jid, msg);
    if (msgUpper.startsWith('INFO ')       || msgUpper.startsWith('/INFO '))     return await handleInfo(jid, msg);
    if (msgUpper.startsWith('UPCOMING')    || msgUpper === 'UPCOMING')           return await handleUpcoming(jid, msg);
    if (msgUpper === 'STATUS'              || msgUpper === '/STATUS')             return await handleStatus(jid);
    if (msgUpper === 'HELP'               || msgUpper === '/HELP' || msgUpper === 'COMMANDS') return await handleHelp(jid);

    // No command matched
    console.log(`⚠️⚠️⚠️ NO ADMIN COMMAND MATCHED! Message: "${msg}"`);
    await sendTextMessage(jid,
        `❓ Command not recognised: "${msg}"\n\n` +
        `Did you mean one of these?\n` +
        `SUMMARY | LEADS | FOLLOWUP\n` +
        `PENDING | HOTLEADS | LOCKED\n` +
        `UPCOMING | INFO | RESET\n` +
        `UNLOCK | LOCK | STATUS\n\n` +
        `💡 Type HELP for full guide`
    );
    return false;
}

module.exports = { handleAdminCommand };