-- Equity snapshots for balance history chart
-- Bots send equity via /api/sync/equity every scan cycle

CREATE TABLE IF NOT EXISTS public.equity_snapshots (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_instance_id UUID REFERENCES public.bot_instances(id) ON DELETE SET NULL,
  equity NUMERIC(12,2) NOT NULL,
  snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  exchange TEXT NOT NULL DEFAULT 'kraken'
);

ALTER TABLE public.equity_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own snapshots"
  ON public.equity_snapshots FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Owner can view all snapshots"
  ON public.equity_snapshots FOR SELECT
  USING (public.is_owner());

CREATE POLICY "Sync can insert snapshots"
  ON public.equity_snapshots FOR INSERT
  WITH CHECK (true);

CREATE INDEX idx_equity_snapshots_user_time
  ON public.equity_snapshots(user_id, snapshot_at DESC);
