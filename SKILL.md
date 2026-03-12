# CryptoBot — Skill & Working Guidelines

## Projekt
Automatiseret crypto CFD trading bot paa Capital.com. Multi-bot arkitektur med fuld isolation pr. bot.
Deployed via Docker paa Hetzner VPS (91.98.26.70).

## Arkitektur
- Entry points: `main.py` (rule/scalper bots), `main_ai.py` (AI bots)
- Shared kode: `src/strategy/`, `src/risk/`, `src/executor/`, `src/api/`
- Dashboard: `dashboard.py` -> `src/dashboard/` (auto-discovers bot DBs via `BOT_DATA_DIR`)
- Hver bot = 1 Docker service + 1 config fil + egne data/logs volumes

## Multi-Bot Navneskema
`{TYPE}{MODE}{NUMMER}` — f.eks. RL1, AD1, SD1
| Kode | Betydning |
|------|-----------|
| RL1 | Rule Live 1 |
| RD1 | Rule Demo 1 |
| AL1 | AI Live 1 |
| AD1 | AI Demo 1 |
| SL1 | Scalper Live 1 |
| SD1 | Scalper Demo 1 |

Bot ID bruges i: config-filnavn (`config_rl1.yaml`), Docker service/container, data-mappe (`data_rl1/`), log-mappe (`logs_rl1/`), log-prefix `[RL1]`, dashboard.

## Docker-struktur
- YAML anchors: `x-bot-common` for faelles settings
- Host config `config_{id}.yaml` mountes som `/app/config.yaml` i containeren
- Data: `./data_{id}:/app/data`, Logs: `./logs_{id}:/app/logs`
- Dashboard: bot data mountes read-only under `/app/bot_data/{id}/`
- Tilfoej ny bot: kopier service-blok, aendr 3 linjer (id, config, volumes)

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

### 6. Tilfoej ny bot
1. Opret Capital.com konto, navngiv efter bot ID
2. Kopier `config.example.yaml` til `config_{id}.yaml` paa VPS
3. Udfyld credentials og `bot:` sektion (id, name, type)
4. Tilfoej service-blok i `docker-compose.yml` (copy-paste, aendr id)
5. Tilfoej volume-mount til dashboard service
6. `docker compose up -d --build`

### 7. Koordinering med platform/
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

- **AI analyse-prompt overhalet** (commits f8c0b0f, 5e289f6)
  - AEndret: `src/strategy/ai_analyst.py` — SYSTEM_PROMPT
  - Ny 5-checkpoint scoring: trend/regime, momentum, price action, sentiment, R:R
  - Haiku SKAL eksplicit besvare alle 5 checkpoints foer signal
  - Scoring: 5/5=conf 9-10, 4/5=conf 7-8, <4=HOLD
  - Ranging markets kraever range_pos < 20% eller > 80% (var: "trade with confidence")
  - Resultat: ETHUSD HOLD(4) trods ADX 29 — foer ville den have sagt BUY(7+)

- **Chat history strammet**
  - Vindue reduceret fra 24h til 4h (forhindrer moenster-forurening)
  - Max exchanges 50 -> 10, max tokens 80k -> 20k
  - Forhindrer at "jeg lover at pause" + "handler alligevel" moenster akkumulerer

- **Tidligere fixes (samme dag)**
  - Telegram HTML parse fix (commit 1baa163)
  - Danish-only prompts (commit 565a72b)
  - Chat context crash fix for None profit (commit 1228710)
  - Portfolio injection logging (commit 1228710)
