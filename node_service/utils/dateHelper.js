/**
 * Date range parser for admin commands
 * Supports:
 *   "SUMMARY"              → today
 *   "SUMMARY 7"            → last 7 days
 *   "SUMMARY 12/02 19/02"  → date range
 *   "SUMMARY 12/02/2026 19/02/2026" → date range with year
 */

function parseDateRange(parts) {
    const today = new Date();

    const formatDate = (d) => d.toISOString().split('T')[0];

    const parseDate = (str) => {
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

module.exports = { parseDateRange };