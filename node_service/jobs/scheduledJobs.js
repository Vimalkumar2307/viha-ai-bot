/**
 * Scheduled jobs for wife reports
 * Morning briefing — 8:00 AM IST
 * Evening summary  — 9:00 PM IST
 * Weekly report    — Every Monday 8:00 AM IST
 * Monthly report   — 1st of every month 8:00 AM IST
 */

const axios = require('axios');
const cron  = require('node-cron');
const { sendTextMessage } = require('../utils/messageHelper');

const WIFE_NUMBER = process.env.WIFE_NUMBER || '919865204829@s.whatsapp.net';

// ============================================================
// MORNING BRIEFING — 8:00 AM IST
// ============================================================
async function sendMorningBriefing() {
    try {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = yesterday.toISOString().split('T')[0];

       const dateLabel = yesterday.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });

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

        // TO - remove that block entirely, replace with this
        if (f.total === 0 && p.total === 0 && u.total === 0) {
            const msg = `☀️ *Good Morning! Briefing - ${dateLabel}*\n\n` +
                `✅ All clear! No pending follow-ups or upcoming events today.\n\n` +
                `Have a productive day! 💪`;
            await sendTextMessage(WIFE_NUMBER, msg);
            console.log('✅ Morning briefing sent (all clear)');
            return;
        }

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
        console.log('✅ Evening summary sent to wife');

    } catch (error) {
        console.error('❌ Evening summary failed:', error.message);
    }
}


// ============================================================
// WEEKLY REPORT — Every Monday 8:00 AM IST
// ============================================================
async function sendWeeklyReport() {
    try {
        const today = new Date();
        const end   = today.toISOString().split('T')[0];
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
        const today             = new Date();
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


// ============================================================
// REGISTER ALL CRON JOBS
// ============================================================
let jobsRegistered = false;

function registerScheduledJobs() {
    if (jobsRegistered) {
        console.log('⚠️ Cron jobs already registered — skipping');
        return;
    }
    jobsRegistered = true;

    // Morning briefing — 8:00 AM IST (daily)
    cron.schedule('0 8 * * *', async () => {
        console.log('⏰ Sending morning briefing to wife...');
        await sendMorningBriefing();
    }, { timezone: 'Asia/Kolkata' });
    console.log('✅ Morning briefing scheduled at 8:00 AM IST');

    // Evening summary — 9:00 PM IST (daily)
    cron.schedule('0 21 * * *', async () => {
        console.log('⏰ Sending evening summary to wife...');
        await sendEveningSummary();
    }, { timezone: 'Asia/Kolkata' });
    console.log('✅ Evening summary scheduled at 9:00 PM IST');

    // Weekly report — Every Monday 8:00 AM IST
    cron.schedule('0 8 * * 1', async () => {
        console.log('⏰ Sending weekly report to wife...');
        await sendWeeklyReport();
    }, { timezone: 'Asia/Kolkata' });
    console.log('✅ Weekly report scheduled every Monday 8:00 AM IST');

    // Monthly report — 1st of every month 8:00 AM IST
    cron.schedule('0 8 1 * *', async () => {
        console.log('⏰ Sending monthly report to wife...');
        await sendMonthlyReport();
    }, { timezone: 'Asia/Kolkata' });
    console.log('✅ Monthly report scheduled on 1st of every month 8:00 AM IST');
}

module.exports = { registerScheduledJobs };