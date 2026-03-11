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

## Testing
No test framework. Verify changes by checking Docker logs after deploy:
```bash
docker compose logs --tail=50 cryptobot
docker compose logs --tail=50 cryptobot-ai
```

## Coins
Allowed: BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD
Banned: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD
