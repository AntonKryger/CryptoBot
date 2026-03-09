# CryptoBot

## Beskrivelse
Automatiseret crypto CFD trading-system paa Capital.com. To uafhaengige bots koerer parallelt paa hver sin demo-konto som A/B test:

- **Bot A** (regelbaseret): Teknisk analyse med scoring-system + trend-filter
- **Bot AI** (AI-drevet): Claude Haiku analyserer markedsdata, modtager Bot A's signal som kontekst

Begge bots bruger **trend-following som primaer strategi** (staerkest dokumenteret edge i crypto, Sharpe ~1.51 out-of-sample). Mean-reversion er sekundaer og kun aktiv i confirmed ranging markeder (ADX < 20).

## Status
**Aktiv** — koerer 24/7 paa Hetzner VPS (91.98.26.70) via Docker.

**Sidst opdateret:** 09-03-2026

---

## Strategi — Evidensbaseret

### Hvorfor trend-following?
Akademisk forskning viser at simpel trend-following er den bedst dokumenterede strategi i crypto:
- 28-dages momentum med 5-dages holding: **Sharpe 1.51** vs 0.84 for buy-and-hold (SSRN, out-of-sample)
- Grayscale Research: 50-dages SMA giver hoejere afkast OG lavere volatilitet end buy-and-hold
- Mean-reversion paa 15-min timeframes har **ingen akademisk stoette** — kun daglige+ timeframes

### Hvad botten goer
1. **1-times candles** (reducerer noise vs. 15-min, faerre handler, lavere spread-cost)
2. **Trend-filter**: +1 score for trades der foelger EMA 9/21 trenden, -2 penalty for counter-trend
3. **Mean-reversion kun i ranging regime** (ADX < 20): Buy near support, sell near resistance
4. **Regime detection** (ADX 14): TRENDING_UP, TRENDING_DOWN, RANGING, NEUTRAL
5. **Time-of-day bias**: Analyserer historiske timereturns over 7 dage
6. **Scan hvert 5. minut** (300s interval, matcher 1H timeframe)

### Hvad vi har fravalgt (og hvorfor)
- **StochRSI, VWAP Z-score, Keltner Channels** — Nul akademisk evidens paa crypto intraday
- **Korrelationsfilter** — Crypto korrelation er 0.7-0.9 og STIGER under crashes (falsk tryghed)
- **Flere indikatorer** — Jo flere parametre, jo stoerre risiko for overfitting
- **ML/LSTM modeller** — Forskning viser simple modeller ofte outperformer komplekse paa crypto

---

## Arkitektur

```
                Capital.com API (demo)
                /                    \
           Bot A                    Bot AI
        (main.py)               (main_ai.py)
            |                        |
      config.yaml             config_ai.yaml
            |                        |
     Demo-konto 1             Demo-konto 2
    "Crypto bot"             "CryptoBot AI"
            |                        |
     Telegram Bot 1           Telegram Bot 2
 @claude_cryptobot_bot   @cryptobot_ai_anton_bot
```

### A/B Test Setup

| Egenskab | Bot A (Regel) | Bot AI (Claude) |
|----------|---------------|-----------------|
| Entry-fil | `main.py` | `main_ai.py` |
| Config | `config.yaml` | `config_ai.yaml` |
| Beslutning | Score-system (min 4/9) | Claude Haiku (min 6/10) |
| Konto | "Crypto bot" (default) | "CryptoBot AI" |
| Watchdog | Fuld watchdog (9 regler, 12 sek.) | Fuld watchdog (9 regler, 12 sek.) |
| Rapport | Nej | Ja (`/report BTCUSD`) |
| AI Debug | Nej | Ja (`/debug`) |
| Docker | `cryptobot` container | `cryptobot-ai` container |

---

## Filstruktur

```
CryptoBot/
├── main.py                          # Bot A: Regelbaseret trading bot
├── main_ai.py                       # Bot AI: AI-drevet med cycle trading + scale-in
├── config.example.yaml              # Eksempel-konfiguration
├── config.yaml                      # Bot A config (ikke i git)
├── config_ai.yaml                   # Bot AI config (ikke i git)
├── Dockerfile                       # Python 3.12 Docker image
├── docker-compose.yml               # Begge bots som services
├── requirements.txt                 # Python dependencies
├── src/
│   ├── api/
│   │   └── capital_client.py        # Capital.com REST API klient
│   ├── strategy/
│   │   ├── signals.py               # Signal engine (trend-following + mean-reversion)
│   │   ├── ai_analyst.py            # Claude AI analyse-modul
│   │   ├── regime_detector.py       # ADX(14) regime detection
│   │   ├── time_bias.py             # Time-of-day bias (historiske timereturns)
│   │   └── reddit_sentiment.py      # CryptoPanic + CoinGecko + Fear & Greed
│   ├── risk/
│   │   └── manager.py               # Risikostyring, ATR SL, confidence sizing
│   ├── executor/
│   │   ├── trade_executor.py        # Handelsudfoersel og SQLite logging
│   │   └── position_watchdog.py     # 7-regel positionsovervagning (12 sek.)
│   ├── notifications/
│   │   └── telegram_bot.py          # Telegram notifikationer og kommandoer
│   └── analysis/
│       └── reporter.py              # Data-analyse og rapportering
└── data/
    └── trades.db                    # SQLite handelshistorik
```

---

## Signal Engine (`src/strategy/signals.py`)

Scorer hvert coin og trigger handel ved score >= 4/9.

**Trend-filter (nyt):**
- Trade med EMA 9/21 trend: +1 score
- Trade mod trenden: -2 score (undtagen i RANGING regime)

**BUY scoring (lignende for SELL):**
1. Pris i buy zone (0-20% af 24h range) +1
2. Trend-aligned (EMA bullish) +1 / counter-trend -2
3. RSI < 30 (oversold) +2
4. Pris under nedre Bollinger Band +2
5. Bounce detection (engulfing, reversal) +1-2
6. Near support +1
7. Volume spike paa groen candle +1
8. MACD bullish divergence +2
9. Volume climax +2
10. Regime adjustment +1/-2
11. Time-of-day bias +1/-1

**SELL-specifikke signaler:**
- Failed breakout over range high: +3
- Volume climax paa roed candle: +2
- MACD bearish divergence: +2
- Memecoin sell zone: 75% (stramere end 80% for majors)
- Shorts blokeres medmindre regime er RANGING eller TRENDING_DOWN

---

## AI Analyst (`src/strategy/ai_analyst.py`)

Claude Haiku analyserer markedsdata og returnerer `{signal, confidence, reasoning}`.

**Kerneprincip (opdateret):** Trade med trenden. Mean-reversion kun i ranging markeder.

**Hvad AI'en modtager:**
- Alle tekniske indikatorer (RSI, EMA, BB, VWAP, ATR, MACD histogram)
- Seneste 6 candles med retning og stoerrelse
- Market regime (ADX) og time-of-day bias
- Sentiment (CryptoPanic, Fear & Greed, CoinGecko)
- Regel-bottens signal og score
- **Seneste 3 trades for denne coin** (feedback loop — laerer af fejl)

**AI regler:**
- Trending marked: kun trade i trend-retning
- Ranging marked: mean-reversion ved ekstremer
- Kraev altid confirmation candle (bounce, engulfing, volume)
- Cost awareness: kun trade naar forventet profit > 2x spread
- Shorts kraever 3+ tekniske bekraeftelser

**Confidence boost ved bot-enighed:**
- Regel-bot score >= 4 og samme signal: +2 confidence
- Regel-bot score >= 2 og samme signal: +1 confidence

---

## Regime Detection (`src/strategy/regime_detector.py`)

ADX(14) beregnet fra 1-times candles via Capital.com API.

| ADX | Regime | Strategi |
|-----|--------|----------|
| > 25 | TRENDING_UP / TRENDING_DOWN | Trade med trenden |
| < 20 | RANGING | Mean-reversion |
| 20-25 | NEUTRAL | Kun staerke signaler |

Wilder's smoothing for +DM/-DM/TR. 15-min cache per coin.

---

## Position Watchdog (`src/executor/position_watchdog.py`)

Baggrundstraad der tjekker positioner hver 12. sekund. 7 regler:

| # | Regel | Beskrivelse |
|---|-------|-------------|
| 1 | **Max holdtid** | Major: 24h, altcoin: 8h, memecoin: 4h. Lukker KUN tabere/breakeven — vindere haandteres af trailing stop |
| 2 | **Early exit** | 3+ accelererende modsat-candles → luk 50%. 4+ → luk 100%. Grace period: 15 min (nye positioner faar tid) |
| 3 | **Break-even** | Flyt SL til entry ved +1.5% profit (server-side paa Capital.com) |
| 3b | **Progressive SL** | Efter break-even: SL trails 1.0% bag nuvaerende pris. Opdateres server-side paa Capital.com naar SL rykker >= 0.3%. Overvaager botten crasher |
| 3c | **Profit pullback close** | Hvis peak P/L >= 1.5% OG pris falder 0.75% fra peak → LUK STRAKS. Den vigtigste profit-beskyttelse |
| 4 | **Delvis profit** | Luk 50% ved +4% profit, resten koerer med trailing |
| 5 | **Dynamisk TP** | Naar pris er inden for 1% af TP + positiv momentum: flyt TP op med 1.5x ATR (max 2 udvidelser) |
| 6 | **Trailing stop** | Aktiv ved +2.5% profit. Lukker naar pris falder 1.5x ATR fra peak |
| 7 | **Sentiment close** | Bearish time-of-day bias + profitable long → luk. Bullish bias + profitable short → luk. Baseret paa 7-dages historiske timereturns |
| 8 | **Cycle trading** | Ved positionslukning: re-analyserer for modsat retning. Begge bots har cycle trading (AI: conf>=7, Rule: strength>=5). 30 min cooldown |

**Scale-in** (hvert ~10 min): Hvis position er profitabel OG ny AI confidence >= entry confidence + 2, tilfoej 50% ekstra.

---

## Risikostyring (`src/risk/manager.py`)

### ATR-baseret Stop Loss
`stop_loss = entry_price * (1 ∓ atr_pct * 2.0)`, clamped til [3%, 8%]. Tilpasser sig automatisk til coin volatilitet (BTC ~1% vs DOGE ~3-5%).

### ATR-baseret Take Profit (grid-inspireret)
`take_profit = entry_price * (1 ± atr_pct * 1.5)`, clamped til [1.5%, 6.0%].
Stjålet fra grid trading: realistiske mål der faktisk rammes (3-4% typisk), i stedet for faste 7% der aldrig rammes.
Eksempel: BTC med 2% ATR → TP ved 3%. ETH med 2.5% ATR → TP ved 3.75%.

### Confidence-baseret Position Sizing
| Confidence | Multiplier | Betydning |
|------------|-----------|-----------|
| 6 | 25% | Decent setup |
| 7 | 50% | Staerk setup |
| 8 | 75% | Meget staerk |
| 9-10 | 100% | Exceptionel |

Regel-bot score mapping: 4→6, 5→7, 6→8, 7+→9.

### Kapitalallokering
| Kategori | Coins | Max pr. coin | Max total |
|----------|-------|-------------|-----------|
| Majors | BTC, ETH | 25% | — |
| Altcoins | SOL, XRP, ADA, AVAX, DOT, LINK, MATIC | 15% | — |
| Memecoins | DOGE, SHIBA, PEPE, FLOKI | 5% | — |
| Total | — | — | 80% (100% ved conf >= 9) |

### Kill Switch
- Dagligt tab > 5% → luk alt, stop handel
- Totalt tab > 30% → permanent stop

---

## Telegram Kommandoer

**Begge bots:**

| Kommando | Funktion |
|----------|----------|
| `/status` | Balance, positioner, holdtider, watchdog-status |
| `/trades` | Seneste 5 handler |
| `/scan` | Scan alle coins (med regime + AI confidence) |
| `/close EPIC` | Luk specifik position |
| `/close ALL` | Luk alle positioner |
| `/stop` | Stop botten |
| `/help` | Vis kommandoer |

**Kun Bot A:** `/buy EPIC SIZE`, `/sell EPIC SIZE`, `/sentiment`

**Kun Bot AI:** `/report EPIC` (detaljeret AI-analyse), `/debug` (ATR, regimer, holdtider, watchdog state)

---

## Konfiguration

Config-filer er i `.gitignore`. Eksempel:

