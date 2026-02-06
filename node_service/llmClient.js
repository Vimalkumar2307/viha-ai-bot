/**
 * LLM Client Module - Updated with product support
 * Production-ready for Render deployment
 */

const axios = require('axios');

// ✅ PRODUCTION: No localhost fallback
const LLM_API_URL = process.env.LLM_API_URL;

// Validate on startup
if (!LLM_API_URL) {
    console.error('❌ CRITICAL: LLM_API_URL environment variable not set!');
    console.error('   Please set it to your Python service URL');
    console.error('   Example: https://viha-bot-python.onrender.com');
    process.exit(1);
}

console.log(`🔗 LLM API configured: ${LLM_API_URL}`);

/**
 * Call LangChain Complete Bot API
 */
async function chatWithLLM(message, userId = 'default') {
    try {
        console.log('🤖 Calling LangChain Bot API...');
        const startTime = Date.now();
        
        const response = await axios.post(`${LLM_API_URL}/chat`, {
            user_id: userId,
            message: message
        }, {
            timeout: 30000
        });
        
        const elapsed = Date.now() - startTime;
        console.log(`✅ Got response (${elapsed}ms)`);
        
        const data = response.data;
        
        // Check if conversation is locked
        if (data.status === 'locked') {
            console.log('🔒 Conversation is LOCKED - bot will stay silent');
            return {
                reply: null,
                needs_handoff: false,
                products: null,
                locked: true,
                locked_at: data.locked_at,
                locked_by: data.locked_by
            };
        }
        
        // Normal response
        if (data && data.status === 'success') {
            return {
                reply: data.reply,
                needs_handoff: data.needs_handoff || false,
                products: data.products || null,
                requirements_summary: data.requirements_summary || null,
                customer_requirements: data.customer_requirements || null,
                handoff_reason: data.handoff_reason || null,
                customer_number: data.customer_number,
                last_message: data.last_message,
                locked: false
            };
        } else {
            console.error('❌ Unexpected response format:', data);
            return null;
        }
        
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            console.error('❌ API Error: Request timed out');
        } else if (error.response) {
            console.error('❌ API Error:', error.response.status);
        } else {
            console.error('❌ API Error:', error.message);
        }
        return null;
    }
}

/**
 * Check if LangChain Bot API is healthy
 */
async function checkLLMHealth() {
    try {
        const response = await axios.get(`${LLM_API_URL}/health`, {
            timeout: 3000
        });
        return response.status === 200;
    } catch (error) {
        return false;
    }
}

module.exports = {
    chatWithLLM,
    checkLLMHealth,
    LLM_API_URL
};