# Architecture Reference

## Mappeansvar

| Mappe | Ansvar | Regler |
|-------|--------|--------|
| `src/app/(public)/` | Offentlige sider: landing, pricing, reviews | Ingen auth krav |
| `src/app/(auth)/` | Login, signup, verify-2fa, setup-2fa, callback | Redirecter vaek hvis allerede logget ind |
| `src/app/(protected)/` | Dashboard, onboarding, settings | Kraever auth + middleware guard |
| `src/app/admin/` | Owner-only admin panel | Kraever role=owner + has_2fa=true |
| `src/app/api/` | API routes (Stripe, sync, admin, auth) | Server-side only, validerer input |
| `src/components/ui/` | Primitive UI (button, card, input, badge, table) | Ingen forretningslogik, kun styling |
| `src/components/layout/` | Sidebar, Header, ThemeSelector, DashboardLayout | Wrapper-komponenter |
| `src/components/dashboard/` | Widgets: BalanceChart, TradeTable, BotStatus, PnlCard | Modtager data via props fra hooks |
| `src/components/landing/` | Hero, Features, PricingCards, Footer | Statiske + constants |
| `src/components/admin/` | UserTable, BotTable, PlatformStats | Owner-only data via admin hooks |
| `src/components/onboarding/` | WizardShell, StepExchange, StepApiKeys, StepBotConfig, StepTelegram | Wizard flow state |
| `src/hooks/` | Client-side data hooks | Eneste sted der kalder Supabase fra client |
| `src/lib/` | Utils, constants, Supabase clients, Stripe, crypto | Delt logik, ingen UI |
| `src/types/` | TypeScript interfaces og types | Database types + custom types |
| `services/bot-orchestrator/` | Bot lifecycle management | Stub fase 1, implementeres fase 2 |
| `references/` | Tung dokumentation | Ikke kode — kun reference for Claude/mennesker |
| `scripts/` | Validation og utility scripts | Bash scripts, chmod +x |
| `supabase/migrations/` | Database migrations | Nummereret sekventielt (001_, 002_, ...) |

## Udvidelsesregler

### Tilfoej ny feature
1. Definer types i `src/types/`
2. Tilfoej Supabase tabel/migration i `supabase/migrations/` (naeste nummer)
3. Opret data-hook i `src/hooks/` (kalder Supabase)
4. Byg komponent i relevant `src/components/` undermappe
5. Saml i page.tsx (kun composition, ingen logik)
6. Tilfoej RLS policy i migration
7. Test RLS: bruger ser kun egne data, owner ser alt

### Tilfoej ny API route
1. Opret i `src/app/api/[feature]/route.ts`
2. Valider input (zod eller manual)
3. Brug Supabase admin client (service role) for server operations
4. Returner JSON response med korrekt status code
5. Log i audit_log for admin-actions

### Tilfoej ny bot-type
1. Insert i `bot_types` tabel (via migration eller seed)
2. Opdater `BOT_TYPES` constant i `src/lib/constants.ts`
3. `public_bot_stats` view opdaterer automatisk

## Arkitektur-beslutninger

| Dato | Beslutning | Begrundelse |
|------|-----------|-------------|
| 2026-03-12 | En Docker container per bruger-bot | Isolation, simpelt, robust — ingen multi-tenant kompleksitet |
| 2026-03-12 | Manuel bot-opstart fase 1 | Anton starter manuelt. BotOrchestrator interface defineret til fase 2 automatisering |
| 2026-03-12 | Python og Next.js deler ENCRYPTION_KEY | Python henter krypterede keys direkte fra Supabase, dekrypterer lokalt |
| 2026-03-12 | pgcron for grace period check | Uafhaengig af Python bot — virker ved crash. Koerer hver 6. time |
| 2026-03-12 | Subscriber dashboard bygges fra scratch | Separat fra Antons interne dashboard.py — bruger Supabase data |
| 2026-03-12 | Public bot stats via aggregeret view | Anonymiseret, ingen bruger-identitet. RLS: anon kan SELECT |
| 2026-03-12 | Reviews med alias + admin approval | is_approved = false default. Anton godkender foer visning |
| 2026-03-12 | Login er eneste adgangskontrol | Intet domane, Vercel URL. RLS er fundamentet for data isolation |
