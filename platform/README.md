# CryptoBot SaaS Platform

Next.js 14 + Supabase + Vercel platform til CryptoBot trading bots.

## Tech Stack
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Auth:** Supabase Auth (email/password, 2FA TOTP)
- **Database:** Supabase (PostgreSQL, RLS)
- **Payments:** Stripe (checkout, webhooks, tiers)
- **Deployment:** Vercel (manual deploy, `npx vercel --prod` fra repo root)
- **Kryptering:** AES-256-GCM for API keys

## Live URL
https://platform-one-tawny.vercel.app

## Deployment

```bash
# Fra repo root (IKKE platform/)
npx vercel --prod --yes
```

Vercel-projektet har `Root Directory: platform` i settings. `.vercel/project.json` skal ligge i repo root.

## Env Vars (Vercel)
| Variabel | Beskrivelse |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | For server-side queries |
| `ENCRYPTION_KEY` | 64-char hex, AES-256 nøgle til API key kryptering |
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `SYNC_SECRET` | Shared secret for bot sync endpoints |
| `VPS_DASHBOARD_URL` | **MANGLER** — VPS base URL for leaderboard proxy (f.eks. `http://91.98.26.70:5000`) |

## Sider

### Public
- `/` — Landing page (4 sprog: EN/DA/DE/ES)
- `/login`, `/signup`, `/forgot-password`, `/reset-password`
- `/pricing` — Stripe pricing (Starter/Pro/Elite)
- `/setup-2fa`, `/verify-2fa`

### Protected (kræver login)
- `/dashboard` — Overblik med charts og KPIs
- `/dashboard/bots` — Bot-kort med exchange badge
- `/dashboard/trades` — Trade-historik
- `/dashboard/charts` — Detaljerede charts
- `/dashboard/leaderboard` — Bot ranking (proxy til VPS)
- `/dashboard/settings` — Profil, exchange connection, tema
- `/dashboard/telegram` — Telegram connection

### Admin (kræver `role: owner`)
- `/admin` — Platform overblik
- `/admin/users` — Brugeradministration
- `/admin/bots` — Bot management + kill switch
- `/admin/trades` — Alle trades
- `/admin/audit` — Audit log

### API
- `/api/exchange/verify` — Verificer exchange credentials
- `/api/exchange/save` — Gem krypterede credentials
- `/api/leaderboard` — Proxy til VPS dashboard (auth-beskyttet)
- `/api/onboarding/complete` — Afslut onboarding wizard
- `/api/sync/*` — 5 endpoints for Python bot sync
- `/api/stripe/*` — Checkout + webhook
- `/api/telegram/*` — Generate code, verify, disconnect, status
- `/api/prices` — Live krypto priser

## Multi-Exchange Arkitektur (2026-03-14)

Platformen understøtter multiple exchanges. Kun Capital.com er aktiv; resten vises som "Kommer snart".

### Registry
`src/lib/exchanges.ts` — single source of truth for alle exchanges:
- **Active:** Capital.com (3 credential fields: apiKey, apiPassword, identifier)
- **Coming soon:** Binance, Kraken, Bybit, OKX, Coinbase (2 fields: apiKey, apiSecret)

### Database
`exchange_accounts` tabellen bruger:
- `exchange` kolonne med CHECK constraint for alle 6 exchanges
- `credentials_encrypted` JSONB kolonne (erstatter 3 separate kolonner)
- Migration: `supabase/migrations/20260313000002_multi_exchange.sql` (APPLIED)

### Onboarding
Step 2 viser exchange picker grid med 6 kort. Coming-soon exchanges er disabled med "Soon" badge. Credential-formularen renderer dynamisk baseret på valgt exchange's `credentialFields`.

## Leaderboard

Proxyer til VPS bot dashboard via `VPS_DASHBOARD_URL` env var.

**Status:** HTTP 503 fordi `VPS_DASHBOARD_URL` ikke er sat i Vercel endnu.

**TODO:** Sæt `VPS_DASHBOARD_URL` i Vercel env vars (f.eks. `http://91.98.26.70:<PORT>`).

Features:
- Auth-beskyttet API route
- Filter per bot type (Rule/Scalper/AI)
- Sortable kolonner med keyboard support
- KPI cards (Aktive bots, Composite Score, P&L, Top Bot)
- Response validation og AbortController cleanup

## Kendte Issues

### VPS_DASHBOARD_URL mangler
Leaderboard viser 503. Sæt env var i Vercel.

### RLS Infinite Recursion
Migration fil klar (`20260313000001_fix_rls_recursion.sql`) men IKKE kørt endnu.
Middleware workaround: owner check bruger JWT `app_metadata.role`.

### Mock Data
Dashboard, bots, trades, admin panels bruger alle mock data. Næste step: connect til Supabase.

### Stripe Placeholders
Reelle Stripe products + prices skal oprettes i Stripe dashboard.

## DB Migrations

| Fil | Status | Beskrivelse |
|-----|--------|-------------|
| `20260312000001_initial_schema.sql` | Applied | Initiel schema |
| `20260313000001_fix_rls_recursion.sql` | **IKKE kørt** | RLS recursion fix |
| `20260313000002_multi_exchange.sql` | Applied | Multi-exchange support |

## Udvikling

```bash
cd platform
npm install
npm run dev      # http://localhost:3000
npx next build   # Type-check + build
```
