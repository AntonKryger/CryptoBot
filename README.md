# CryptoBot

## Beskrivelse
Automatiseret crypto trading-system der handler CFD'er via Capital.com's API. Systemet bestaar af **to uafhaengige bots** der koerer parallelt paa hver sin demo-konto som et A/B test-setup:

- **Bot A** (regelbaseret): Ren teknisk analyse med scoring-system
- **Bot AI** (AI-drevet): Claude Haiku analyserer markedsdata og traffer beslutninger

Begge bots samarbejder ved at Bot AI modtager Bot A's signal som ekstra kontekst i sin analyse. Naar de er enige, boostes AI'ens confidence, hvilket giver staerkere overbevisning om handler.

## Status
Aktiv - koerer live paa to Capital.com demo-konti via Docker paa VPS

## Sidst arbejdet paa
**Dato:** 07-03-2026 18:00
**Hvad blev lavet:**
- Bot-samarbejde: Regel-bot signal sendes til AI som kontekst
- Confidence boost naar begge bots er enige (+2 ved fuld enighed, +1 ved delvis)
- Position Watchdog: Hurtig positionsovervagning hver 12. sekund
- ATR-baseret trailing stop (dynamisk, tilpasser sig volatilitet)
- Delvis profit-taking (luk 50% ved +4% profit)
- Break-even stop (flyt stop-loss til entry ved 1x ATR profit)
- Smart kapitalallokering: Fordeling baseret paa confidence og coin-kategori
- Kategoribaserede graenser: Memecoins max 5%, majors max 25%, altcoins max 15%
- To-pass scan-cyklus: Forst saml alle signaler, dernaest alloker kapital
- Markedsstatus-tjek: Springer scan over naar markeder er lukket
- Duplikat-positionstjek: Aabner ikke ny position i coin der allerede er aaben
- AI system prompt aendret til moderat-aggressiv trading-stil
- Min confidence saenket fra 6 til 5 for AI-bot
- Reasoning-visning udvidet fra 200 til 500 tegn i Telegram

**Naeste skridt:**
- [ ] Backtesting paa historisk data
- [ ] WebSocket streaming for hurtigere prisdata
- [ ] Multi-timeframe analyse (15min + 1h + 4h)
- [ ] Portfolio heat map i Telegram
- [ ] Automatisk performance-sammenligning mellem Bot A og Bot AI

---

## Arkitektur

### Systemdiagram
```
                    Capital.com API
                    /              \
               Bot A              Bot AI
            (main.py)          (main_ai.py)
               |                    |
          config.yaml          config_ai.yaml
               |                    |
        Demo-konto 1          Demo-konto 2
       "Crypto bot"          "CryptoBot AI"
               |                    |
        Telegram Bot 1        Telegram Bot 2
    @claude_cryptobot_bot  @cryptobot_ai_anton_bot
```

### To-bot A/B test
Begge bots handler de samme 10 coins, med samme risiko-parametre, men med forskellig beslutningslogik. Formålet er at sammenligne regelbaseret vs. AI-drevet trading over tid:

| Egenskab | Bot A (Regel) | Bot AI (Claude) |
|----------|---------------|-----------------|
| Entry-fil | `main.py` | `main_ai.py` |
| Config | `config.yaml` | `config_ai.yaml` |
| Beslutning | Score-system (min 4/9) | Claude Haiku (min 5/10) |
| Konto | "Crypto bot" (default) | "CryptoBot AI" |
| Watchdog | Nej (enkel trailing stop) | Ja (ATR-baseret, 12 sek.) |
| Rapport | Nej | Ja (/report BTCUSD) |
| Docker | `cryptobot` container | `cryptobot-ai` container |

---

## Filstruktur

```
CryptoBot/
├── main.py                          # Bot A: Regelbaseret trading bot
├── main_ai.py                       # Bot AI: AI-drevet trading bot
├── config.example.yaml              # Eksempel-konfiguration
├── config.yaml                      # Bot A config (ikke i git)
├── config_ai.yaml                   # Bot AI config (ikke i git)
├── Dockerfile                       # Python 3.12 Docker image
├── docker-compose.yml               # Koerer begge bots som services
├── requirements.txt                 # Python dependencies
├── src/
│   ├── api/
│   │   └── capital_client.py        # Capital.com REST API klient
│   ├── strategy/
│   │   ├── signals.py               # Regelbaseret signal engine
│   │   └── ai_analyst.py            # Claude AI analyse-modul
│   ├── risk/
│   │   └── manager.py               # Risikostyring og kapitalallokering
│   ├── executor/
│   │   ├── trade_executor.py        # Handelsudfoersel og SQLite logging
│   │   └── position_watchdog.py     # Hurtig positionsovervagning (12 sek.)
│   ├── notifications/
│   │   └── telegram_bot.py          # Telegram notifikationer og kommandoer
│   └── analysis/
│       └── reporter.py              # Data-analyse og rapportering
└── data/
    └── trades.db                    # SQLite handelshistorik
```

---

## Detaljeret Systembeskrivelse

### 1. Capital.com API Klient (`src/api/capital_client.py`)

Haandterer al kommunikation med Capital.com's REST API:

- **Session management**: Automatisk login med CST/X-SECURITY-TOKEN, auto-refresh ved 401
- **Rate limiting**: Max 10 requests/sekund for at undga API-blokering
- **Konto-switching**: Kan skifte mellem sub-konti (brugt til at koere Bot AI paa separat konto)
- **Market status**: `is_market_open()` og `are_crypto_markets_open()` tjekker om markeder er aabne via API'ens `marketStatus` felt. Begge bots springer scan over naar markeder er lukket, hvilket forhindrer 400-fejl ved ordreplacering i weekender.
- **Prisdata**: Henter historiske candles (15-minutters standard)
- **Positionsstyring**: Aabne, lukke og opdatere positioner med SL/TP
- **Ordre-typer**: Markedsordrer og limit-ordrer

**Hvorfor denne design?**
Capital.com's API kraever session-tokens i stedet for persistente API keys. Klienten haandterer dette transparent saa resten af systemet aldrig behoever at taenke paa authentication.

### 2. Regelbaseret Signal Engine (`src/strategy/signals.py`)

Bot A's hjerne. Scorer hvert coin paa 9 kriterier og trigger handel ved score >= 4:

**Tekniske indikatorer beregnet:**
- EMA 9/21 (trend)
- RSI 14 (overbought/oversold)
- Bollinger Bands (volatilitet)
- VWAP (volumen-vaegtet gennemsnit)
- ATR (Average True Range, volatilitet)
- Rate of Change 3/6 (momentum)
- Volume spike detection
- Support/resistance niveauer
- 24-timers range position (0-100%)
- Candlestick patterns (engulfing)

**Scoring-system for BUY (lignende for SELL):**
1. Pris i buy zone (0-20% af 24h range)
2. RSI under 30 (oversold)
3. Pris under nedre Bollinger Band
4. Bullish engulfing pattern
5. Pris naer support
6. Volume spike
7. Positiv momentum (ROC)
8. Pris under VWAP
9. EMA 9 > EMA 21 (bullish crossover)

**Sentiment data:**
- CryptoPanic API (nyheder)
- CoinGecko API (community data)
- Fear & Greed Index
- Reddit-lignende sentiment scoring

### 3. AI Analyst (`src/strategy/ai_analyst.py`)

Bot AI's hjerne. Bruger Claude Haiku API til at analysere al tilgaengelig markedsdata.

**Hvordan det virker:**
1. Signal Engine beregner alle tekniske indikatorer (samme som Bot A)
2. Sentiment-data hentes fra CryptoPanic/CoinGecko
3. Bot A's regelbaserede signal beregnes
4. Alt data pakkes i en struktureret prompt til Claude
5. Claude returnerer JSON: `{"signal": "BUY", "confidence": 7, "reasoning": "..."}`
6. Confidence boostes naar begge bots er enige

**System prompt - noegleprincipperne:**
- Moderat-til-aggressiv trading-stil
- "Du er en TRADER, ikke en tilskuer" - fokus paa at finde handler
- Position Watchdog beskytter alle handler, saa AI behover ikke vaere overkautios
- Fear & Greed "Extreme Fear" = KOB-mulighed (contrarian)
- Confidence 5+ = gyldigt setup, 7+ = staerk overbevisning
- Naar regel-bot er enig, oeg confidence med 1-2 point

**Bot-samarbejde (confidence boost):**
```
AI signal = BUY, regel-bot signal = BUY:
  - Regel-bot score >= 4: confidence + 2 (fuld enighed)
  - Regel-bot score >= 2: confidence + 1 (delvis enighed)
```

