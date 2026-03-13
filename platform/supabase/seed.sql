-- Seed: Anton's owner profile
-- Run after first signup or manually set role
-- UPDATE public.profiles SET role = 'owner' WHERE email = 'YOUR_EMAIL_HERE';

-- Platform stats initial values
UPDATE public.platform_stats SET
  total_users = 1,
  active_bots = 2,
  total_trades = 847,
  total_volume = 1250000.00;
