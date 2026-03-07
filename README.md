# CryptoBot

## Beskrivelse
Automatiseret crypto trading bot der handler CFD'er via Capital.com's API. Bruger multi-signal momentum strategi med konfigurerbar risikoprofil. Understoetter long og short positioner med 2x leverage.

## Status
Aktiv - koerer live paa demo-konto

## Sidst arbejdet paa
**Dato:** 07-03-2026 09:00
**Hvad blev lavet:**
- Range-trading strategi (mean-reversion) erstatter momentum-strategi
- Koeber i bunden af range, shorter i toppen - ikke omvendt
- Ny /scan kommando (viser alle coins med zone-position)
- /close ALL bug fikset
- Close position 400-fejl fikset (sender direction+size i DELETE body)
- Kill switch false-trigger fikset (reset ved genstart)
- Duplicate position check paa /buy og /sell
- Manuelle trades faar nu automatisk stop-loss og take-profit
- Fjernet ubrugt pandas-ta dependency
- Ny VPS: 91.98.26.70 (gammel 5.78.76.213 nedlagt)
- Deployed og kører live

**Naeste skridt:**
- [ ] Backtesting paa historisk data
- [ ] Multi-strategi: flere demo-konti med A/B test
- [ ] Evaluere range-trading resultater
- [ ] Tilfoej flere indikator-kombinationer

## Tech Stack
- Python 3.12
- Capital.com REST API (demo-server)
- pandas (teknisk analyse, rene beregninger)
- SQLite (handelslog)
- Telegram Bot API (notifikationer)
- GitHub: https://github.com/AntonKryger/CryptoBot (privat)

## Konfiguration
Alle indstillinger kan justeres i `config.yaml`:
- Risikoprofil (konservativ/moderat/aggressiv/moderate_aggressive)
- Stop-loss og take-profit procenter
- Leverage (standard 2x)
- Coins der handles (10 coins)
- Kill switch (max tab-graense)
- Tidsramme for analyse (15 min candles)

## Strategi: Range-Trading (Mean Reversion)
Koeber i bunden af range, shorter i toppen. Holder sig ude af midten.

| Zone | Position i range | Handling |
|------|-----------------|----------|
| Buy Zone | 0-20% (bund) | KOEB - pris nær support |
| Neutral | 20-80% (midt) | HOLD - ingen edge |
| Sell Zone | 80-100% (top) | SHORT - pris nær resistance |

### Signal scoring (minimum 4 af 9 for at handle)
1. Pris i korrekt zone (bund/top af 24h range)
2. RSI (oversold/overbought)
3. Bollinger Band position
4. Bounce/rejection candle patterns
5. Support/resistance nærhed
6. Volume bekræftelse

### Risikostyring
- Stop-loss: 4% (moderate_aggressive profil)
- Take-profit: 7%
- Trailing stop: Flyt stop-loss til break-even ved +3%
- Max position: 20% af portfolio per trade
- Ingen cap paa aabne positioner
- Kill switch: Stop handel ved -5% dagligt eller -30% totalt

## Features
- [x] Kravspecifikation
- [x] Capital.com API integration
- [x] Signal engine (EMA, RSI, Volume, VWAP)
- [x] Risk manager (stop-loss, take-profit, kill switch)
- [x] Order executor (long + short)
- [x] 2x leverage support
- [x] Telegram notifikationer
- [x] Konfigurerbar risikoprofil via config.yaml
- [x] Data-analyse modul (Claude Code samarbejde)
- [x] Cloud deployment (Hetzner VPS, Docker, 24/7)
- [x] Telegram kommandoer (/status, /trades, /scan, /buy, /sell, /close, /stop, /help)
- [x] Range-trading strategi (mean-reversion)
- [x] Bugfixes (/close ALL, close position API, kill switch, duplicates)
- [ ] Multi-strategi (flere demo-konti)
- [ ] Backtesting

## Installation
```bash
# Klon repository
git clone https://github.com/AntonKryger/CryptoBot.git
cd CryptoBot

# Opret virtuelt miljoe
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Installer dependencies
pip install -r requirements.txt

# Kopier config
cp config.example.yaml config.yaml
# Rediger config.yaml med dine API-noegler

# Koer botten
python main.py
```

## Projektbeslutninger
- **Capital.com** valgt som exchange (brugerens eksisterende platform)
- **CFD-handel** - muliggoer short selling og leverage
- **Python** valgt pga. bedste biblioteker til trading og dataanalyse
- **Rene pandas beregninger** i stedet for pandas-ta (hurtigere, mere paalideligt)
- **Multi-signal strategi** - reducerer falske signaler vs. enkelt-indikator
- **Konfigurerbar risikoprofil** - kan justeres uden kodeaendringer
- **Intet dashboard** - Capital.com's platform bruges til overblik
- **Telegram** til notifikationer
- **Cloud-server** planlagt for 24/7 drift
- **Data-analyse modul** - saa bot-data kan gennemgaas i Claude Code sessioner