**Hvorfor denne tilgang?**
AI'en var oprindeligt for konservativ - returnerede HOLD paa alt med confidence 3-4. Ved at give den en trader-mentalitet og lade den bruge regel-bottens signal som validering, faar den mod til at tage handler naar signalerne er der. Watchdog'en giver et sikkerhedsnet der goer det OK at vaere lidt mere aggressiv paa entries.

**Rapport-funktion:**
`/report BTCUSD` genererer en detaljeret analyse paa dansk med 6 sektioner: pris/range, tekniske indikatorer, price action, sentiment, regel-bot sammenligning, og konklusion.

### 4. Risikostyring (`src/risk/manager.py`)

Kontrollerer positionsstaerrelse, kapitalallokering og kill switch.

**Coin-kategorier med allokeringsgraenser:**

| Kategori | Coins | Max allokering pr. coin |
|----------|-------|------------------------|
| Majors | BTC, ETH | 25% af balance |
| Altcoins | SOL, XRP, ADA, AVAX, DOT, LINK, MATIC | 15% af balance |
| Memecoins | DOGE, SHIBA, PEPE, FLOKI | 5% af balance |

**Smart kapitalallokering (`allocate_capital()`):**
1. Sorterer alle signaler efter confidence (hoejest foerst)
2. Beregner total vaegtning ud fra confidence
3. Fordeler kapital proportionelt med confidence
4. Capper hver allokering til kategoriens max
5. Springer over hvis allokering er under minimum (3% af balance)
6. Max total eksponering: 80% af balance

**Hvorfor dette system?**
Oprindeligt brugte botten 100% af balancen paa en enkelt position. BTC kunne tage 86% af kontoen (EUR 86k af EUR 100k). Med kategori-baseret allokering spredes risikoen, og memecoins (hoej volatilitet) faar kun en lille andel.

**Kill switch:**
- Dagligt tabsgraense: -5% -> luk alle positioner, stop handel
- Totalt tabsgraense: -30% -> luk alle positioner, stop permanent
- Nulstilles ved ny dag

### 5. Position Watchdog (`src/executor/position_watchdog.py`)

Hurtig positionsovervagning der koerer i en baggrundstraad. Kun brugt af Bot AI.

**Hvorfor den blev bygget:**
En DOGE-position tabte EUR 281 fordi bottens 60-sekunders scan-cyklus + API-kaldstid var for langsom til at reagere paa et hurtigt prisfald. Watchdoggen tjekker positioner hver 12. sekund uden AI-kald.

**Tre regler:**

**Regel 1: Break-even stop (1x ATR)**
Naar profit overstiger 1x ATR (f.eks. 2% ved ATR=2%), flyttes stop-loss til entry-pris paa Capital.com's server. Positionen kan herefter ikke tabe penge. Sker server-side, saa den er aktiv selv hvis bot crasher.

**Regel 2: Delvis profit-taking (50% ved +4%)**
Naar profit naar 4%, lukkes halvdelen af positionen automatisk. Resten koerer videre med trailing stop. Dette sikrer profit paa gode handler selv hvis prisen vender.

**Regel 3: ATR-baseret trailing stop (2x ATR fra peak)**
Tracker den bedste pris siden entry. Naar prisen falder 2x ATR fra peak, lukkes hele positionen. ATR-vaerdierne caches og opdateres af hoved-scancyklussen.

**Hvorfor ATR-baseret og ikke fast procent?**
BTC har typisk ATR paa 0.5-1%, mens DOGE kan have 3-5%. Et fast 2% trailing stop ville vaere for tight for DOGE og for loest for BTC. Ved at bruge ATR-multiplikator tilpasser stoppet sig automatisk til hver coins volatilitet.

### 6. Trade Executor (`src/executor/trade_executor.py`)

Udforer handler og logger dem i SQLite database.

- Cooldown: 5 minutter mellem handler paa samme coin
- Duplikattjek: Kan ikke aabne to positioner i samme coin
- SQLite logging: Alle handler logges med timestamp, pris, SL/TP, deal ID, signal details
- Statistik: Win rate, total P/L, gennemsnitlig P/L

### 7. Telegram Notifikationer (`src/notifications/telegram_bot.py`)

To separate Telegram bots, en for hver trading-bot:

**Bot A:** @claude_cryptobot_bot
**Bot AI:** @cryptobot_ai_anton_bot

**Kommandoer (begge bots):**

| Kommando | Funktion |
|----------|----------|
| `/status` | Balance, positioner, statistik, watchdog-status |
| `/trades` | Seneste 5 handler |
| `/scan` | Scan alle coins med signaler |
| `/close EPIC` | Luk specifik position |
| `/close ALL` | Luk alle positioner |
| `/stop` | Stop botten |
| `/help` | Vis kommandoer |

**Kun Bot A:**
| `/buy EPIC SIZE` | Manuel koeb |
| `/sell EPIC SIZE` | Manuel short |
| `/sentiment` | Reddit sentiment |

**Kun Bot AI:**
| `/report EPIC` | Detaljeret AI-analyse rapport |

### 8. To-pass Scan-cyklus

Begge bots bruger samme scan-arkitektur, implementeret efter DOGE-spamproblemet (30+ handler paa 1.5 time):

```
PASS 1: Indsaml signaler
  For hver coin:
    - Tjek om position allerede er aaben -> skip
    - Hent prisdata og beregn indikatorer
    - (Bot AI: Hent sentiment + kald Claude API)
    - Gem signal med confidence/styrke

PASS 2: Alloker og eksekver
  - Sorter signaler efter confidence
  - allocate_capital() fordeler tilgaengelig kapital
  - Eksekver handler med korrekt stoerrelse
  - Log til database og send Telegram-notifikation
```

**Hvorfor to-pass?**
Tidligere eksekverede botten handler enkeltvis per coin. Resultatet var at den foerste coin med signal fik hele kontoen, og resten blev sprunget over. To-pass loeser dette ved foerst at se det samlede billede og dernaest fordele intelligent.

**Forudgaaende checks:**
- Kill switch (dagligt/totalt tab)
- Markedsstatus (aabent/lukket)
- Max aabne positioner
- Allerede aabne positioner i samme coin

---

## Tech Stack
- **Python 3.12** - Hovedsprog
- **Capital.com REST API** - Trading og markedsdata (demo-server)
- **Claude Haiku API** (Anthropic SDK) - AI-analyse
- **pandas** - Teknisk analyse (rene beregninger, ingen pandas-ta)
- **SQLite** - Handelslog
- **Telegram Bot API** - Notifikationer og kommandoer
- **Docker + Docker Compose** - Deployment
- **Hetzner VPS** - 24/7 drift
- **GitHub** - Versionsstyring (privat repo)

## Konfiguration

Alle indstillinger i `config.yaml` / `config_ai.yaml` (ikke i git):

```yaml
# Capital.com API
capital:
  email: "..."
  password: "..."
  api_key: "..."
  demo: true
  account_name: "CryptoBot AI"  # kun i config_ai.yaml

# Trading
trading:
  coins: [BTCUSD, ETHUSD, SOLUSD, XRPUSD, ADAUSD,
          DOGEUSD, AVAXUSD, DOTUSD, LINKUSD, MATICUSD]
  leverage: 2
  timeframe: "MINUTE_15"
  scan_interval: 60

# Risikostyring
risk:
  profile: "moderate_aggressive"
  stop_loss: 4.0          # procent
  take_profit: 7.0        # procent
  trailing_stop_trigger: 3.0
  max_open_positions: 6
  daily_loss_limit: 5.0   # kill switch
  total_loss_limit: 30.0  # kill switch
  allocation:
    max_total_exposure: 80  # max 80% af balance i positioner
    max_memecoin: 5         # max 5% pr. memecoin
    max_major: 25           # max 25% pr. major (BTC/ETH)
    max_altcoin: 15         # max 15% pr. altcoin
    min_position: 3         # min 3% for at aabne position

# AI (kun config_ai.yaml)
ai:
  anthropic_api_key: "sk-ant-..."
  model: "claude-haiku-4-5-20251001"
  max_tokens: 300
  min_confidence: 5

# Watchdog (kun config_ai.yaml)
watchdog:
  check_interval: 12       # sekunder
  trailing_atr_mult: 2.0   # 2x ATR fra peak
  partial_profit_pct: 4.0  # tag profit ved +4%
  partial_close_ratio: 0.5 # luk 50%
  breakeven_atr_mult: 1.0  # break-even ved 1x ATR
```

## Deployment

### Docker Compose (VPS)
```bash
# SSH til VPS
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70

# Deploy
cd /opt/cryptobot
git pull
docker compose up -d --build
```

Begge bots koerer som separate Docker-containere med `restart: always`. Config-filer er monteret som volumes og ligger kun paa serveren (ikke i git).

### Lokal udvikling
```bash
git clone https://github.com/AntonKryger/CryptoBot.git
cd CryptoBot
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Rediger config.yaml med dine API-noegler
python main.py      # Koer Bot A
python main_ai.py   # Koer Bot AI
```

---

## Loeste Problemer og Laerdomme

### DOGE-spam (30+ handler paa 1.5 time)
**Problem:** Bot A aabnede DOGE-positioner hvert minut. Root cause: Botten genstartede ofte (nulstillede cooldown), ingen duplikattjek, `max_open_positions: 99`.
**Loesning:** To-pass scan med aaben-positionstjek, max 6 positioner, kategorigraenser.

### BTC tog 86% af kontoen
**Problem:** En enkelt BTC-position brugte EUR 86k af EUR 100k margin.
**Loesning:** Kategoribaseret kapitalallokering. BTC (major) maks 25%, memecoins maks 5%.

### AI for konservativ (HOLD paa alt)
**Problem:** Alle coins returnerede HOLD med confidence 3-4, selv naar tekniske signaler var staerke.
**Loesning:** Omskrev system prompt til trader-mentalitet, saenkede min_confidence til 5, tilfoejede confidence boost ved bot-enighed.

### DOGE-tab paa EUR 281
**Problem:** Prisen crashede hurtigere end 60-sekunders scancyklussen kunne reagere.
**Loesning:** Position Watchdog der tjekker hver 12. sekund med ATR-baseret trailing stop.

### Weekend-handelsfejl (400 errors)
**Problem:** Bots forsogte at handle i weekenden naar markeder var lukket.
**Loesning:** `are_crypto_markets_open()` tjekker markedsstatus foer scan.

### Forkert konto lukket
**Problem:** Ved manuel lukning af positioner blev den forkerte konto ramt.
**Loesning:** Separate Docker-containere med separate configs og separate Telegram-bots.

---

## Forslag til Naeste Tilfoejelser

### 1. WebSocket Streaming (Hoej prioritet)
**Hvad:** Erstat polling med real-time prisdata via Capital.com's WebSocket API.
**Hvorfor:** I dag henter botten priser hvert 60. sekund. Med WebSocket faar Watchdoggen prisaendringer i real-time (<1 sekund), hvilket dramatisk forbedrer trailing stop reaktionstid. Capital.com's API understotter allerede WebSocket.
**Implementering:**
- Tilfoej WebSocket-klient i `capital_client.py` (allerede importerer `websocket`)
- Subscribe paa prisfeeds for alle 10 coins
- Watchdoggen laesser fra en delt pris-cache i stedet for at kalde REST API
- Fallback til REST polling hvis WebSocket disconnecter
**Vaerdi:** Reducerer reaktionstid fra 12 sek til under 1 sek. Reducerer API-kald markant.

### 2. Multi-timeframe Analyse (Hoej prioritet)
**Hvad:** Brug baade 15-min, 1-times og 4-timers candles i analysen.
**Hvorfor:** En BUY paa 15-min i en 4-timers downtrend er en daarlig handel. Multi-timeframe bekraeftelse filtrerer falske signaler.
**Implementering:**
- Hent 3 timeframes per coin i scan-cyklus
- Tilfoej "hoejere timeframe trend" til prompt/scoring
- Krav: hoejere timeframe maa ikke modarbejde signalet
**Vaerdi:** Faerre falske signaler, bedre win rate.

### 3. Automatisk Performance Dashboard (Medium prioritet)
**Hvad:** Daglig/ugentlig sammenligning af Bot A vs Bot AI sendt som Telegram-rapport.
**Hvorfor:** Hele pointen med A/B testen er at se hvilken tilgang der virker bedst. Uden automatisk sammenligning skal man manuelt gennemgaa data.
**Implementering:**
- Daglig cronjob der laeser begge SQLite databaser
- Beregner: total P/L, win rate, gennemsnitlig holdtid, Sharpe ratio
- Sender sammenligningsrapport til en faelles Telegram-kanal
**Vaerdi:** Data-drevet beslutning om hvilken bot der skal koere paa live-konto.

