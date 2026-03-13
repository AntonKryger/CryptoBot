-- CryptoBot Platform - Initial Schema
-- 7 tables + RLS + triggers

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- 1. PROFILES (extends auth.users)
-- ============================================
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  full_name TEXT,
  role TEXT NOT NULL DEFAULT 'visitor' CHECK (role IN ('owner', 'subscriber', 'visitor')),
  tier TEXT CHECK (tier IN ('starter', 'pro', 'elite')),
  has_2fa BOOLEAN NOT NULL DEFAULT false,
  onboarding_completed BOOLEAN NOT NULL DEFAULT false,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  subscription_status TEXT DEFAULT 'none' CHECK (subscription_status IN ('none', 'active', 'past_due', 'canceled', 'grace_period')),
  grace_period_ends_at TIMESTAMPTZ,
  theme TEXT NOT NULL DEFAULT 'midnight',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- ============================================
-- 2. EXCHANGE ACCOUNTS
-- ============================================
CREATE TABLE public.exchange_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  exchange TEXT NOT NULL DEFAULT 'capital_com' CHECK (exchange IN ('capital_com')),
  environment TEXT NOT NULL DEFAULT 'demo' CHECK (environment IN ('demo', 'live')),
  api_key_encrypted TEXT NOT NULL,
  api_password_encrypted TEXT,
  identifier_encrypted TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  connection_verified BOOLEAN NOT NULL DEFAULT false,
  last_verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER exchange_accounts_updated_at
  BEFORE UPDATE ON public.exchange_accounts
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- ============================================
-- 3. BOT INSTANCES
-- ============================================
CREATE TABLE public.bot_instances (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  exchange_account_id UUID NOT NULL REFERENCES public.exchange_accounts(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'My Bot',
  status TEXT NOT NULL DEFAULT 'stopped' CHECK (status IN ('running', 'stopped', 'error', 'suspended')),

  -- Kill switch
  is_suspended BOOLEAN NOT NULL DEFAULT false,
  suspended_reason TEXT,
  suspended_by UUID REFERENCES public.profiles(id),
  suspended_at TIMESTAMPTZ,

  -- Config
  coins TEXT[] NOT NULL DEFAULT ARRAY['BTCUSD'],
  risk_percent NUMERIC(5,2) NOT NULL DEFAULT 1.0,
  max_positions INTEGER NOT NULL DEFAULT 3,
  adx_minimum NUMERIC(5,2) NOT NULL DEFAULT 20.0,
  rr_minimum NUMERIC(5,2) NOT NULL DEFAULT 2.0,

  -- Health
  last_heartbeat TIMESTAMPTZ,
  last_signal_at TIMESTAMPTZ,
  uptime_percent NUMERIC(5,2),

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER bot_instances_updated_at
  BEFORE UPDATE ON public.bot_instances
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- ============================================
-- 4. TRADES (upsert keyed on deal_id)
-- ============================================
CREATE TABLE public.trades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_instance_id UUID REFERENCES public.bot_instances(id) ON DELETE SET NULL,
  deal_id TEXT NOT NULL,
  deal_reference TEXT,

  epic TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
  size NUMERIC(20,8) NOT NULL,

  entry_price NUMERIC(20,8),
  exit_price NUMERIC(20,8),
  stop_loss NUMERIC(20,8),
  take_profit NUMERIC(20,8),

  profit_loss NUMERIC(20,2),
  profit_loss_percent NUMERIC(10,4),

  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'canceled')),

  opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ,

  signal_mode TEXT,
  signal_data JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(user_id, deal_id)
);

CREATE TRIGGER trades_updated_at
  BEFORE UPDATE ON public.trades
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE INDEX idx_trades_user_status ON public.trades(user_id, status);
CREATE INDEX idx_trades_deal_id ON public.trades(deal_id);
CREATE INDEX idx_trades_opened_at ON public.trades(opened_at DESC);

-- ============================================
-- 5. TELEGRAM CONNECTIONS
-- ============================================
CREATE TABLE public.telegram_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  chat_id TEXT,
  verification_code TEXT,
  code_expires_at TIMESTAMPTZ,
  is_verified BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(user_id),
  UNIQUE(chat_id)
);

CREATE TRIGGER telegram_connections_updated_at
  BEFORE UPDATE ON public.telegram_connections
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- ============================================
-- 6. PLATFORM STATS (public, single row)
-- ============================================
CREATE TABLE public.platform_stats (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  total_users INTEGER NOT NULL DEFAULT 0,
  active_bots INTEGER NOT NULL DEFAULT 0,
  total_trades INTEGER NOT NULL DEFAULT 0,
  total_volume NUMERIC(20,2) NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.platform_stats (id) VALUES (1);

-- ============================================
-- 7. AUDIT LOG
-- ============================================
CREATE TABLE public.audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id UUID REFERENCES public.profiles(id),
  action TEXT NOT NULL,
  target_type TEXT,
  target_id UUID,
  details JSONB,
  ip_address INET,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_actor ON public.audit_log(actor_id);
CREATE INDEX idx_audit_log_created ON public.audit_log(created_at DESC);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

-- Profiles: users see own, owner sees all
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
  ON public.profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Owner can view all profiles"
  ON public.profiles FOR SELECT
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

CREATE POLICY "Users can update own profile"
  ON public.profiles FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

CREATE POLICY "Owner can update any profile"
  ON public.profiles FOR UPDATE
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

-- Exchange accounts: own only, owner sees all
ALTER TABLE public.exchange_accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own exchange accounts"
  ON public.exchange_accounts FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Owner can view all exchange accounts"
  ON public.exchange_accounts FOR SELECT
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

-- Bot instances: own only, owner sees all
ALTER TABLE public.bot_instances ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own bots"
  ON public.bot_instances FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Owner can manage all bots"
  ON public.bot_instances FOR ALL
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

CREATE POLICY "Users can update own bots"
  ON public.bot_instances FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Trades: own only, owner sees all
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own trades"
  ON public.trades FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Owner can view all trades"
  ON public.trades FOR SELECT
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

-- Telegram: own only
ALTER TABLE public.telegram_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own telegram"
  ON public.telegram_connections FOR ALL
  USING (auth.uid() = user_id);

-- Platform stats: public read
ALTER TABLE public.platform_stats ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read platform stats"
  ON public.platform_stats FOR SELECT
  USING (true);

CREATE POLICY "Owner can update platform stats"
  ON public.platform_stats FOR UPDATE
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

-- Audit log: owner only
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Owner can view audit log"
  ON public.audit_log FOR SELECT
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );

CREATE POLICY "System can insert audit log"
  ON public.audit_log FOR INSERT
  WITH CHECK (true);
