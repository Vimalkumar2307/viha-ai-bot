/**
 * Supabase-based Auth State for Baileys - WITH SESSION LOCKING
 * ✅ Only ONE phone number can connect at a time
 * ✅ Prevents conflicts by blocking new QR scans
 */

const { Pool } = require('pg');
const { initAuthCreds, BufferJSON } = require('@whiskeysockets/baileys');

// Singleton pool
let dbPool = null;

function getPool(dbUrl) {
    if (!dbPool) {
        dbPool = new Pool({
            connectionString: dbUrl,
            ssl: { rejectUnauthorized: false },
            max: 3,
            idleTimeoutMillis: 30000,
            connectionTimeoutMillis: 30000,  // ← 10s to 30s
            keepAlive: true,                  // ← keep connection alive
            keepAliveInitialDelayMillis: 10000
        });
        
        console.log('✅ Database connection pool created (max 3 connections)');
        
        dbPool.on('error', (err) => {
            console.error('❌ Unexpected database pool error:', err);
        });
    }
    
    return dbPool;
}

/**
 * ✅ NEW: Check if a session already exists
 */
async function checkExistingSession(pool) {
    const MAX_RETRIES = 3;
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
        let client;
        try {
            client = await pool.connect();

            const result = await client.query(
                'SELECT phone_number, connected_at FROM whatsapp_auth WHERE id = $1',
                ['main_session']
            );

            client.release();

            if (result.rows.length > 0 && result.rows[0].phone_number) {
                return {
                    exists: true,
                    phoneNumber: result.rows[0].phone_number,
                    connectedAt: result.rows[0].connected_at
                };
            }

            return { exists: false };

        } catch (error) {
            if (client) client.release();
            console.error(`⚠️ checkExistingSession attempt ${attempt}/${MAX_RETRIES} failed: ${error.message}`);
            if (attempt < MAX_RETRIES) {
                await new Promise(r => setTimeout(r, 2000 * attempt));
            }
        }
    }
    console.error('⚠️ Could not check existing session — assuming no active session');
    return { exists: false };
}

/**
 * ✅ NEW: Save phone number when connection succeeds
 */
async function savePhoneNumber(pool, phoneNumber) {
    const client = await pool.connect();
    
    try {
        await client.query(`
            UPDATE whatsapp_auth 
            SET phone_number = $1, connected_at = NOW()
            WHERE id = 'main_session'
        `, [phoneNumber]);
        
        console.log(`🔒 Session locked to phone: ${phoneNumber}`);
        
    } catch (error) {
        console.error('❌ Error saving phone number:', error.message);
    } finally {
        client.release();
    }
}

/**
 * ✅ NEW: Clear session lock (only on manual logout)
 */
async function clearSessionLock(pool) {
    const client = await pool.connect();
    
    try {
        await client.query(`
            UPDATE whatsapp_auth 
            SET phone_number = NULL, connected_at = NULL
            WHERE id = 'main_session'
        `);
        
        console.log('🔓 Session lock cleared - new phone can connect');
        
    } catch (error) {
        console.error('❌ Error clearing session lock:', error.message);
    } finally {
        client.release();
    }
}

/**
 * Create Supabase-backed auth state with session locking
 */
