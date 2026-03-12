# CryptoBot - Project Instructions

## Language
User speaks Danish. Code comments and logs are in English/Danish mix. README is in Danish.

## Architecture
- Rule bot: `main.py` + `config.yaml`
- AI bot: `main_ai.py` + `config_ai.yaml`
- Demo bot: same as rule bot with `config_demo.yaml`
- Dashboard: `dashboard.py` → `src/dashboard/`
- All bots share: `src/strategy/`, `src/risk/`, `src/executor/`, `src/api/`

## Config Files
Config files (`config.yaml`, `config_ai.yaml`, `config_demo.yaml`) are in `.gitignore`.
To update config on VPS, use Python yaml manipulation directly on the server filesystem.
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
ALL trade paths in `main_ai.py` (scan cycle, cycle trade, scale-in) MUST go through the same Python gates in `src/risk/hard_rules.py`. Haiku's decision is only valid if Python says go.

**Pre-AI:** Trading hours → Circuit breaker → Max positions → Min interval → ADX >= 20
**Post-AI:** R:R >= 2.0 → Risk EUR <= 1.5%

All values configurable in `config_ai.yaml` under `trading:` section. Safe defaults if not set.
Never add a new trade path without enforcing ALL gates. Scale-in was missing all gates and caused EUR 576 loss on 2026-03-12.

## Testing
No test framework. Verify changes by checking Docker logs after deploy:
```bash
docker compose logs --tail=50 cryptobot
docker compose logs --tail=50 cryptobot-ai
```

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
