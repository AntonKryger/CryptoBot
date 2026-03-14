# CryptoBot

## Beskrivelse
Automatiseret crypto trading-system med multi-exchange support:

- **RuleBot** (regelbaseret): Teknisk analyse med 6-mode scoring-system + trend-filter
- **AIBot** (AI-drevet): Claude Haiku analyserer markedsdata, modtager regel-bottens signal som kontekst
- **ScalpingBot** (scalper): Hurtig trading med range-analyse
- **AI Coach** (analyse-service): Laeser alle bots' data, koerer Sonnet/Opus, giver specifikke optimeringsanbefalinger via Telegram

## Status
**Aktiv** — koerer 24/7 paa Hetzner VPS (91.98.26.70) via Docker.

**Sidst opdateret:** 14-03-2026

### Aktive Bots

| Bot | Exchange | Mode | Coins | Profil | Beskrivelse |
|-----|----------|------|-------|--------|-------------|
| RL1 | Capital.com | Live | BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD | moderate | Regelbaseret, rigtige penge |
| RD1 | Capital.com | Demo | Samme 6 coins | moderate | Regelbaseret, demo |
| AD1 | Capital.com | Demo | Samme 6 coins | moderate | AI-drevet med cycle trading |
| SD1 | **Kraken** | Live (spot) | BTC/USD, ETH/USD | conservative | Major pair scalper |
| SD2 | **Kraken** | Live (spot) | SOL/USD, AVAX/USD, LINK/USD, LTC/USD | moderate | Altcoin scalper |

### Exchanges

| Exchange | Type | Fordele | Bots |
|----------|------|---------|------|
| Capital.com | CFD broker | Demo-konti, ingen rigtige crypto assets | RL1, RD1, AD1 |
| Kraken | Rigtig exchange | Lav spread ($0.10 BTC vs $30+ CFD), orderbook, limit orders, 24/7 | SD1, SD2 |

