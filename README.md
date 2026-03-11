# CryptoBot

## Beskrivelse
Automatiseret crypto CFD trading-system paa Capital.com med tre bots:

- **Live Bot** (regelbaseret, rigtige penge): Teknisk analyse med scoring-system + trend-filter
- **AI Bot** (AI-drevet, demo): Claude Haiku analyserer markedsdata, modtager regel-bottens signal som kontekst
- **Demo Bot** (regelbaseret, demo): Identisk med Live Bot, til A/B test

## Status
**Aktiv** — koerer 24/7 paa Hetzner VPS (91.98.26.70) via Docker.

**Sidst opdateret:** 11-03-2026

**Coins (6 stk):** BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD

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
│   │   └── manager.py               # ATR SL/TP, R:R enforcement, confidence sizing
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
- **R:R enforcement**: TP >= SL_distance × 1.5 (minimum 1.5:1)

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
| 1 | Max holdtid | Major: 24h, altcoin: 8h, memecoin: 4h. Kun tabere lukkes |
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
- **Dashboard timestamps**: UTC fra VPS, konverteret til dansk tid (CET/CEST) i browser

---

## Dashboard

Flask + Jinja2 + Chart.js dark theme dashboard paa port 5000.

- **3 bot-profiler**: Live Bot, AI Bot, Demo Bot (selector i navbar)
- **Sider**: Oversigt, Rapporter (Transaktioner/Trades), Statistik, Coins, Kalender, Sammenlign
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

### 11-03-2026: Aggressiv trading + pattern recognition + timezone fix

**6 signal modes (ny):**
- Mode 5: Momentum continuation — ROC-6 > 1% + EMA aligned → trade i neutral zone
- Mode 6: Session trading — proaktiv SHORT i bearish timer, BUY i bullish timer
- Trend-following zones bredere: BUY 20-75%, SELL 20-80%
- Alle modes: min score 4 (trend sænket fra 5)

**AI pattern recognition:**
- 12h candle-historie (var 6 candles), streak detection, 24h prisaendring
- Aggressivt prompt: deploy kapital, find patterns, SHORT aktivt
- Hard filters lempet: counter-trend kun ved lav confidence, RSI 72/28, 3+ losses

**Kapitaludnyttelse:**
- Confidence multipliers haevet: conf 6=50%, 7=70%, 8=85%
- Allokering: max_major=40%, max_altcoin=30%, max_total=95%
- Foerste scan efter deploy: 4 trades, 95% kapitaludnyttelse

**Dashboard timezone:**
- Fikset: viser nu dansk tid (CET/CEST) i stedet for UTC

### 11-03-2026: Trade tracking + AI filters + coin selection

**Trade P/L tracking:**
- dealId hentes via confirms endpoint (dealReference ≠ dealId)
- reconcile bruger transaktionshistorik + epic+timestamp matching
- Watchdog close methods sender epic til DB for fallback

**AI hard filters:**
- Counter-trend blocker, RSI overextension, recent loss penalty
- Time-of-day BUY blocker i bearish timer (begge bots)

**Coin selection:**
- Reduceret fra 10 til 6 coins (BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD)
- Banned: DOGEUSD, XRPUSD, ADAUSD, DOTUSD, MATICUSD

### 11-03-2026: R:R fix + Dashboard + AI feedback loop

- ATR TP: 1.5x → 3.0x, clamp [3%, 10%], R:R enforcement min 1.5:1
- Trading Dashboard med 3 bot-profiler
- AI feedback loop med cross-bot laering

### 09-03-2026: Grid trading + profit-beskyttelse

- Profit pullback close, progressive SL, sentiment close
- ATR-baseret TP, cycle trading for begge bots
- Watchdog R:R fix ved opstart

### 09-03-2026: Evidensbaseret strategiskift

- Timeframe 15min → 1H, trend-following primaer
- ADX regime detection, time-of-day bias
- AI feedback loop, scan interval 300s

---

## Kendte Begraensninger
- **Ingen backtesting** — Vigtigste manglende funktion
- **CFD spread-cost** — 0.1-0.5% per trade
- **Crypto korrelation** — Alle coins er hoejt korrelerede (0.7-0.9)
- **CryptoPanic rate-limiting** — Begge bots rammer 429 errors
- **Ingen WebSocket** — REST polling, watchdog hvert 12 sek