### 4. Backtesting Framework (Medium prioritet)
**Hvad:** Test strategier paa historisk data foer de koerer live.
**Hvorfor:** Lige nu testes nye strategier direkte paa demo-kontoen. Backtesting lader dig teste paa maaneders data paa sekunder.
**Implementering:**
- Hent og gem historiske priser (Capital.com giver 10.000 candles)
- Simuler scan-cyklus med historiske data
- Beregn P/L, drawdown, win rate for enhver strategi
- Visualiser med matplotlib eller send til Telegram
**Vaerdi:** Hurtigere iteration, undga at teste daarlige strategier med rigtige penge.

### 5. Dynamisk Risikoprofil (Medium prioritet)
**Hvad:** Automatisk justerer risiko-parametre baseret paa recent performance.
**Hvorfor:** En fast 4% stop-loss er optimal i et volatilt marked, men for tight i et roligt marked. Performance-baseret justering tilpasser sig automatisk.
**Implementering:**
- Track de seneste 20 handlers win rate og gennemsnitlig P/L
- Vindende streak: gradvis oeg positionsstaerrelse (max 1.5x)
- Tabende streak: reducer positionsstaerrelse (min 0.5x)
- Hoej volatilitet: oeg stop-loss og trailing distance
- Lav volatilitet: straem stop-loss
**Vaerdi:** Reducerer tab i daarlige perioder, maximerer profit i gode perioder.

### 6. Ordrebog-analyse (Lav prioritet, hoej vaerdi)
**Hvad:** Analyser buy/sell ordrer paa boersen for at forudsige prisbevagelser.
**Hvorfor:** Store buy walls = support, store sell walls = resistance. Ordrebogen viser hvad andre tradere planlagger.
**Implementering:** Capital.com understotter ikke ordrebog-data, saa dette ville kraeve en sekundaer datakilde (f.eks. Binance API for spot-data som proxy).
**Vaerdi:** Forbedret support/resistance identifikation.

### 7. Korrelationsbaseret Risikostyring (Lav prioritet)
**Hvad:** Tag hoejde for at BTC og altcoins er korrelerede.
**Hvorfor:** At vaere long i BTC, ETH, SOL og XRP samtidig er reelt set en enkelt bet paa crypto-markedet. Aedte diversifikation kraever korrelationsbevidsthed.
**Implementering:**
- Beregn rolling korrelation mellem alle coin-par
- Reducer samlet eksponering naar alle positioner er korrelerede
- Tilfoej "portfolio correlation score" til risk manager
**Vaerdi:** Undgaa scenariet hvor alle 6 positioner taber samtidig i et markedsfald.

### 8. Sentiment fra Multiple Kilder (Lav prioritet)
**Hvad:** Tilfoej Twitter/X, Telegram-grupper og on-chain data som sentimentkilder.
**Hvorfor:** CryptoPanic og Fear & Greed giver et godt overblik, men on-chain data (whale movements, exchange inflows) er mere handlingsbare signaler.
**Implementering:**
- Whale Alert API for store transaktioner
- Glassnode/CryptoQuant for exchange flow data
- Vaegt de forskellige kilder i AI-prompten
**Vaerdi:** Tidligere warning om store markedsbevagelser.

---

## Projektbeslutninger
- **To separate bots** - A/B test giver data til at vurdere om AI tilfojer vaerdi vs. regler
- **Capital.com** - Brugerens eksisterende platform, CFD muliggoer shorting og leverage
- **Claude Haiku** - Billigst Claude model, hurtig nok til 60-sek cyklus, god nok til teknisk analyse
- **Kategoribaseret allokering** - Forhindrer at en enkelt coin dominerer kontoen
- **Position Watchdog** - Loesning paa det fundamentale problem at scancyklus er for langsom til exit
- **Bot-samarbejde (ikke -konkurrence)** - AI faar mere data at arbejde med, regel-bot validerer AI'en
- **Rene pandas beregninger** - Hurtigere og mere paalideligt end pandas-ta biblioteket
- **Docker Compose** - Simpel deployment, begge bots deler samme image men koerer separat
- **SQLite** - Nemt, filbaseret, perfekt til en enkelt bots handelslog
- **Telegram** - Brugerens foretrukne platform, god til notifikationer og hurtige kommandoer
