# CryptoBot

## Beskrivelse
Automatiseret crypto trading bot der handler CFD'er via Capital.com's API. Bruger multi-signal momentum strategi med konfigurerbar risikoprofil. Understoetter long og short positioner med 2x leverage.

## Status
Aktiv - koerer live paa demo-konto

## Sidst arbejdet paa
**Dato:** 07-03-2026 02:30
**Hvad blev lavet:**
- Telegram kommandoer implementeret (/status, /trades, /buy, /sell, /close, /stop, /help)
- Command listener i baggrundstraad (polling-baseret)
- SQLite thread-safety fix (ny forbindelse per forespoergsel)
- Ny Hetzner VPS med SSH-noegle (ed25519) i stedet for password
- Re-deployed til VPS med Docker

**Naeste skridt:**
- [ ] Backtesting paa historisk data
- [ ] Multi-strategi: flere demo-konti med A/B test
- [ ] Forbedre signal engine baseret paa resultater
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

## Strategi: Smart Momentum
Multi-signal tilgang - handler kun naar flere indikatorer er enige:

| Signal | Koeb | Saelg |
|--------|------|-------|
| EMA Crossover (9/21) | EMA9 > EMA21 | EMA9 < EMA21 |
| RSI | Under 70 | Over 30 (short) |
| Volume | Over 1.5x gennemsnit | Over 1.5x gennemsnit |
| VWAP | Pris over VWAP | Pris under VWAP |

### Risikostyring
- Stop-loss: 4% (moderate_aggressive profil)
- Take-profit: 7%
- Trailing stop: Flyt stop-loss til break-even ved +3%
- Max position: 20% af portfolio per trade
- Max aabne positioner: 5
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
- [x] Telegram kommandoer (/status, /trades, /buy, /sell, /close, /stop, /help)
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
