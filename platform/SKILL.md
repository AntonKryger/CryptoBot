---
name: cryptobot-saas-platform
description: SaaS crypto trading platform development.
  Use when building auth flows, Supabase schema, Stripe
  integration, onboarding wizard, dashboard components,
  bot orchestration, or any feature in the platform/
  directory. Triggers on: "build auth", "add stripe",
  "create onboarding", "supabase migration", "dashboard
  feature", "bot orchestrator", "kill switch", "RLS
  policy", "bot suspend", "onboarding step",
  "stripe webhook", "2FA setup", "bot-type stats",
  "public aggregated data", "reviews table".
metadata:
  author: Anton Kryger
  version: 1.0.0
  category: saas-platform
---

# CryptoBot SaaS Platform

## Quick Reference
- **Stack:** Next.js 14 (App Router), Supabase, Stripe, Tailwind CSS
- **Dev:** `cd platform && npm run dev -- -p 3001`
- **Build:** `cd platform && npm run build`
- **Migrations:** `supabase/migrations/` (nummereret sekventielt)
- **Arkitektur + mappestruktur:** `references/architecture.md`
- **Database schema:** `references/database-schema.md`
- **Bot orchestrator spec:** `references/bot-orchestrator.md`
- **Stripe flows:** `references/stripe-flows.md`
- **Env validation:** `bash scripts/validate-env.sh`

---

## Projekt
SaaS crypto trading platform. Brugere betaler one-time + monthly for AI bot trading via Capital.com.
Anton (owner) har admin panel og bypasser alle gates.

## Tech Stack
- Next.js 14 (App Router) + TypeScript
- Supabase (Auth + PostgreSQL + RLS + Realtime + 2FA)
- Stripe (Payment Intent + Subscription)
- Tailwind CSS + CSS variable themes
- Recharts, lucide-react
- Deploy: Vercel (platform/ as root)

## Naeste Steps
- Connect dashboard til live Supabase data (replace mock data)
- Configure Stripe med rigtige price IDs
- Python bot integration (kill switch, sync endpoints)
- Custom domain setup
- E2E tests

---

## ARBEJDSREGLER (KRITISKE)

### 1. Single Source of Truth for data
Data skal defineres ET sted og genbruges overalt.

- **Balance**: Hentes fra Supabase `bot_instances` eller API — ALDRIG hardcodet.
  Brug en shared hook/util: `useAccountBalance()` eller `getBalance()`.
- **Trade data**: Fra `trades` table via Supabase. En query, et format.
  Formatering via shared utils (`formatCurrency`, `formatPercent`).
- **Bot status**: En kilde (`bot_instances` table), en hook (`useBotStatus()`).

**ALDRIG**:
- Hardcode tal som `94681.42` noget sted
- Beregn samme vaerdi paa to forskellige maader
- Duplicate queries til samme data
- Kopier formaterings-logik mellem komponenter

**ALTID**:
- Definer data-fetching i `src/lib/` eller `src/hooks/`
- Komponenter kalder hooks, hooks kalder Supabase
- Hvis X vises 3 steder, skal X komme fra 1 hook

### 2. Dokumenter ved HVER milestone
Naar en opgave er faerdig, opdater Changelog i denne fil.

### 3. Kode-kvalitet
- Ingen magic numbers — brug constants fra `src/lib/constants.ts`
- Alle priser/beloeb formateres via `formatCurrency()` fra `src/lib/utils.ts`
- Alle procenter via `formatPercent()`
- TypeScript strict — ingen `any` types
- Komponenter er smaa og fokuserede
- Server components som default, client components kun naar noedvendigt
- Ingen logik i page.tsx — kun composition
- Hooks henter data, komponenter viser data
- services/ eksponeres kun via api/ routes
- Aldrig importer paa tvaers af app/ routes direkte

### 4. Supabase RLS
- Brugere ser KUN egne data
- Owner (Anton) ser ALT
- `platform_stats` er public read
- `public_bot_stats` view er public read (aggregeret, anonymiseret)
- `reviews` er public read (kun is_approved = true)
- Test RLS policies efter hver migration

### 5. Stripe
- Aldrig gem card details
- Brug Payment Intent (one-time) + Subscription (monthly)
- Webhook verification med signing secret
- Idempotency keys paa alle mutations

---

## Pricing Tiers
| Tier | One-time | Monthly | Bots | Coins |
|------|----------|---------|------|-------|
| Starter | EUR 149 | EUR 19/mo | 1 | 3 |
| Pro | EUR 349 | EUR 39/mo | 3 | All 6 |
| Elite | EUR 799 | EUR 79/mo | Unlimited | All 6 |

Defineret i `src/lib/constants.ts` (TIERS) og `src/lib/stripe/plans.ts`.
ALDRIG hardcode priser i komponenter.

---

## Middleware Routing (Step 3 — DONE)
```
unauthenticated + protected route -> /login
owner -> /admin (krav: has_2fa=true, ellers -> /setup-2fa)
subscriber uden onboarding -> /onboarding
subscriber uden tier -> /pricing
subscriber med alt -> /dashboard
visitor -> /pricing
Owner bypasser ALLE gates
```

---

## Filstruktur
```
platform/
  src/app/
    (public)/       — landing, pricing, reviews
    (auth)/         — login, signup, verify-2fa
    (protected)/    — dashboard, onboarding
    admin/          — kun owner
    api/            — API routes
  src/components/
    ui/             — primitive komponenter
    layout/         — header, sidebar, nav
    dashboard/      — dashboard widgets
    landing/        — landing page sektioner
    admin/          — admin panel komponenter
    onboarding/     — wizard steps
  src/hooks/        — useBalance, useBotStatus, useTheme
  src/lib/
    supabase/       — client, server, middleware
    stripe/         — plans, webhook handlers
    crypto.ts       — AES-256-GCM encrypt/decrypt
    constants.ts    — TIERS, ALLOWED_COINS, BOT_TYPES
    utils.ts        — formatCurrency, formatPercent
  src/types/        — alle TypeScript interfaces
  services/
    bot-orchestrator/ — stub nu, implementeres fase 2
  references/       — tung dokumentation
  scripts/          — validate-env, check-migrations
  supabase/
    migrations/     — en fil per migration, nummereret
    seed/           — bot_types seed data
```

