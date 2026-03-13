-- Fix infinite recursion in RLS policies
-- Problem: "Owner can view all profiles" does a subquery on profiles,
-- which triggers RLS again, causing infinite recursion.
-- Solution: Use a SECURITY DEFINER function that bypasses RLS for the owner check.

-- Step 1: Create helper function (runs as definer, bypasses RLS)
CREATE OR REPLACE FUNCTION public.is_owner()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner'
  )
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- Step 2: Drop ALL recursive policies on profiles
DROP POLICY IF EXISTS "Owner can view all profiles" ON public.profiles;
DROP POLICY IF EXISTS "Owner can update any profile" ON public.profiles;

-- Step 3: Recreate owner policies using the helper function
CREATE POLICY "Owner can view all profiles"
  ON public.profiles FOR SELECT
  USING (public.is_owner());

CREATE POLICY "Owner can update any profile"
  ON public.profiles FOR UPDATE
  USING (public.is_owner());

-- Step 4: Fix owner policies on OTHER tables (they also subquery profiles)
DROP POLICY IF EXISTS "Owner can view all exchange accounts" ON public.exchange_accounts;
CREATE POLICY "Owner can view all exchange accounts"
  ON public.exchange_accounts FOR SELECT
  USING (public.is_owner());

DROP POLICY IF EXISTS "Owner can manage all bots" ON public.bot_instances;
CREATE POLICY "Owner can manage all bots"
  ON public.bot_instances FOR ALL
  USING (public.is_owner());

DROP POLICY IF EXISTS "Owner can view all trades" ON public.trades;
CREATE POLICY "Owner can view all trades"
  ON public.trades FOR SELECT
  USING (public.is_owner());

DROP POLICY IF EXISTS "Owner can update platform stats" ON public.platform_stats;
CREATE POLICY "Owner can update platform stats"
  ON public.platform_stats FOR UPDATE
  USING (public.is_owner());

DROP POLICY IF EXISTS "Owner can view audit log" ON public.audit_log;
CREATE POLICY "Owner can view audit log"
  ON public.audit_log FOR SELECT
  USING (public.is_owner());
