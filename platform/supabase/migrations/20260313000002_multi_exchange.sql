-- Multi-exchange support: expand exchange_accounts to support multiple providers
-- Run this in Supabase SQL Editor

-- 1. Expand CHECK constraint to all 6 exchanges
ALTER TABLE exchange_accounts DROP CONSTRAINT IF EXISTS exchange_accounts_exchange_check;
ALTER TABLE exchange_accounts ADD CONSTRAINT exchange_accounts_exchange_check
  CHECK (exchange IN ('capital_com','binance','kraken','bybit','okx','coinbase'));

-- 2. Add credentials_encrypted JSONB column
ALTER TABLE exchange_accounts ADD COLUMN IF NOT EXISTS credentials_encrypted JSONB;

-- 3. Migrate existing data (pack 3 encrypted columns into JSONB)
UPDATE exchange_accounts
SET credentials_encrypted = jsonb_build_object(
  'apiKey', api_key_encrypted,
  'apiPassword', api_password_encrypted,
  'identifier', identifier_encrypted
)
WHERE credentials_encrypted IS NULL
  AND api_key_encrypted IS NOT NULL;

-- 4. Make NOT NULL and drop old columns
ALTER TABLE exchange_accounts ALTER COLUMN credentials_encrypted SET NOT NULL;
ALTER TABLE exchange_accounts DROP COLUMN IF EXISTS api_key_encrypted;
ALTER TABLE exchange_accounts DROP COLUMN IF EXISTS api_password_encrypted;
ALTER TABLE exchange_accounts DROP COLUMN IF EXISTS identifier_encrypted;

-- 5. Add exchange_provider to trades table
ALTER TABLE trades ADD COLUMN IF NOT EXISTS exchange_provider TEXT NOT NULL DEFAULT 'capital_com';
