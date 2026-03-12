# CryptoBot — Skill & Working Guidelines

## Projekt
Automatiseret crypto CFD trading bot paa Capital.com. To bots: rule-based (main.py) og AI-powered (main_ai.py).
Deployed via Docker paa Hetzner VPS (91.98.26.70).

## Arkitektur
- Rule bot: `main.py` + `config.yaml`
- AI bot: `main_ai.py` + `config_ai.yaml`
- Demo bot: `main.py` + `config_demo.yaml`
- Dashboard: `dashboard.py` -> `src/dashboard/`
- Shared: `src/strategy/`, `src/risk/`, `src/executor/`, `src/api/`

## ARBEJDSREGLER (KRITISKE)

### 1. Hard Gates — ALDRIG bypass
Alle trade paths (scan, cycle, scale-in) SKAL gaa gennem `src/risk/hard_rules.py`.
Pre-AI: Trading hours -> Circuit breaker -> Max positions -> Min interval -> ADX >= 20
Post-AI: R:R >= 2.0 -> Risk EUR <= 1.5%
Tilfoej ALDRIG en ny trade path uden at enforce ALLE gates.

### 2. Single Source of Truth
- Config-vaerdier laeses fra YAML, aldrig hardcodet i kode
- Safe defaults i `hard_rules.py` hvis config mangler
- Balance/positions hentes fra Capital.com API, aldrig estimeret
- P/L data: Se KRITISK BUG i CLAUDE.md — dashboard-tal er IKKE paalidelige

### 3. Dokumenter ved HVER milestone
Naar en opgave er faerdig, opdater Changelog nedenfor med:
- Dato og kort beskrivelse
- Filer oprettet/aendret/fjernet
- Hvad er naeste step
- Kendte issues

### 4. Allowed Coins
BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD
Banned: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD

### 5. Deploy-flow
```bash
git push origin master
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot && git pull origin master
docker compose down && docker compose up -d --build
```

### 6. Koordinering med platform/
SaaS-platformen bygges i `platform/` med sin egen `SKILL.md`.
Begge instanser laaser DENNE fil og `platform/SKILL.md`.
Step 11 (PlatformSync i `src/platform/`) er overlap-punktet — koordiner via changelog.

---

## Changelog

### 2026-03-12
- **Hard gates implementeret** (commits 6e292af, 78763d9)
  - Ny fil: `src/risk/hard_rules.py` (HardRules class, SQLite persistence, 7 gates)
  - AEndret: `main_ai.py` (alle 3 trade paths enforcer gates)
  - AEndret: `src/risk/manager.py` (risk calc support)

- **Telegram chat-crash fix**
  - AEndret: `src/strategy/ai_analyst.py`
  - Problem: Tomme beskeder i SQLite -> API 400 error ved message #68
  - Fix: Filtrerer tomme beskeder ved load + skipper tom-save

- **AI chat-prompt strammet**
  - AEndret: `src/strategy/ai_analyst.py`
  - Chat system prompt: maks 150 ord, maks 2 emojis, ingen headers, ingen gentagelser
  - max_tokens reduceret 800 -> 400
  - Problem: AI brugte 90% af tokens paa emojis og selvros

- **Tidligere fixes (samme dag)**
  - Telegram HTML parse fix (commit 1baa163)
  - Danish-only prompts (commit 565a72b)
  - Chat context crash fix for None profit (commit 1228710)
  - Portfolio injection logging (commit 1228710)
