# CryptoBot

## Beskrivelse
Automatiseret crypto CFD trading-system paa Capital.com med tre bots:

- **Live Bot** (regelbaseret, rigtige penge): Teknisk analyse med scoring-system + trend-filter
- **AI Bot** (AI-drevet, demo): Claude Haiku analyserer markedsdata, modtager regel-bottens signal som kontekst
- **Demo Bot** (regelbaseret, demo): Identisk med Live Bot, til A/B test

## Status
**Aktiv** — koerer 24/7 paa Hetzner VPS (91.98.26.70) via Docker.

**Sidst opdateret:** 12-03-2026

**Coins (6 stk):** BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD

**KRITISK BUG:** P/L-vaerdier i dashboard stemmer IKKE overens med Capital.com. Se [Kendte Fejl](#kritisk-pl-data-integritetsproblem).

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
- 12 timers candle-historie med streak detection (konsekutive groenne/roede)
- 24h prisaendring og momentum-analyse
- Session-baseret bias (aften = favoriser SHORT, morgen = favoriser BUY)
- Modtager regel-bottens signal, sentiment, regime, og trade feedback
- Confidence boost ved bot-enighed (+2 ved fuld, +1 ved delvis)

**Hard filters i kode (efter AI response):**
- Counter-trend blocker ved lav confidence (<8) + staerkt modmomentum
- RSI ekstremfilter (>72 for BUY, <28 for SELL)
- 3+ consecutive losses paa samme coin → kraev confidence >= 8

### Python Hard Gates (`src/risk/hard_rules.py`)

UBRYDELIGE Python-gates der koerer FØR og EFTER AI-beslutninger. Kan IKKE overrides af Haiku.
Alle 3 trade paths (scan cycle, cycle trade, scale-in) bruger samme gates.

**Pre-AI gates (foer tokens bruges):**

| # | Gate | Default | Beskrivelse |
|---|------|---------|-------------|
| 1 | Handelstid | 08:00-22:00 CET | Ingen nye trades udenfor vindue |
| 2 | Circuit breaker | 3 tab → 20 min pause | Tvungen pause efter consecutive losses |
| 3 | Max positioner | 3 | Hard cap paa aabne positioner |
| 4 | Min interval | 15 min | Minimum tid mellem trades |
| 5 | ADX gate | >= 20 | Ingen trades i ranging/choppy marked |

**Post-AI gates (efter Haiku returnerer SL/TP):**

| # | Gate | Default | Beskrivelse |
|---|------|---------|-------------|
| 6 | R:R gate | >= 2.0:1 | Minimum risk/reward ratio |
| 7 | Max risiko | 1.5% af konto | Max tab per trade i EUR |

**Konfigurerbar via `config_ai.yaml`:**
```yaml
trading:
  min_adx: 20
  min_rr_ratio: 2.0
  max_hold_hours: 4
  max_positions: 3
  min_interval_minutes: 15
  trading_hours_start: 8
  trading_hours_end: 22
  circuit_breaker_losses: 3
  circuit_breaker_pause_minutes: 20
  max_risk_pct: 1.5
```

Circuit breaker state overlever restart (SQLite). Telegram notifikationer max 1 per gate-type per 30 min.

---

## Arkitektur

```
                Capital.com API
                /          |          \
           Live Bot     AI Bot      Demo Bot
          (main.py)  (main_ai.py)  (main.py)
              |          |              |
        config.yaml  config_ai.yaml  config_demo.yaml
              |          |              |
        Live-konto   Demo-konto 2   Demo-konto 1
              |          |              |
        Telegram 1   Telegram 2    Telegram 1
```

### A/B Test Setup

| Egenskab | Bot A (Regel) | Bot AI (Claude) |
|----------|---------------|-----------------|
| Entry-fil | `main.py` | `main_ai.py` |
| Config | `config.yaml` | `config_ai.yaml` |
| Beslutning | Score-system (min 4/9) | Claude Haiku (min 6/10) |
| Watchdog | 9 regler, 12 sek. | 9 regler, 12 sek. + scale-in |
| Docker | `cryptobot` container | `cryptobot-ai` container |

---

## Filstruktur

```
CryptoBot/
├── main.py                          # Live Bot: Regelbaseret trading bot
├── main_ai.py                       # AI Bot: AI-drevet med cycle trading + scale-in
├── dashboard.py                     # Dashboard entry point (Flask, port 5000)
├── config.example.yaml              # Eksempel-konfiguration
├── Dockerfile                       # Python 3.12 Docker image
├── docker-compose.yml               # Alle services (bots + dashboard)
├── requirements.txt                 # Python dependencies
├── scripts/
│   ├── import_capital_csv.py        # Import enkelt Capital.com CSV
│   ├── clean_reimport.py            # Clean reimport af alle 3 CSVs
│   └── sync_vps.py                  # Auto-sync til VPS (windowless)
├── src/
│   ├── api/
│   │   └── capital_client.py        # Capital.com REST API klient
│   ├── strategy/
│   │   ├── signals.py               # 6-mode signal engine
│   │   ├── ai_analyst.py            # Claude AI analyse + pattern recognition
│   │   ├── regime_detector.py       # ADX(14) regime detection
│   │   ├── time_bias.py             # Time-of-day bias (7-dages historik)
│   │   └── reddit_sentiment.py      # CryptoPanic + CoinGecko + Fear & Greed
│   ├── risk/
│   │   ├── manager.py               # ATR SL/TP, R:R enforcement, confidence sizing
│   │   └── hard_rules.py            # 7 Python hard gates (ADX, R:R, hours, circuit breaker)
│   ├── executor/
│   │   ├── trade_executor.py        # Handelsudfoersel, SQLite, reconcile
│   │   └── position_watchdog.py     # 9-regel positionsovervagning (12 sek.)
│   ├── dashboard/
│   │   ├── app.py                   # Flask app factory (3 DB paths)
│   │   ├── routes.py                # HTML pages + JSON API
│   │   ├── stats_engine.py          # Statistik fra SQLite (pandas)
│   │   ├── templates/               # Jinja2 templates (dark theme)
│   │   └── static/                  # CSS + Chart.js helpers
│   ├── notifications/
│   │   └── telegram_bot.py          # Telegram notifikationer og kommandoer
│   └── analysis/
│       └── reporter.py              # Data-analyse og rapportering
├── data/                            # Live Bot SQLite DB
├── data_ai/                         # AI Bot SQLite DB
└── data_demo/                       # Demo Bot SQLite DB
```

---

## Risikostyring (`src/risk/manager.py`)

### ATR-baseret Stop Loss / Take Profit
- **SL**: `entry * (1 ∓ atr_pct * 2.0)`, clamped [3%, 8%]
- **TP**: `entry * (1 ± atr_pct * 3.0)`, clamped [3%, 10%]
- **R:R enforcement**: TP >= SL_distance × 2.0 (minimum 2.0:1, konfigurerbar via `trading.min_rr_ratio`)

### Confidence-baseret Position Sizing

| Confidence | Multiplier | Beskrivelse |
|------------|-----------|-------------|
| 1-3 | 20% | Svagt signal |
| 4-5 | 25-30% | Moderat signal |
| 6 | 50% | Decent setup |
| 7 | 70% | Staerk setup |
| 8 | 85% | Meget staerk |
| 9-10 | 100% | Exceptionel |

### Kapitalallokering

| Kategori | Coins | Max pr. coin | Max total |
|----------|-------|-------------|-----------|
| Majors | BTC, ETH | 40% | — |
| Altcoins | SOL, AVAX, LINK, LTC | 30% | — |
| Total | — | — | 95% |
| Min position | — | 5% | — |

### Kill Switch
- Dagligt tab > 5% → luk alt, stop handel
- Totalt tab > 30% → permanent stop

---

## Position Watchdog (`src/executor/position_watchdog.py`)

Baggrundstraad der tjekker positioner hver 12 sekund:

| # | Regel | Beskrivelse |
|---|-------|-------------|
| 1 | Max holdtid | Global cap: 4h (default). Kun tabere/breakeven lukkes, vindere koerer |
| 2 | Early exit | 3+ accelererende adverse candles → luk 50-100% |
| 3 | Break-even | Flyt SL til entry ved +1.5% |
| 3b | Progressive SL | Trail 1.0% bag pris, server-side, min 0.3% step |
| 3c | Profit pullback | Peak >= 1.5% + drop 0.75% fra peak → LUK |
| 4 | Delvis profit | 50% ved +4% |
| 5 | Dynamisk TP | Near TP + momentum → extend 1.5×ATR (max 2x) |
| 6 | Trailing stop | +2.5% profit, luk ved 1.5×ATR drawdown |
| 7 | Sentiment close | Bearish time-bias + profitable long → luk |
| 8 | Cycle trading | Re-analyse for reversal efter close, 30min cooldown |

---

## Trade Tracking

- `execute_trade()` henter rigtig dealId via `/api/v1/confirms/{dealRef}`
- `reconcile_closed_trades()` bruger transaktionshistorik + epic+timestamp matching
- Watchdog close methods sender `epic=epic` til DB for fallback matching
- Reconcile Step 2 re-checker trades lukket inden for 48h og overskriver estimeret P/L med faktisk
- **Dashboard timestamps**: UTC fra VPS, konverteret til dansk tid (CET/CEST) i browser

---

## Dashboard

Flask + Jinja2 + Chart.js dark theme dashboard paa port 5000.

- **3 bot-profiler**: Live Bot, AI Bot, Demo Bot (selector i navbar)
- **Sider**: Oversigt, Rapporter (Transaktioner/Trades), Statistik, Coins, Kalender, Sammenlign
- **Sammenlign**: Periodefiltre (Dag/Uge/Maaned/Aar/Total), procentbaseret ROI, 6 grafer, 3 bot-kort
- **Tidszone**: Dansk tid (CET/CEST) — VPS gemmer UTC, browser konverterer

---

## Regime Detection (`src/strategy/regime_detector.py`)

| ADX | Regime | Strategi |
|-----|--------|----------|
| > 25 | TRENDING_UP / TRENDING_DOWN | Trade med trenden |
| < 20 | RANGING | Mean-reversion |
| 20-25 | NEUTRAL | Kun staerke signaler |

---

## Telegram Kommandoer

**Begge bots:** `/status` `/trades` `/scan` `/close EPIC|ALL` `/stop` `/help`

**Kun Bot A:** `/buy EPIC SIZE` `/sell EPIC SIZE` `/sentiment`

**Kun Bot AI:** `/report EPIC` `/debug`

---

## Konfiguration

Config-filer er i `.gitignore`. Se `config.example.yaml` for format.

**Aktuel konfiguration (paa server):**
```yaml
trading:
  coins: [BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD]
  leverage: 2
  timeframe: "HOUR"
  scan_interval: 300

risk:
  max_open_positions: 6
  allocation:
    max_total_exposure: 95
    max_major: 40
    max_altcoin: 30
    min_position: 5
```

---

## Deployment

### Hetzner VPS
```bash
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot && git pull origin master
docker compose down && docker compose up -d --build
docker compose logs --tail=30 cryptobot
docker compose logs --tail=30 cryptobot-ai
```

### Docker Compose Services
- `cryptobot`: Live Bot (config.yaml, data/, logs/)
- `cryptobot-ai`: AI Bot (config_ai.yaml, data_ai/, logs_ai/)
- `cryptobot-demo`: Demo Bot (config_demo.yaml, data_demo/, logs_demo/)
- `cryptobot-dashboard`: Flask dashboard (port 5000)

---

## API Gotchas
- **`update_position()` SKAL sende baade SL og TP** — ellers cleares den manglende
- **`dealReference` ≠ `dealId`** — brug `/api/v1/confirms/{dealRef}` for rigtig dealId
- **Transaction history `size` felt = P/L i EUR** for 'Trade closed' entries
- **CryptoPanic rate-limits aggressivt** — 429 errors ved samtidige kald fra begge bots

---

## Tech Stack
- **Python 3.12** + pandas
- **Capital.com REST API** (live + demo)
- **Claude Haiku 4.5** (Anthropic SDK) for AI-analyse
- **SQLite** for handelslog
- **Flask** + Jinja2 + Chart.js for dashboard
- **Telegram Bot API** for notifikationer
- **Docker Compose** paa Hetzner VPS

---

## Changelog

### 12-03-2026 (v2): Ubrydelige Python hard gates — fix EUR 576 BTC tab

**Problem:** AI-botten (Haiku) tabte EUR 576 paa BTC ved at handle i ranging marked, selvom den "lovede" at pause. AI kan ikke kontrollere sig selv.

**Root cause:** `_handle_scale_in()` havde NULGATEZ — ingen ADX, R:R, handelstid, circuit breaker eller max positions check. Scale-in trades var helt ubeskyttede. BTC max hold var 24 timer (som "major") i stedet for 4.

**Fix — 3 filer aendret:**

| Fil | Aendring |
|-----|---------|
| `src/risk/hard_rules.py` | Alle 7 gates centraliseret. Config-laesning. Spam guard. Startup log. Nye standalone metoder: `check_adx_gate()`, `check_rr_gate()`, `is_trading_hours()`, `is_circuit_breaker_active()`, `pre_trade_gates()` |
| `main_ai.py` | Alle 3 trade paths (scan, cycle, scale-in) bruger nu SAMME gates. Trading hours + circuit breaker check FØR coin-loop. Scale-in har nu alle 7 gates. |
| `src/risk/manager.py` | Global `max_hold_hours` cap (default 4h) overskriver per-kategori (BTC 24h → 4h) |

**Gate execution flow:**
```
FØR AI-kald:  Handelstid → Circuit breaker → Max pos → Min interval → ADX >= 20
EFTER AI-svar: R:R >= 2.0 → Risk EUR <= 1.5%
```

### 12-03-2026: P/L reconcile fix + Compare page redesign

**KRITISK P/L fix (delvis):**
- Reconcile overskriver nu watchdog-estimeret P/L med faktisk Capital.com P/L (48h vindue)
- Opdagede dybereliggende dataproblem: duplikerede trades i DB (se Kendte Fejl)

**Compare page redesign:**
- Periodefiltre: Dag, Uge, Maaned, Aar, Total
- Procentbaseret ROI (fair sammenligning paa tvaers af konti med forskellige balancer)
- 6 grafer: Kumulativ ROI%, Win Rate, Daglig P&L, Profit Factor, Coin ROI%, BUY/SELL
- 3 bot-kort bevaret med alle stats
- Ny `/api/compare?period=` endpoint med `get_period_comparison()`

**Stats engine:**
- Fikset ISO8601 timestamp parsing (mikrosekunder fra VPS)
- Periodefiltreret statistik med start-balance lookup

### 11-03-2026: Aggressiv trading + pattern recognition + timezone fix

**6 signal modes (ny):**
- Mode 5: Momentum continuation — ROC-6 > 1% + EMA aligned → trade i neutral zone
- Mode 6: Session trading — proaktiv SHORT i bearish timer, BUY i bullish timer
- Trend-following zones bredere: BUY 20-75%, SELL 20-80%
- Alle modes: min score 4 (trend saenket fra 5)

**AI pattern recognition:**
- 12h candle-historie (var 6 candles), streak detection, 24h prisaendring
- Aggressivt prompt: deploy kapital, find patterns, SHORT aktivt
- Hard filters lempet: counter-trend kun ved lav confidence, RSI 72/28, 3+ losses

**Kapitaludnyttelse:**
- Confidence multipliers haevet: conf 6=50%, 7=70%, 8=85%
- Allokering: max_major=40%, max_altcoin=30%, max_total=95%

**Dashboard timezone:**
- Fikset: viser nu dansk tid (CET/CEST) i stedet for UTC

### 11-03-2026: Trade tracking + AI filters + coin selection

- dealId hentes via confirms endpoint (dealReference ≠ dealId)
- reconcile bruger transaktionshistorik + epic+timestamp matching
- Reduceret fra 10 til 6 coins, banned: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD

### 11-03-2026: R:R fix + Dashboard + AI feedback loop

- ATR TP: 1.5x → 3.0x, clamp [3%, 10%], R:R enforcement min 1.5:1
- Trading Dashboard med 3 bot-profiler
- AI feedback loop med cross-bot laering

### 09-03-2026: Evidensbaseret strategiskift

- Timeframe 15min → 1H, trend-following primaer
- ADX regime detection, time-of-day bias
- Profit pullback close, progressive SL, sentiment close, cycle trading

---

## KRITISK: P/L Data-Integritetsproblem

**Status:** ULOEST — Dashboard P/L-vaerdier stemmer IKKE overens med Capital.com.

### Symptomer
- Dashboard viser forkerte P/L-vaerdier for mange trades
- Total P/L i dashboard ≠ Capital.com performance
- Eksempler (Live Bot, 11-03-2026):
  - BTCUSD 21:15: Capital.com +EUR 1.69, Dashboard +1.98 (afvigelse +0.29)
  - SOLUSD 18:03: Capital.com +EUR 5.32, Dashboard +6.25 (afvigelse +0.93)
  - ETHUSD 15:00: Capital.com +EUR 0.92, Dashboard +1.09 (afvigelse +0.17)

### Grundaarsager (3 separate problemer)

**Problem 1: Duplikerede trades i databasen**
- CSV-import (`clean_reimport.py`) OG bot-tracking opretter BEGGE trades for samme handel
- Samme Capital.com transaktion matcher til 2+ DB-rækker
- Eksempel: SOLUSD id=109 (CSV, size=0.89, pl=5.32) + id=130 (bot, size=3.75, pl=6.25)
- Resultat: P/L taelles dobbelt, trade-antal er oppustet

**Problem 2: Watchdog estimerer P/L uden spread/fees**
- Watchdog beregner: `pl_pct / 100 * entry_price * size`
- Inkluderer IKKE: spread-cost, overnight funding, Capital.com fees
- Estimat er altid for hoejt (0.1-1.0 EUR pr. trade)
- Reconcile overskriver nu estimater (fix deployet 12-03-2026), men virker kun for trades < 48h

**Problem 3: Reconcile matcher forkerte transaktioner**
- `_match_close()` matcher paa epic + tidsstempel (foerste ledige efter entry)
- Med duplikerede trades matches samme Capital.com transaktion til forkert DB-raekke
- CSV-importerede trades har forkerte directions/sizes (size=0.0, entry=0.0)

### Foreslaaede Loesninger

**Loesning A: Nulstil databaser + stop CSV import (anbefalet)**
1. Stop alle bots
2. Slet trades-tabellen i alle 3 databaser (behold balance_snapshots)
3. Importer KUN fra Capital.com transaction history API (ikke CSV)
4. Tilfoej `source` kolonne til trades-tabellen (`bot`, `reconcile`, `csv`)
5. Fjern `clean_reimport.py` fra workflow — brug kun API-data
6. Genstart bots — fremtidige trades trackes korrekt fra bot + reconcile

**Loesning B: Dedupliker eksisterende data**
1. Identificer duplikerede trades (samme epic + exit_timestamp ± 1 sekund)
2. Behold kun den med hoejeste id (nyeste = bot-skabt)
3. Kør reconcile for at overskrive estimeret P/L med faktisk
4. Validér total P/L mod Capital.com performance

**Loesning C: Ny reconcile med dealId-matching (mest robust)**
1. Tilfoej `capital_deal_id` kolonne til trades (fra confirms endpoint)
2. Reconcile matcher paa dealId i stedet for epic+timestamp
3. Forhindrer duplikater: hvis dealId allerede eksisterer, opdatér i stedet for insert
4. Backfill alle eksisterende trades via transaction history

**Loesning D: Hybrid (hurtigst at implementere)**
1. Kør SQL deduplikering: slet CSV-importerede trades (size=0, entry_price=0)
2. Kør reconcile for alle resterende trades (udvid 48h vindue til "all")
3. Validér mod Capital.com
4. Tilfoej guard i reconcile: spring trades over der allerede har korrekt dealId-match

### Prioritet
Loesning A er renest og forhindrer fremtidige problemer. Loesning D er hurtigst.

---

## Kendte Begraensninger
- **P/L data-integritet** — Se ovenfor. Dashboard matcher IKKE Capital.com
- **Ingen backtesting** — Vigtigste manglende funktion
- **CFD spread-cost** — 0.1-0.5% per trade, ikke tracket
- **Overnight funding** — Ikke tracket i bot DB (kun i Capital.com)
- **Crypto korrelation** — Alle coins er hoejt korrelerede (0.7-0.9)
- **CryptoPanic rate-limiting** — Begge bots rammer 429 errors
- **Ingen WebSocket** — REST polling, watchdog hvert 12 sek
