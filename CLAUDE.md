# CryptoBot - Project Instructions

## Language
User speaks Danish. Code comments and logs are in English/Danish mix. README is in Danish.

## Architecture — Separate Codebases per Bot
Each bot type has its **own directory with its own `src/` code**. No shared code between bot types.

```
RuleBot/Live/RL1/   — Live rule bot (main.py + src/)
RuleBot/Demo/RD1/   — Demo rule bot (main.py + src/)
AIBot/Demo/AD1/     — AI bot (main_ai.py + src/)
ScalpingBot/Demo/SD1/ — Scalper bot (main.py + src/)
ScalpingBot/Demo/SD2/ — Scalper bot (main.py + src/)
AICoach/AC1/        — AI Coach (main_coach.py + src/)
```

Each bot directory contains: `main*.py`, `src/`, `Dockerfile`, `requirements.txt`, `config.example.yaml`.
The root `src/` directory is legacy and should not be used for new work.

Dashboard currently builds from `RuleBot/Live/RL1/` context (temporary).

## Config Files
Each bot has its own `config.yaml` in its directory. All `**/config.yaml` files are in `.gitignore`.
To update config on VPS, edit directly on the server filesystem.
Never commit config files to git.

## Deployment
After code changes: `git push origin master`, then SSH to VPS and rebuild Docker.
```bash
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot && git pull origin master
docker compose down && docker compose up -d --build
```

## Key Rules
- VPS timezone is UTC. Dashboard converts to Danish time (CET/CEST) in browser.
- Capital.com `update_position()` MUST send both SL and TP, or the missing one gets cleared.
- `dealReference` from create_position is NOT the same as `dealId` from positions API. Use `/api/v1/confirms/{dealRef}` to get real dealId.
- CryptoPanic API rate-limits aggressively. Both bots share the same API key.

## Hard Gates (AI Bot)
ALL trade paths in `AIBot/Demo/AD1/main_ai.py` (scan cycle, cycle trade, scale-in) MUST go through the same Python gates in `src/risk/hard_rules.py`. Haiku's decision is only valid if Python says go.

**Pre-AI:** Trading hours → Circuit breaker → Max positions → Min interval → ADX >= 20
**Post-AI:** R:R >= 2.0 → Risk EUR <= 1.5%

All values configurable in `config.yaml` under `trading:` section. Safe defaults if not set.
Never add a new trade path without enforcing ALL gates. Scale-in was missing all gates and caused EUR 576 loss on 2026-03-12.

## R:R Ratio — CRITICAL
`min_rr_ratio` in `src/risk/manager.py` MUST be `2.0` (matching hard_rules). If set to 1.5, RiskManager adjusts TP to R:R 1.5:1, then HardRules blocks it for being < 2.0:1. This caused AD1 to find signals but never trade.

## Testing
No test framework. Verify changes by checking Docker logs after deploy:
```bash
docker compose logs --tail=50 cryptobot-rl1
docker compose logs --tail=50 cryptobot-ad1
docker compose logs --tail=50 cryptobot-sd1
```

## Preflight Check
Run `python preflight_check.py` before `docker compose up` to verify no two bots share the same credentials + sub-account.

## Friday Evening Trading
Not a hard block. Friday after 20:00 CET: only IMPULSE structures (BULLISH_IMPULSE, BEARISH_IMPULSE) are allowed. CORRECTIVE and UNCLEAR are blocked. Implemented in `hard_rules.check_friday_structure_gate()`.

## Bot Identity
Each bot prints an identity banner at startup (Bot ID, email, credential hash, sub-account). Telegram messages are prefixed with `[BOT_ID]`. This prevents cross-bot confusion.

## Coins
Allowed: BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD
Banned: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD

## CRITICAL BUG: P/L Data Integrity (2026-03-12)
Dashboard P/L values DO NOT match Capital.com. Root causes:
1. **Duplicate trades**: CSV import + bot tracking create 2 entries for the same trade
2. **Estimated P/L**: Watchdog calculates P/L from price×size (ignoring spread/fees)
3. **Reconcile mismatch**: Same Capital.com transaction matched to multiple DB rows

**DO NOT run `clean_reimport.py`** — it creates duplicates.
Before working on trade data, read the full analysis in README.md "KRITISK: P/L Data-Integritetsproblem".
Proposed solutions: A) nuke+reimport from API only, B) deduplicate, C) dealId-matching reconcile, D) hybrid.