**KRITISK BUG:** P/L-vaerdier i Capital.com dashboard stemmer IKKE overens med Capital.com. Se [Kendte Fejl](#kritisk-pl-data-integritetsproblem).

---

## Arkitektur — Hybrid Shared Code

Hver bot-type deler ÉN `src/` codebase. Varianter inden for en type deler kode men har separate configs.

```
RuleBot/
  src/                    ← delt af ALLE RuleBot-varianter
    exchange/             ← Exchange adapter layer
      base_adapter.py     ← Abstract interface
      capital_adapter.py  ← Capital.com CFD (requests)
      kraken_adapter.py   ← Kraken spot/futures (ccxt)
      binance_adapter.py  ← Stub (fremtid)
      factory.py          ← get_adapter(config)
    strategy/             ← Signal engine, AI analyst, regime, sentiment
    risk/                 ← Manager (ATR SL/TP), hard_rules (7 gates)
    executor/             ← Trade executor, position watchdog
    coach/                ← Analyzer, LLM advisor, leaderboard
    dashboard/            ← Flask + Jinja2 + Chart.js
    notifications/        ← Telegram bot
  main.py                 ← Entry point
  Dockerfile              ← Builds one image per type
  requirements.txt        ← Python dependencies (incl. ccxt)
  config.example.yaml     ← Template
  Live/RL1/config.yaml    ← Variant-specifik (+ data/, logs/)
  Demo/RD1/config.yaml

ScalpingBot/              ← Samme moenster
AIBot/                    ← Samme moenster (main_ai.py)
AICoach/                  ← Coaches (main_coach.py)
  AC1/                    ← AI Coach (coaches AI bots)
  RuleCoach/RC1/          ← Rule Coach (coaches rule bots)
  ScalpCoach/SC1/         ← Scalp Coach (coaches scalper bots)
  MasterCoach/MC1/        ← Meta-coach (sammenligner bedste fra hver type)
```

### Exchange Adapter Layer
Bots kalder ALDRIG exchange APIs direkte. Al kommunikation gaar via `src/exchange/`:

```python
from src.exchange import get_adapter
adapter = get_adapter(config)  # Returnerer Capital/Kraken/Binance adapter
adapter.start_session()
adapter.get_prices("BTC/USD", "HOUR", 200)
adapter.create_position("BTC/USD", "BUY", 0.001, stop_loss=69000, take_profit=72000)
```

**Kraken adapter** bruger `ccxt` biblioteket (unified API for 100+ exchanges):
- Symbol mapping: `BTCUSD` ↔ `BTC/USD` (automatisk konvertering begge veje)
- Pris-data returneres i Capital.com-kompatibelt format (ingen kodeaendringer nødvendige)
- SL/TP via separate conditional orders (Kraken har ikke native SL/TP paa positioner)
- Spot mode: `ccxt.kraken` | Futures mode: `ccxt.krakenfutures` (med sandbox)

### Variant System
- `variants.yaml` — central registrering af alle bot-varianter (profiler, coins, overrides)
- `scripts/generate_variant.py` — genererer config.yaml + docker-compose.generated.yml
- 7 risikoprofiler: ultra_conservative → ultra_aggressive

---

## Strategi — 6 Signal Modes

### Signal Engine (`src/strategy/signals.py`)

| Mode | Trigger | Beskrivelse |
|------|---------|-------------|
| 1. Mean-reversion BUY | range_pos <= 20% | Koeb ved bund af 24h range, bounce + oversold |
| 2. Mean-reversion SELL | range_pos >= 80% | Short ved top af range, rejection + overbought |
| 3. Trend-following BUY | TRENDING_UP + range 20-75% | Koeb paa pullback i optrend |
| 4. Trend-following SELL | TRENDING_DOWN + range 20-80% | Short paa rally i nedtrend |
| 5. Momentum continuation | ROC-6 > 1% + EMA aligned | Trade staerkt momentum i neutral zone (25-75%) |
| 6. Session trading | Bearish/bullish time-of-day bias | Proaktivt SHORT i historisk bearish timer |

Alle modes kraever minimum score 4 for at trigge.

### Scoring-faktorer
- Range position, RSI, Bollinger Bands, bounce/rejection detection
- EMA 9/21 trend alignment (+1 med trend, -2 mod trend)
- MACD divergence (+2), volume climax (+2), failed breakout (+3)
- Sentiment adjustment, regime adjustment, time-of-day bias (±2)

### AI Analyst (`src/strategy/ai_analyst.py`)
Claude Haiku analyserer markedsdata med **pattern recognition fokus**:
- 12 timers candle-historie med streak detection
- 24h prisaendring og momentum-analyse
- Session-baseret bias (aften = favoriser SHORT, morgen = favoriser BUY)
- Modtager regel-bottens signal, sentiment, regime, og trade feedback

### Python Hard Gates (`src/risk/hard_rules.py`)

UBRYDELIGE Python-gates der koerer FØR og EFTER AI-beslutninger.
Alle 3 trade paths (scan cycle, cycle trade, scale-in) bruger samme gates.

**Pre-AI:** Handelstid → Circuit breaker → Max positioner → Min interval → ADX >= 20

**Post-AI:** R:R >= 2.0:1 → Risiko <= 1.5% af konto

---

## Risikostyring (`src/risk/manager.py`)

### ATR-baseret Stop Loss / Take Profit
- **SL**: `entry * (1 ∓ atr_pct * 2.0)`, clamped [3%, 8%]
- **TP**: `entry * (1 ± atr_pct * 3.0)`, clamped [3%, 10%]
- **R:R enforcement**: TP >= SL_distance × 2.0 (minimum 2.0:1)

### Kapitalallokering

| Kategori | Coins | Max pr. coin | Max total |
|----------|-------|-------------|-----------|
| Majors | BTC, ETH | 40% | — |
| Altcoins | SOL, AVAX, LINK, LTC | 30% | — |
| Total | — | — | 95% |
| Min position | — | 5% | — |

---

## Position Watchdog (`src/executor/position_watchdog.py`)

Baggrundstraad der tjekker positioner hver 12 sekund.

**Opdaterede default-vaerdier (2026-03-14)** — tunet for at lade winners koere laengere:

| # | Regel | Beskrivelse | Default |
|---|-------|-------------|---------|
| 1 | Max holdtid | Lukker kun tabere/breakeven, vindere koerer | 4h |
| 2 | Early exit | 3+ accelererende adverse candles → luk 50-100% | — |
| 3 | Break-even | Flyt SL til entry | **+2.5%** (var 1.5%) |
| 3b | Progressive SL | Trail bag pris, server-side | **+3.0%** (var 2.0%) |
| 3c | Profit pullback | Peak profit + drop fra peak → LUK | **peak >= 4.0%** (var 2.5%), **min P/L >= 1.5%** (NY) |
| 4 | Delvis profit | Luk del af position | **30% ved +6.0%** (var 50% ved +4.0%) |
| 5 | Dynamisk TP | Near TP + momentum → extend 1.5×ATR (max 2x) | — |
| 6 | Trailing stop | Profit → luk ved ATR drawdown | +2.5% |
| 7 | Sentiment close | Bearish time-bias + profitable long → luk | — |
| 8 | Cycle trading | Re-analyse for reversal efter close | 30min cooldown |

**Ny regel: Minimum profit floor** — Pullback close sker KUN hvis nuværende P/L >= 1.5%. Forhindrer at watchdog lukker positioner der har givet al profit tilbage.

---

## Konfiguration

Config-filer er i `.gitignore`. Se `config.example.yaml` for format.

### Capital.com config:
```yaml
exchange:
  provider: capital
  email: "..."
  password: "..."
  api_key: "..."
  demo: true
  account_name: "RD1"
```

### Kraken config:
```yaml
exchange:
  provider: kraken
  api_key: "..."
  api_secret: "..."
  mode: spot          # spot eller futures
  demo: false         # futures har demo; spot har ikke
```

---

## Deployment

### Hetzner VPS
```bash
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot && git pull origin master
docker compose down && docker compose up -d --build
docker compose logs --tail=30 cryptobot-rl1
docker compose logs --tail=30 cryptobot-sd1
```

### Docker Compose Services
- `rl1`: RuleBot Live (Capital.com)
- `rd1`: RuleBot Demo (Capital.com)
- `ad1`: AIBot Demo (Capital.com)
- `sd1`: ScalpingBot Live (Kraken, BTC/ETH)
- `sd2`: ScalpingBot Live (Kraken, altcoins)
- `coach`: AI Coach
- `dashboard`: Flask dashboard (port 5000)

### Preflight Check
```bash
python preflight_check.py
```
Verificerer at ingen bots deler credentials + sub-account. Laeser fra `variants.yaml`.

---

## Telegram Kommandoer

**Alle trading bots:** `/status` `/trades` `/scan` `/close EPIC|ALL` `/stop` `/help`

**Kun RuleBot:** `/buy EPIC SIZE` `/sell EPIC SIZE` `/sentiment`

**Kun AIBot:** `/report EPIC` `/debug`

**AI Coach:** `/coach_status` `/coach_analyze` `/coach_recs` `/coach_approve {id}` `/coach_reject {id}` `/coach_bot {id}`

---

## AI Coach (`main_coach.py`)

Separat Docker-service der laeser ALLE bots' trade-data i read-only mode og giver datadrevne optimeringsanbefalinger via Telegram.

### Scheduling
- **Daglig rapport**: 23:30 CET
- **Ugentlig deep analysis**: Soendag 09:00 CET
- **On-demand**: `/coach_analyze` i Telegram

### Dedikerede coaches
- **AC1** — coaches AI bots
- **RC1** — coaches RuleBots
- **SC1** — coaches ScalpBots
- **MC1** — meta-coach (sammenligner bedste fra hver type)

---

## Tech Stack
- **Python 3.12** + pandas + ccxt
- **Capital.com REST API** (CFD, live + demo)
- **Kraken API via ccxt** (spot + futures)
- **Claude Haiku 4.5** for AI-analyse i trading bots
- **Claude Sonnet/Opus** for AI Coach analyse
- **SQLite** for handelslog
- **Flask** + Jinja2 + Chart.js for dashboard
- **Telegram Bot API** for notifikationer
- **Docker Compose** paa Hetzner VPS

---

## API Gotchas

### Capital.com
- `update_position()` SKAL sende baade SL og TP — ellers cleares den manglende
- `dealReference` ≠ `dealId` — brug `/api/v1/confirms/{dealRef}` for rigtig dealId
- Transaction history `size` felt = P/L i EUR for 'Trade closed' entries
- CryptoPanic rate-limits aggressivt — 429 errors ved samtidige kald

### Kraken
- Crypto markeder er 24/7 — ingen market hours check
- Spot har ingen demo mode — brug futures sandbox til test
- SL/TP er separate conditional orders, ikke attached til positioner
- Spread markant lavere end Capital.com ($0.10 BTC vs $30+ CFD)
- API key permissions: Query funds + Query orders + Create/modify orders + Cancel orders + Query ledger

---

## Changelog

### 14-03-2026: Kraken Exchange Integration + Watchdog Tuning

**Ny exchange:** Kraken spot trading via ccxt — SD1 og SD2 migreret fra Capital.com til Kraken.

| Aendring | Detaljer |
|----------|---------|
| `kraken_adapter.py` | Fuld implementation med ccxt: alle 17 adapter-metoder, symbol mapping, spot+futures support |
| `factory.py` | Opdateret til at logge Kraken mode (spot/futures) |
| `requirements.txt` | Tilfojet `ccxt>=4.0.0` til alle 4 bot-typer |
| `config.example.yaml` | Tilfojet Kraken config eksempel til alle 4 bot-typer |
| `position_watchdog.py` | Tunet defaults: breakeven 2.5%, pullback 4.0%, partial 6.0%@30%, ny min profit floor 1.5% |
| `variants.yaml` | SD1 → Kraken Major Pair (konservativ), SD2 → Kraken Altcoin (moderat) |

**SD1/SD2 differentiering:**
- SD1: BTC/USD + ETH/USD, konservativ profil, max 2 positioner
- SD2: SOL/USD + AVAX/USD + LINK/USD + LTC/USD, moderat profil, max 3 positioner

### 13-03-2026: AI Coach + Telegram bots

AI Coach service med dedikerede coaches per bot-type, leaderboard, og Telegram integration.

### 12-03-2026: Hard gates fix + P/L reconcile

Fixed scale-in bypassing ALL gates (EUR 576 BTC tab). R:R ratio mismatch (1.5→2.0).

### 11-03-2026: 6 signal modes + pattern recognition + dashboard

Aggressiv trading strategi, 6 signal modes, AI pattern recognition, timezone fix.

---

## KRITISK: P/L Data-Integritetsproblem

**Status:** ULOEST — Dashboard P/L-vaerdier stemmer IKKE overens med Capital.com.

### Grundaarsager (3 separate problemer)

1. **Duplikerede trades**: CSV-import + bot-tracking opretter BEGGE trades for samme handel
2. **Estimeret P/L**: Watchdog beregner P/L uden spread/fees (altid for hoejt)
3. **Reconcile matcher forkert**: Samme Capital.com transaktion matched til forkert DB-raekke

### Foreslaaede Loesninger

**A) Nulstil databaser + stop CSV import (anbefalet)**
**B) Dedupliker eksisterende data**
**C) Ny reconcile med dealId-matching (mest robust)**
**D) Hybrid (hurtigst)**

**DO NOT run `clean_reimport.py`** — det skaber duplikater.

---

## Kendte Begraensninger
- **P/L data-integritet** — Dashboard matcher IKKE Capital.com (kun Capital.com bots)
- **Ingen backtesting** — Vigtigste manglende funktion
- **CFD spread-cost** — Ikke tracket (Capital.com)
- **Crypto korrelation** — Alle coins er hoejt korrelerede (0.7-0.9)
