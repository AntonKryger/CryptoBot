# CryptoBot - Project Instructions

## Language
User speaks Danish. Code comments and logs are in English/Danish mix. README is in Danish.

## Architecture — Hybrid Shared Code per Bot Type
Each bot type shares ONE `src/` codebase. Variants within a type share code but have separate configs.

```
RuleBot/
  src/                    ← shared by ALL RuleBot variants
  main.py                 ← shared
  dashboard.py            ← shared (Gunicorn entry)
  Dockerfile              ← shared (builds one image per type)
  requirements.txt        ← shared
  config.example.yaml     ← template
  Live/RL1/config.yaml    ← variant-specific (+ data/, logs/)
  Demo/RD1/config.yaml
  Demo/RD2/config.yaml
  Demo/RD3/config.yaml

ScalpingBot/              ← same pattern
  src/, main.py, Dockerfile
  Demo/SD1/, SD2/, SD3/, SD4/

AIBot/                    ← same pattern
  src/, main_ai.py, Dockerfile
  Demo/AD1/, AD2/

AICoach/                  ← coaches share code too
  src/, main_coach.py, Dockerfile
  AC1/                    ← AI Coach (coaches AI bots)
  RuleCoach/RC1/          ← Rule Coach (coaches rule bots)
  ScalpCoach/SC1/         ← Scalp Coach (coaches scalper bots)
  MasterCoach/MC1/        ← Meta-coach (compares best from each type)
```

Docker-compose mounts variant config as volume:
```yaml
rd2:
  build: ./RuleBot
  volumes:
    - ./RuleBot/Demo/RD2/config.yaml:/app/config.yaml:ro
    - ./RuleBot/Demo/RD2/data:/app/data
```

## Variant System
- `variants.yaml` — central registry of all bot variants (profiles, coins, overrides)
- `scripts/generate_variant.py` — generates config.yaml + docker-compose.generated.yml
- 7 risk profiles: ultra_conservative, conservative, balanced, moderate, moderate_aggressive, aggressive, ultra_aggressive
- Built-in profiles in `src/config.py` (BUILTIN_PROFILES dict)
- `scan_offset_seconds` staggers API calls across variants

## Exchange Adapter Layer
Bots NEVER call exchange APIs directly. All communication goes through `src/exchange/`:
- `base_adapter.py` — abstract interface all adapters must implement
- `capital_adapter.py` — Capital.com CFD implementation (production, live + demo)
- `kraken_adapter.py` — Kraken spot + futures via ccxt (production, SD1/SD2)
- `binance_adapter.py` — stub (NotImplementedError)
- `factory.py` — `get_adapter(config)` returns the right adapter based on config

Main entry points use `from src.exchange import get_adapter` instead of `CapitalClient`.

### Capital.com config:
```yaml
exchange:
  provider: capital
  email: ...
  password: ...
  api_key: ...
  demo: true
  account_name: "RL1"
```

### Kraken config:
```yaml
exchange:
  provider: kraken
  api_key: "..."
  api_secret: "..."
  mode: spot          # spot (default) or futures
  demo: false         # futures has demo endpoint; spot does not
```

Legacy `capital:` config format is still supported as fallback.

### Kraken Adapter Details
- Uses `ccxt` library (unified exchange API, supports 100+ exchanges)
- Symbol mapping: bots use `BTCUSD` or `BTC/USD` — adapter handles both formats
- Resolution mapping: Capital.com format (`HOUR`, `MINUTE_15`) → ccxt format (`1h`, `15m`)
- Price data returned in Capital.com-compatible format (downstream code needs no changes)
- Spot mode: `ccxt.kraken` — 24/7 crypto markets, no session needed
- Futures mode: `ccxt.krakenfutures` — with sandbox/demo support
- SL/TP via linked orders (Kraken has no native SL/TP on positions)
- API key needs: Query funds, Query orders, Create/modify orders, Cancel orders, Query ledger

### Exchange-Specific Gotchas
**Capital.com:**
- `update_position()` MUST send both SL and TP, or the missing one gets cleared
- `dealReference` from create_position is NOT the same as `dealId` from positions API. Use `/api/v1/confirms/{dealRef}` to get real dealId

**Kraken:**
- Crypto markets are 24/7 (no market hours check needed)
- Spot has no demo mode — use futures sandbox for testing
- SL/TP are separate conditional orders, not attached to positions
- Spread is much lower than Capital.com ($0.10 BTC vs $30+ CFD)

## Config Files
Each variant has its own `config.yaml` in its directory. All `**/config.yaml` files are in `.gitignore`.
To update config on VPS, edit directly on the server filesystem or use `generate_variant.py`.
Never commit config files to git.

## Deployment
After code changes: `git push origin master`, then SSH to VPS and rebuild Docker.
```bash
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot && git pull origin master
docker compose down && docker compose up -d --build
```

For variant batches:
```bash
python scripts/generate_variant.py --batch A
docker compose -f docker-compose.generated.yml up -d --build
```

