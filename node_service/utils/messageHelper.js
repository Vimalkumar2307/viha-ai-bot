/**
 * Message sending helpers
 * sendTextMessage, sendImageMessage, sendProductImages, alertWife
 */

const WIFE_NUMBER = process.env.WIFE_NUMBER || '919865204829@s.whatsapp.net';

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Will be injected from vihaBot.js
let sock = null;
function setSock(s) { sock = s; }

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
            await sleep(2000);
        }
        for (let i = 0; i < products.length; i++) {
            const product = products[i];
            const caption = `${i + 1}. ${product.name}\n₹${product.price}/piece`;
            await sendImageMessage(jid, product.image_url, caption);
            if (i < products.length - 1) await sleep(1500);
        }
        await sleep(2000);
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
                if (req.quantity)        alertMessage += `Quantity: ${req.quantity} pieces\n`;
                if (req.budget_per_piece) alertMessage += `Budget: ₹${req.budget_per_piece} per piece\n`;
                if (req.location)        alertMessage += `Location: ${req.location}\n`;
                if (req.timeline)        alertMessage += `When needed: ${req.timeline}\n`;
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
            if (llmResponse.last_message)   alertMessage += `Last Message:\n"${llmResponse.last_message}"\n\n`;
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

module.exports = {
    setSock,
    sendTextMessage,
    sendImageMessage,
    sendProductImages,
    alertWife,
    sleep
};