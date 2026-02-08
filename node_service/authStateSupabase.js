/**
 * Supabase-based Auth State for Baileys
 * ✅ Fixed: Properly serializes binary data for JSONB storage
 */

const { Client } = require('pg');
const { initAuthCreds, BufferJSON } = require('@whiskeysockets/baileys');

/**
 * Create Supabase-backed auth state
 * @param {string} dbUrl - PostgreSQL connection string
 * @returns {Promise<{state, saveCreds, closeConnection}>}
 */
async function useSupabaseAuthState(dbUrl) {
    const client = new Client({ 
        connectionString: dbUrl,
        ssl: {
            rejectUnauthorized: false
        }
    });
    
    try {
        await client.connect();
        console.log('📦 Loading auth from Supabase...');
    } catch (error) {
        console.error('❌ Failed to connect to Supabase:', error.message);
        throw error;
    }
    
    // ============================================================
    // LOAD EXISTING AUTH FROM DATABASE
    // ============================================================
    
    const result = await client.query(
        'SELECT creds, keys FROM whatsapp_auth WHERE id = $1',
        ['main_session']
    );
    
    let creds, keys;
    
    if (result.rows.length > 0) {
        console.log('✅ Found existing auth in database');
        
        // ✅ FIX: Deserialize with BufferJSON to handle binary data
        const storedCreds = result.rows[0].creds;
        const storedKeys = result.rows[0].keys;
        
        creds = JSON.parse(JSON.stringify(storedCreds), BufferJSON.reviver);
        keys = storedKeys ? JSON.parse(JSON.stringify(storedKeys), BufferJSON.reviver) : {};
        
    } else {
        console.log('📝 No existing auth - initializing new session');
        creds = initAuthCreds();
        keys = {};
    }
    
    // ============================================================
    // SAVE CREDENTIALS TO DATABASE
    // ============================================================
    
    const saveCreds = async () => {
        try {
            // ✅ FIX: Serialize with BufferJSON to preserve binary data
            const serializedCreds = JSON.parse(JSON.stringify(creds, BufferJSON.replacer));
            const serializedKeys = JSON.parse(JSON.stringify(keys, BufferJSON.replacer));
            
            await client.query(`
                INSERT INTO whatsapp_auth (id, creds, keys, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (id) 
                DO UPDATE SET 
                    creds = $2, 
                    keys = $3, 
                    updated_at = NOW()
            `, ['main_session', serializedCreds, serializedKeys]);
            
            console.log('💾 Auth saved to Supabase');
        } catch (error) {
            console.error('❌ Error saving auth:', error.message);
        }
    };
    
    // ============================================================
    // CREATE BAILEYS-COMPATIBLE STATE OBJECT
    // ============================================================
    
    return {
        state: { 
            creds, 
            keys: {
                // Get keys by type and IDs
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
                
                // Set/update keys
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
        closeConnection: () => client.end()
    };
}

module.exports = { useSupabaseAuthState };