## Key Rules
- VPS timezone is UTC. Dashboard converts to Danish time (CET/CEST) in browser.
- CryptoPanic API rate-limits aggressively. Bots sharing the same API key will get 429 errors.

## Hard Gates (AI Bot)
ALL trade paths in `AIBot/main_ai.py` (scan cycle, cycle trade, scale-in) MUST go through the same Python gates in `src/risk/hard_rules.py`. Haiku's decision is only valid if Python says go.

**Pre-AI:** Trading hours → Circuit breaker → Max positions → Min interval → ADX >= 20
**Post-AI:** R:R >= 2.0 → Risk EUR <= 1.5%

All values configurable in `config.yaml` under `trading:` section. Safe defaults if not set.
Never add a new trade path without enforcing ALL gates. Scale-in was missing all gates and caused EUR 576 loss on 2026-03-12.

## R:R Ratio — CRITICAL
`min_rr_ratio` in `src/risk/manager.py` MUST be `2.0` (matching hard_rules). If set to 1.5, RiskManager adjusts TP to R:R 1.5:1, then HardRules blocks it for being < 2.0:1. This caused AD1 to find signals but never trade.

## Watchdog Tuning (updated 2026-03-14)
Default values tuned to prevent early profit-taking:

| Parameter | Default | Description |
|---|---|---|
| `breakeven_trigger_pct` | 2.5% | Move SL to entry (was 1.5%) |
| `progressive_sl_trigger_pct` | 3.0% | Start trailing SL (was 2.0%) |
| `pullback_peak_trigger_pct` | 4.0% | Peak profit to trigger pullback close (was 2.5%) |
| `pullback_min_profit_pct` | 1.5% | NEW: minimum current P/L to allow pullback close |
| `partial_profit_pct` | 6.0% | Take partial profit (was 4.0%) |
| `partial_close_ratio` | 0.3 | Close 30% at partial (was 50%) |

## Testing
No test framework. Verify changes by checking Docker logs after deploy:
```bash
docker compose logs --tail=50 cryptobot-rl1
docker compose logs --tail=50 cryptobot-ad1
docker compose logs --tail=50 cryptobot-sd1
```

## Preflight Check
Run `python preflight_check.py` before `docker compose up` to verify no two bots share the same credentials + sub-account.
Now reads from `variants.yaml` for auto-discovery of all variant configs.

## Coaches
- **Dedicated coaches per bot type**: RuleCoach (RC1) evaluates only RuleBots, ScalpCoach (SC1) only ScalpBots, AICoach (AC1) only AIBots
- **MasterCoach (MC1)**: Meta-coach that compares the best from each type, runs weekly
- Coaches use `strategy_profiles.py` for profile-aware evaluation (knows a conservative bot should have fewer trades)
- `leaderboard.py` generates composite scores (Sharpe, profit factor, win rate, drawdown, volume)
- Leaderboard exported to `data/leaderboard.json`, accessible via `/coach_leaderboard` Telegram command

## Friday Evening Trading
Not a hard block. Friday after 20:00 CET: only IMPULSE structures (BULLISH_IMPULSE, BEARISH_IMPULSE) are allowed. CORRECTIVE and UNCLEAR are blocked. Implemented in `hard_rules.check_friday_structure_gate()`.

## Bot Identity
Each bot prints an identity banner at startup (Bot ID, email, credential hash, sub-account). Telegram messages are prefixed with `[BOT_ID]`. This prevents cross-bot confusion.

## Coins
**Capital.com (CFD):** BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD
**Kraken (Spot):** BTC/USD, ETH/USD, SOL/USD, AVAX/USD, LINK/USD, LTC/USD
Banned on Capital.com: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD

## Current Bot Deployment (2026-03-14)

| Bot | Exchange | Mode | Coins | Profile |
|-----|----------|------|-------|---------|
| RL1 | Capital.com | Live | All 6 | moderate |
| RD1 | Capital.com | Demo | All 6 | moderate |
| AD1 | Capital.com | Demo | All 6 | moderate |
| SD1 | **Kraken** | Live (spot) | BTC/USD, ETH/USD | conservative |
| SD2 | **Kraken** | Live (spot) | SOL/USD, AVAX/USD, LINK/USD, LTC/USD | moderate |

## CRITICAL BUG: P/L Data Integrity (2026-03-12)
Dashboard P/L values DO NOT match Capital.com. Root causes:
1. **Duplicate trades**: CSV import + bot tracking create 2 entries for the same trade
2. **Estimated P/L**: Watchdog calculates P/L from price×size (ignoring spread/fees)
3. **Reconcile mismatch**: Same Capital.com transaction matched to multiple DB rows

**DO NOT run `clean_reimport.py`** — it creates duplicates.
Before working on trade data, read the full analysis in README.md "KRITISK: P/L Data-Integritetsproblem".
Proposed solutions: A) nuke+reimport from API only, B) deduplicate, C) dealId-matching reconcile, D) hybrid.
