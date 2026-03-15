# CryptoBot SaaS Platform

Next.js 14 + Supabase + Vercel platform til CryptoBot trading bots.

## Tech Stack
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Auth:** Supabase Auth (email/password, 2FA TOTP)
- **Database:** Supabase (PostgreSQL, RLS)
- **Payments:** Stripe (checkout, webhooks, tiers)
- **Charts:** TradingView Advanced Chart (iframe embed, Kraken data)
- **AI Analyse:** Claude Haiku 4.5 via Anthropic API
- **Data Service:** PlatformData container (Flask + ccxt, dedikeret Kraken API)
- **Deployment:** Vercel (manual deploy) + VPS Docker (PlatformData)
- **Kryptering:** AES-256-GCM for API keys

## Live URL
https://platform-one-tawny.vercel.app

## Arkitektur

```
Bruger → Vercel (Next.js)
           ├── Charts → TradingView iframe (direkte fra TradingView, Kraken data)
           ├── AI Chat → /api/chart-analysis → Claude Haiku 4.5
           │              └── /api/prices → PlatformData container (VPS:5100)
           │                                  └── ccxt → Kraken API (dedikeret key)
           ├── Leaderboard → /api/leaderboard → VPS Dashboard (VPS:5000)
           └── Auth/DB → Supabase

Bots → Kraken API (helt separat, egne API keys, egne rate limits)
```

### PlatformData Container
Dedikeret data-service der isolerer platformens Kraken-kald fra bots:
- **Port:** 5100 på VPS
- **Tech:** Flask + ccxt + Gunicorn (2 workers)
- **Endpoints:** `/api/prices`, `/api/ticker`, `/api/orderbook`, `/api/markets`, `/health`
- **Cache:** 10s in-memory cache per endpoint
- **CORS:** Kun `platform-one-tawny.vercel.app` + localhost
- **Fallback:** Hvis PlatformData er nede, falder `/api/prices` tilbage til Kraken public API direkte

## Deployment

### Platform (Vercel)
```bash
# Fra repo root (IKKE platform/)
npx vercel --prod
```
Vercel-projektet har `Root Directory: platform` i settings.

### PlatformData (VPS)
```bash
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot
git pull origin master
docker compose up -d --build platform-data
```

## Env Vars

### Vercel
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
| `PLATFORM_DATA_URL` | PlatformData service URL (`http://91.98.26.70:5100`) |
| `VPS_DASHBOARD_URL` | VPS dashboard URL for leaderboard (`http://91.98.26.70:5000`) |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI chart analyse |

### VPS (.env fil, gitignored)
| Variabel | Beskrivelse |
|----------|-------------|
| `PLATFORM_KRAKEN_API_KEY` | Dedikeret Kraken API key til platformen |
| `PLATFORM_KRAKEN_API_SECRET` | Kraken API secret |
| `CAPITAL_EMAIL` | Capital.com login |
| `CAPITAL_PASSWORD` | Capital.com password |
| `CAPITAL_API_KEY` | Capital.com API key |

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
- `/dashboard/charts` — TradingView chart + AI Chart Analyst
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
| Endpoint | Metode | Beskrivelse |
|----------|--------|-------------|
| `/api/prices` | GET | Krypto OHLCV data (PlatformData → Kraken fallback) |
| `/api/chart-analysis` | POST | AI chart analyse via Claude Haiku |
| `/api/leaderboard` | GET | Proxy til VPS dashboard (auth-beskyttet) |
| `/api/exchange/verify` | POST | Verificer exchange credentials |
| `/api/exchange/save` | POST | Gem krypterede credentials |
| `/api/onboarding/complete` | POST | Afslut onboarding wizard |
| `/api/sync/*` | POST | 5 endpoints for Python bot sync |
| `/api/stripe/*` | POST | Checkout + webhook |
| `/api/telegram/*` | POST | Generate code, verify, disconnect, status |

## Charts & AI Analyse (2026-03-15)

### TradingView Advanced Chart
- Fuldt TradingView charting widget via iframe embed
- **Datakilde:** Kraken via TradingView (ikke Capital.com)
- **Features:** Tegneværktøjer, 100+ indikatorer, alle chart types, alle timeframes
- 25+ coins med hurtig-selector (BTC, ETH, SOL, XRP, ADA, DOGE) + søgbar dropdown
- Brugerens lokale tidszone automatisk
- Dark theme matcher platform

### AI Chart Analyst
- Claude Haiku 4.5 analyserer live Kraken data
- Henter 100 candles fra PlatformData, beregner:
  - Swing highs/lows (S/R niveauer)
  - Fibonacci retracement (0.236, 0.382, 0.5, 0.618, 0.786)
  - Volume, momentum, trend-retning
- Svarer på dansk med konkrete priser
- Timeframe-selector (15m, 1H, 4H, 1D) i chat header
- Rate limit: 10 requests/min, max 500 chars spørgsmål, max 500 candles
- **Kræver:** `ANTHROPIC_API_KEY` i Vercel env vars

## Multi-Exchange Arkitektur

Platformen understøtter multiple exchanges via registry i `src/lib/exchanges.ts`:
- **Active:** Capital.com (3 credential fields), Kraken (chart data)
- **Coming soon:** Binance, Bybit, OKX, Coinbase

### Database
`exchange_accounts` bruger JSONB `credentials_encrypted` kolonne med CHECK constraint for alle exchanges.

## Kendte Issues

### Mock Data
Dashboard, bots, trades, admin panels bruger mock data. Næste step: connect til Supabase.

### RLS Infinite Recursion
Migration fil klar (`20260313000001_fix_rls_recursion.sql`) men IKKE kørt endnu.
Middleware workaround: owner check bruger JWT `app_metadata.role`.

### Stripe Placeholders
Reelle Stripe products + prices skal oprettes i Stripe dashboard.

### Credentials i Git-historik
Capital.com credentials var hardcoded i `docker-compose.yml` og er i git-historikken.
Credentials er nu i `.env` (gitignored). **Roter Capital.com password.**

## DB Migrations

| Fil | Status | Beskrivelse |
|-----|--------|-------------|
| `20260312000001_initial_schema.sql` | Applied | Initiel schema |
| `20260313000001_fix_rls_recursion.sql` | **IKKE kørt** | RLS recursion fix |
| `20260313000002_multi_exchange.sql` | Applied | Multi-exchange support |

## Docker Containers (VPS)

| Container | Port | Formål |
|-----------|------|--------|
| `cryptobot-dashboard` | 5000 | Bot dashboard + leaderboard API |
| `cryptobot-platform-data` | 5100 | Dedikeret Kraken data service for platform |
| `cryptobot-rl1/rd1/ad1/...` | — | Trading bots (ingen ekstern port) |

## Udvikling

```bash
cd platform
npm install
npm run dev      # http://localhost:3000
npx next build   # Type-check + build
```

### Tilføj env var til Vercel
```bash
cd platform
npx vercel env add VARIABEL_NAVN production
# Paste value og tryk Enter
```