```yaml
capital:
  email: "..."
  password: "..."
  api_key: "..."
  demo: true
  base_url: "https://demo-api-capital.backend-capital.com"
  account_name: "CryptoBot AI"  # kun config_ai.yaml

ai:  # kun config_ai.yaml
  anthropic_api_key: "sk-ant-..."
  model: "claude-haiku-4-5-20251001"
  max_tokens: 500
  min_confidence: 6

trading:
  coins: [BTCUSD, ETHUSD, SOLUSD, XRPUSD, ADAUSD,
          DOGEUSD, AVAXUSD, DOTUSD, LINKUSD, MATICUSD]
  leverage: 2
  timeframe: "HOUR"          # 1-times candles
  scan_interval: 300          # 5 min mellem scans

risk:
  profile: "moderate_aggressive"
  stop_loss: 4.0
  take_profit: 7.0
  atr_sl_multiplier: 2.0     # ATR-baseret SL
  atr_sl_min_pct: 3.0
  atr_sl_max_pct: 8.0
  max_hold_hours:
    major: 24
    altcoin: 8
    memecoin: 4
  allocation:
    max_total_exposure: 80
    max_memecoin: 5
    max_major: 25
    max_altcoin: 15
    min_position: 3

watchdog:
  check_interval: 12
  breakeven_trigger_pct: 1.5
  progressive_sl_trigger_pct: 2.0  # Start trailing SL server-side
  progressive_sl_trail_pct: 1.0    # Trail 1% bag pris
  pullback_peak_trigger_pct: 1.5   # Peak profit for pullback close
  pullback_close_pct: 0.75         # Pullback fra peak der trigger close
  trailing_trigger_pct: 2.5
  trailing_atr_mult: 1.5
  partial_profit_pct: 4.0
  partial_close_ratio: 0.5

signals:
  range_period: 24            # 24 x 1H = 24 timer
  buy_zone_pct: 20
  sell_zone_pct: 80
  min_range_pct: 3.0
```

---

## Deployment

### Hetzner VPS (produktion)
```bash
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70
cd /root/cryptobot
git pull origin master
docker compose down && docker compose up --build -d
docker compose logs --tail=30
```

Config-filer opdateres paa serveren via Python yaml manipulation (da de er i .gitignore):
```bash
python3 -c "
import yaml
with open('config.yaml', 'r') as f: cfg = yaml.safe_load(f)
cfg['trading']['timeframe'] = 'HOUR'
with open('config.yaml', 'w') as f: yaml.dump(cfg, f)
"
```

### Lokal udvikling
```bash
git clone https://github.com/AntonKryger/CryptoBot.git
cd CryptoBot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Rediger config.yaml med API-noegler
python main.py      # Bot A
python main_ai.py   # Bot AI
```

### Docker Compose
Begge bots deler samme Docker image men koerer som separate containere med isoleret data og logs:
- `cryptobot`: Bot A med `config.yaml`, `data/`, `logs/`
- `cryptobot-ai`: Bot AI med `config_ai.yaml`, `data_ai/`, `logs_ai/`

---

## Tech Stack
- **Python 3.12** + pandas (rene beregninger, ingen pandas-ta)
- **Capital.com REST API** (demo-server)
- **Claude Haiku 4.5** (Anthropic SDK) for AI-analyse
- **SQLite** for handelslog
- **Telegram Bot API** for notifikationer og kommandoer
- **Docker Compose** paa Hetzner VPS

---

## Changelog

### 09-03-2026: Grid trading optimering + profit-beskyttelse
**Hovedproblem:** Botten tog ikke profit. Positioner toppede (ETH +€428, BTC +€216) men blev holdt
mens prisen faldt. Account value gik fra €99.400 til €98.400 uden at botten reagerede.

**Nye watchdog-regler:**
- **Profit pullback close** (Rule 3c) — Hvis peak P/L >= 1.5% og pris falder 0.75% fra peak: LUK STRAKS.
  Eksempel: ETH peak +3.2% → lukker ved +2.45% (i stedet for at ride ned til break-even)
- **Progressive server-side SL** (Rule 3b) — SL trails 1.0% bag pris paa Capital.com server.
  Opdateres kun naar SL rykker >= 0.3% (undgaar API-spam). Virker selv hvis bot crasher
- **Sentiment-based close** (Rule 7) — Lukker profitable longs i bearish timer og shorts i bullish timer.
  Baseret paa 7 dages historiske timereturns via TimeBias

**Grid trading research (Pionex):**
- Undersoegt Grid Trading Bot, DCA/Martingale, Reverse Grid, Rebalancing, Spot-Futures Arbitrage
- Akademisk konklusion: grid trading uden trend-forudsigelse har forventet vaerdi = 0 minus fees
- **Hvad vi stjal:** Realistisk TP (ATR-baseret), cycle trading, hurtig re-entry
- **Hvad vi droppede:** Multi-position grids (CFD overnight fees draeber det), DCA/Martingale (eskalerende tab)

**ATR-baseret Take Profit:**
- TP aendret fra faste 7% til 1.5×ATR, clamped [1.5%, 6.0%]
- BTC med 2% ATR → TP ved 3% (realistisk, rammes faktisk)
- Grid trading insight: hyppige smaa profits slaar sjældne store

