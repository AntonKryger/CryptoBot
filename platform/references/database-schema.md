# Database Schema Reference

## Eksisterende tabeller (001_initial_schema.sql)

| Tabel | Formaal | RLS |
|-------|---------|-----|
| `profiles` | Udvider auth.users: role, tier, 2FA, Stripe, theme | Bruger ser egen, owner ser alle |
| `exchange_accounts` | Krypterede API keys til Capital.com | Bruger ser egne, owner ser alle |
| `bot_instances` | Bot config + status + kill switch | Bruger ser egne, owner manager alle |
| `trades` | Trade historik, keyed paa deal_id | Bruger ser egne, owner ser alle |
| `telegram_connections` | Telegram chat linking med verification code | Bruger manager egen |
| `platform_stats` | Single-row aggregerede platform-tal | Public read, owner update |
| `audit_log` | Log af admin/system actions | Owner read, system insert |

## Nye tabeller (002_bot_types_reviews.sql — IKKE DEPLOYED ENDNU)

### bot_types
Definerer de tilgaengelige bot-typer (Aggressiv, Moderat, Passiv, etc.)

```sql
CREATE TABLE public.bot_types (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  description TEXT,
  risk_level INTEGER CHECK (risk_level BETWEEN 1 AND 5),
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### bot_instances tilfoejelse
```sql
ALTER TABLE public.bot_instances
  ADD COLUMN bot_type_id UUID REFERENCES public.bot_types(id);
```

### public_bot_stats (view)
Aggregeret, anonymiseret statistik per bot-type. Public read.

```sql
CREATE VIEW public_bot_stats AS
SELECT
  bt.display_name AS bot_type,
  count(DISTINCT bi.user_id) AS active_users,
  round(avg(CASE WHEN t.profit_loss > 0
    THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate_pct,
  round(avg(t.profit_loss), 0) AS avg_trade_eur,
  round(sum(t.profit_loss), 0) AS total_profit_eur
FROM bot_types bt
JOIN bot_instances bi ON bi.bot_type_id = bt.id
JOIN trades t ON t.bot_instance_id = bi.id
WHERE t.status = 'closed'
GROUP BY bt.id, bt.display_name;

GRANT SELECT ON public_bot_stats TO anon;
```

### reviews
Bruger-reviews med alias, godkendt af admin foer visning.

```sql
CREATE TABLE public.reviews (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES public.profiles(id),
  alias TEXT NOT NULL,
  bot_type_id UUID REFERENCES public.bot_types(id),
  rating INTEGER CHECK (rating BETWEEN 1 AND 5),
  content TEXT,
  is_approved BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public reads approved reviews"
  ON public.reviews FOR SELECT
  USING (is_approved = true);

CREATE POLICY "Users write own review"
  ON public.reviews FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Owner manages all reviews"
  ON public.reviews FOR ALL
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'owner')
  );
```

### pgcron grace period job
Koerer hver 6. time, uafhaengigt af Python bots.

```sql
SELECT cron.schedule(
  'check-grace-periods',
  '0 */6 * * *',
  $$
  UPDATE bot_instances
  SET is_suspended = true,
      suspended_by = NULL,
      suspended_at = now(),
      suspended_reason = 'Grace period expired — payment overdue'
  WHERE id IN (
    SELECT bi.id FROM bot_instances bi
    JOIN profiles p ON p.id = bi.user_id
    WHERE p.grace_period_ends_at < now()
    AND p.subscription_status = 'past_due'
    AND bi.is_suspended = false
  );
  $$
);
```

## Seed data (bot_types)

```sql
INSERT INTO public.bot_types (name, display_name, description, risk_level) VALUES
  ('aggressive', 'Aggressiv', 'Hoej risiko, hoej reward. Storerre positioner, flere trades.', 5),
  ('moderate', 'Moderat', 'Balanceret tilgang. Standard risk gates.', 3),
  ('passive', 'Passiv', 'Lav risiko, faa trades. Kun stoerste confidence signals.', 1),
  ('aggressive_moderate', 'Aggressiv+Moderat Hybrid', 'Kombinerer aggressiv og moderat strategi.', 4),
  ('daytrader', 'Daytrader', 'Mange trades per dag, tighter stops, hurtig exit.', 4);
```

## AES-256-GCM kryptering

Format i database: Base64-encoded string hvor foerste 12 bytes er IV, resten er ciphertext+tag.

```
[12 bytes IV][ciphertext][16 bytes auth tag] → base64
```

Baade Next.js (`src/lib/crypto.ts`) og Python (`src/utils/crypto.py`) bruger:
- Samme `ENCRYPTION_KEY` (64-char hex = 32 bytes)
- Samme IV format (foerste 12 bytes af decoded base64)
- AES-256-GCM med 128-bit tag
