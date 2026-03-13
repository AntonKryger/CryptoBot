-- Fix infinite recursion in RLS policies
-- Problem: "Owner can view all profiles" does a subquery on profiles,
-- which triggers RLS again, causing infinite recursion.
-- Solution: Use a SECURITY DEFINER function that bypasses RLS for the owner check.

-- ============================================
-- STEP 1: SECURITY DEFINER helper (bypasses RLS)
-- ============================================
CREATE OR REPLACE FUNCTION public.is_owner()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner'
  )
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- ============================================
-- STEP 2: Fix recursive policies on profiles
-- ============================================
DROP POLICY IF EXISTS "Owner can view all profiles" ON public.profiles;
DROP POLICY IF EXISTS "Owner can update any profile" ON public.profiles;

CREATE POLICY "Owner can view all profiles"
  ON public.profiles FOR SELECT
  USING (public.is_owner());

CREATE POLICY "Owner can update any profile"
  ON public.profiles FOR UPDATE
  USING (public.is_owner());

-- ============================================
-- STEP 3: Fix owner policies on OTHER tables
-- ============================================
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

-- ============================================
-- STEP 4: Prevent users from changing their own role
-- ============================================
CREATE OR REPLACE FUNCTION public.prevent_role_change()
RETURNS TRIGGER AS $$
BEGIN
  -- Only service_role (admin) can change the role column
  IF OLD.role IS DISTINCT FROM NEW.role THEN
    IF current_setting('request.jwt.claims', true)::json->>'role' != 'service_role' THEN
      RAISE EXCEPTION 'Cannot change role — contact admin';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS prevent_role_change ON public.profiles;
CREATE TRIGGER prevent_role_change
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.prevent_role_change();

-- ============================================
-- STEP 5: Lock down audit log INSERT (only service_role or auth.uid() as actor)
-- ============================================
DROP POLICY IF EXISTS "System can insert audit log" ON public.audit_log;
CREATE POLICY "Authenticated users can insert own audit entries"
  ON public.audit_log FOR INSERT
  WITH CHECK (actor_id = auth.uid());

-- ============================================
-- STEP 6: Add missing INSERT policy for bot_instances (needed for onboarding)
-- ============================================
CREATE POLICY "Users can create own bots"
  ON public.bot_instances FOR INSERT
  WITH CHECK (auth.uid() = user_id);