---

## Allowed Coins
BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD
Banned: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD
Defineret i `src/lib/constants.ts` (ALLOWED_COINS).

---

## Common Issues

**Supabase RLS fejler / bruger ser andres data:**
```sql
SELECT * FROM pg_policies WHERE tablename = 'trades';
```
Tjek `auth.uid()` matcher `user_id` i query.
Owner bypass pattern:
```sql
WHERE user_id = auth.uid() OR EXISTS (
  SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'owner'
)
```

**Build fejler efter ny komponent:**
- Mangler `'use client'` paa client component?
- Bruger hooks i server component?
- Kør: `cd platform && npm run build`

**Stripe webhook fejler lokalt:**
```bash
stripe listen --forward-to localhost:3001/api/webhooks/stripe
```
Tjek `STRIPE_WEBHOOK_SECRET` matcher `stripe listen` output.

**Middleware redirect loop:**
- Matcher i `middleware.ts` maa ikke fange `/login` selv
- Owner maa aldrig ramme `/pricing` eller `/onboarding`

**2FA blokerer owner login:**
- Owner SKAL have 2FA — paakraevet, ikke valgfrit
- Saet `has_2fa = true` i profiles efter setup

**AES dekryptering fejler i Python:**
- `ENCRYPTION_KEY` skal vaere identisk i `.env` og VPS
- IV gemmes med encrypted value (første 12 bytes af base64-encoded string)
- Python og Next.js bruger samme key + IV-format

---

## Nuvaerende Status (2026-03-13)
Steps 1-16 BUILT. 98 source files, 36 routes. Deployed to Vercel.
Landing page med 4-sprogs sprogvaelger (EN default).
Supabase auth + RLS. Stripe checkout flow. Full dashboard med mock data.

## Changelog
- [2026-03-13] Steps 5-16 done: FULL PLATFORM BUILD (98 files, 36 routes)
  - Step 5: 2FA setup (TOTP enroll + QR code + verify)
  - Steps 6-8: Stripe (pricing page, checkout, webhook handler)
  - Step 9: Onboarding wizard (4 steps: welcome, exchange, bot config, complete)
  - Step 10: Telegram connection (6-digit code, polling, disconnect)
  - Step 12: Admin panel (overview, users, bots, trades, audit log, kill switch)
  - Step 13: Full dashboard (sidebar, header, theme selector, PnlCards, BalanceChart, BotStatus, TradeTable, trades/bots/settings/telegram sub-pages)
  - Step 14: Sync API endpoints (heartbeat, trade, trade-close, bot-status, stats)
  - Step 15: Landing page (4 languages, all links fixed, EN default)
  - Step 16: Vercel deployment (platform-one-tawny.vercel.app)
  - Extra: Password reset flow, 404/error pages, loading skeletons, SEO metadata, Skeleton UI component
  - Middleware gates re-enabled (tier → pricing, subscription → checkout, onboarding → wizard)
  - Supabase auth config: Site URL + Redirect URLs set via API
- [2026-03-12] Step 4 done: Auth pages (login, signup, verify-2fa, callback)
  - Nye filer: `src/app/(auth)/layout.tsx`, `src/app/(auth)/login/page.tsx`, `src/app/(auth)/signup/page.tsx`, `src/app/(auth)/verify-2fa/page.tsx`, `src/app/(auth)/callback/route.ts`
  - Nye komponenter: `src/components/auth/LoginForm.tsx`, `SignupForm.tsx`, `TwoFactorInput.tsx`
  - AEndret: `src/middleware.ts` (tilfojet /verify-2fa og /setup-2fa til public routes)
  - Login → password auth → MFA check → redirect eller /verify-2fa
  - Signup → email confirmation → callback → /pricing
  - 2FA: 6-digit input med auto-advance, paste support, auto-submit
  - Callback: exchange code for session, redirect til destination
  - Build passes clean, alle routes returnerer korrekt status
  - Naeste step: Step 5 — 2FA Setup (TOTP enroll + QR)
- [2026-03-12] Supabase projekt oprettet og linked (tuxdcpawpetbdsxckcir)
  - Migration 001 applied (rettede uuid_generate_v4 → gen_random_uuid)
  - Migration filformat aendret til timestamp (20260312000001_initial_schema.sql)
  - .env.local konfigureret med alle keys
- [2026-03-12] SKILL.md omstruktureret: YAML frontmatter, references/ mappe, scripts/, bot-orchestrator stubs, common issues sektion
- [2026-03-12] Step 3 done: Middleware (auth guard + role-based routing)
  - Nye filer: `src/middleware.ts`, `src/lib/supabase/middleware.ts`
  - AEndret: `src/app/(protected)/layout.tsx` (server-side auth check)
  - Routing: unauthenticated→/login, owner→bypass all (2FA required for /admin), subscriber→pricing→onboarding→dashboard
  - Build passes clean, middleware 75.1 kB
- [2026-03-12] Landing page V7 valgt (V3 layout + V2 violet/fuchsia farvepalette)
- [2026-03-12] Steps 1-2 done: Next.js init, 5 themes, fonts, 6 UI components, layout, landing page mockup, dashboard mockup, Supabase schema SQL, Supabase helpers, Stripe config, AES-256-GCM encryption, env template