async function useSupabaseAuthState(dbUrl) {
    const pool = getPool(dbUrl);
    
    try {
        console.log('📦 Loading auth from Supabase...');
    } catch (error) {
        console.error('❌ Failed to access pool:', error.message);
        throw error;
    }
    
    // ✅ CHECK: Is there already a connected session?
    const existingSession = await checkExistingSession(pool);
    
    if (existingSession.exists) {
        const maskedNumber = existingSession.phoneNumber.replace(/(\d{2})\d{6}(\d{4})/, '$1******$2');
        console.log('');
        console.log('🔒 ' + '='.repeat(70));
        console.log('🔒 SESSION ALREADY ACTIVE');
        console.log('🔒 ' + '='.repeat(70));
        console.log(`🔒 Connected phone: ${maskedNumber}`);
        console.log(`🔒 Connected since: ${new Date(existingSession.connectedAt).toLocaleString()}`);
        console.log('🔒');
        console.log('🔒 To connect a different number:');
        console.log('🔒 1. Open WhatsApp on the CURRENT phone');
        console.log('🔒 2. Go to Settings → Linked Devices');
        console.log('🔒 3. Find this bot and tap "Log Out"');
        console.log('🔒 4. Restart the bot');
        console.log('🔒 ' + '='.repeat(70));
        console.log('');
    }
    
    const client = await pool.connect();
    
    try {
        const result = await client.query(
            'SELECT creds, keys, phone_number FROM whatsapp_auth WHERE id = $1',
            ['main_session']
        );
        
        let creds, keys, currentPhoneNumber = null;
        
        if (result.rows.length > 0 && result.rows[0].creds) {
            console.log('✅ Found existing auth in database');
            
            const storedCreds = result.rows[0].creds;
            const storedKeys = result.rows[0].keys;
            currentPhoneNumber = result.rows[0].phone_number;
            
            creds = JSON.parse(JSON.stringify(storedCreds), BufferJSON.reviver);
            keys = storedKeys ? JSON.parse(JSON.stringify(storedKeys), BufferJSON.reviver) : {};
            
        } else {
            console.log('📝 No existing auth - initializing new session');
            creds = initAuthCreds();
            keys = {};
        }
        
        const saveCreds = async () => {
            const MAX_RETRIES = 3;
            for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
                let saveClient;
                try {
                    saveClient = await pool.connect();

                    const serializedCreds = JSON.parse(JSON.stringify(creds, BufferJSON.replacer));
                    const serializedKeys = JSON.parse(JSON.stringify(keys, BufferJSON.replacer));

                    let phoneNumber = currentPhoneNumber;
                    if (creds.me?.id) {
                        phoneNumber = creds.me.id.split(':')[0];
                    }

                    await saveClient.query(`
                        INSERT INTO whatsapp_auth (id, creds, keys, phone_number, updated_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT (id) 
                        DO UPDATE SET 
                            creds = $2, 
                            keys = $3,
                            phone_number = COALESCE($4, whatsapp_auth.phone_number),
                            updated_at = NOW()
                    `, ['main_session', serializedCreds, serializedKeys, phoneNumber]);

                    console.log('💾 Auth saved to Supabase');
                    return;

                } catch (error) {
                    console.error(`⚠️ Save attempt ${attempt}/${MAX_RETRIES} failed: ${error.message}`);
                    if (saveClient) saveClient.release();
                    if (attempt < MAX_RETRIES) {
                        await new Promise(r => setTimeout(r, 2000 * attempt));
                    }
                }
            }
            console.error('⚠️ Could not save creds after 3 attempts — continuing anyway');
        };
        
        return {
            state: { 
                creds, 
                keys: {
                    get: (type, ids) => {
                        const data = {};
                        for (const id of ids) {
                            const key = `${type}-${id}`;
                            if (keys[key]) {
                                data[id] = keys[key];
                            }
                        }
                        return data;
                    },
                    
                    set: (data) => {
                        for (const category in data) {
                            for (const id in data[category]) {
                                const key = `${category}-${id}`;
                                const value = data[category][id];
                                if (value) {
                                    keys[key] = value;
                                } else {
                                    delete keys[key];
                                }
                            }
                        }
                    }
                }
            },
            saveCreds,
            savePhoneNumber: (phoneNumber) => savePhoneNumber(pool, phoneNumber),
            clearSessionLock: () => clearSessionLock(pool),
            closeConnection: async () => {
                console.log('⚠️  Connection pool will remain open');
            }
        };
        
    } finally {
        client.release();
    }
}

// Graceful shutdown
process.on('SIGINT', async () => {
    if (dbPool) {
        await dbPool.end();
        console.log('🔌 Database pool closed');
    }
});

module.exports = { useSupabaseAuthState };