**Cycle trading for begge bots:**
- Rule-bot fik cycle trading (var kun paa AI-bot). Kraever signal strength >= 5
- Efter watchdog lukker position → tjek for modsat signal → abn ny position
- 10% af tilgaengelig kapital (konservativ), 30 min cooldown per coin

### 09-03-2026: Evidensbaseret strategiskift
**Aendringer:**
- **Timeframe 15min → 1H** — Reducerer noise, faerre handler, lavere spread-drag
- **Trend-following primaer strategi** — +1 score for trend-aligned, -2 for counter-trend
- **Mean-reversion kun i RANGING regime** (ADX < 20)
- **AI prompt omskrevet** — Trend-following regler, cost awareness, confirmation candle krav
- **AI feedback loop** — Seneste 3 trades per coin vises i AI prompt (laerer af fejl)
- **Scan interval 60s → 300s** — Matcher 1H timeframe

**Bugfixes:**
- Early exit grace period (15 min) — nye positioner fik ikke tid til at aande
- Early exit P/L threshold -0.5% → -1% til -3% — var for aggressiv
- LINKUSD stop-loss spam — break-even blev sat hvert 60s cycle (dedup fix)
- SOL rapid re-open — watchdog lukkede → scan genaabnede straks (cooldown fix)

**Research-baggrund:**
- Simpel trend-following: Sharpe 1.51 out-of-sample (SSRN), bestaerkest af Grayscale Research
- Mean-reversion paa 15-min: ingen akademisk stoette, kun daglige+ timeframes
- StochRSI/VWAP Z-score/Keltner: nul peer-reviewed evidens paa crypto intraday
- TA profitabilitet forsvinder typisk efter reelle spread/fee costs
- Jo flere indikatorer/parametre, jo stoerre risiko for overfitting

### 09-03-2026: 4-prioritets optimering
**Prioritet 1 — Risk Management:**
- ATR-baseret stop loss (2x ATR, clamped 3-8%)
- Max holdtid per kategori (major 24h, altcoin 8h, memecoin 4h)
- Trailing stop parametre: break-even +1.5%, trail +2.5% @ 1.5x ATR

**Prioritet 2 — Confidence Sizing & Scale-In:**
- Confidence multiplier: {6:0.25, 7:0.50, 8:0.75, 9:1.00}
- Scale-in ved stigende conviction (ny conf >= entry + 2, +50% position)

**Prioritet 3 — Dynamisk Exit:**
- Early exit paa momentum acceleration (3+ accelererende adverse candles)
- Dynamisk TP udvidelse (max 2x, 1.5 ATR per udvidelse)
- Cycle trading: re-analyse for reversal ved positionslukning

**Prioritet 4 — Market Regime & Short-side:**
- ADX(14) regime detector (TRENDING/RANGING/NEUTRAL)
- Time-of-day bias (historiske timereturns)
- MACD divergence (+2), volume climax (+2), failed breakout (+3)
- Memecoin sell zone strammet til 75%

### 07-03-2026: Bugfixes
- `/close ALL` bug (tjekkede for epic "ALL" foer ALL keyword)
- `close_position` 400 error (manglende direction/size i body)
- Kill switch 100% false trigger ved restart
- Duplikat-positioner fra manuelle `/buy` kommandoer

### 07-03-2026: Bot-samarbejde og watchdog
- Bot-samarbejde: Regel-bot signal sendes til AI som kontekst
- Position Watchdog: 12-sekunders overvagning
- Smart kapitalallokering med kategorigraenser
- To-pass scan-cyklus

---

## Kendte Begraensninger
- **Ingen backtesting** — Vigtigste manglende funktion. Uden out-of-sample test ved vi ikke om parameteraendringer hjaelper
- **CFD spread-cost** — 0.1-0.5% per trade. Signaler skal forvente profit > 2x spread for at vaere profitable
- **Crypto korrelation** — Alle coins er hoejt korrelerede (0.7-0.9). 10 positioner = reelt en stor crypto-bet
- **Capital.com session timeout** — Sessions udloeber efter 10 min inaktivitet (auto-refresh haandterer det)
- **Ingen WebSocket** — Bruger REST polling. Watchdog tjekker hvert 12 sek, ikke real-time

## Fremtidige Forbedringer (prioriteret)
1. **Backtesting framework** med walk-forward validering (vigtigst)
2. **Performance metrics** (Sharpe, Sortino, expectancy, profit factor)
3. **Half-Kelly position sizing** fra rolling trade statistik
4. **BTC Dominance filter** for altcoin trades
5. **Funding rate data** fra CoinGlass som score modifier
6. **WebSocket streaming** for hurtigere prisdata
