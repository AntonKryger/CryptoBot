# CryptoBot

## Beskrivelse
Automatiseret crypto trading bot der handler CFD'er via Capital.com's API. Bruger multi-signal momentum strategi med konfigurerbar risikoprofil. Understøtter long og short positioner med 2x leverage.

## Status
Aktiv

## Sidst arbejdet paa
**Dato:** 06-03-2026
**Hvad blev lavet:**
- Projekt oprettet
- Kravspecifikation defineret
- Capital.com API adgang bekraeftet (demo-konto med €1.000)

**Naeste skridt:**
- [ ] Opsaet Python-miljoe og dependencies
- [ ] Byg Capital.com API-forbindelse (session, auth)
- [ ] Hent prisdata og test WebSocket
- [ ] Implementer signal engine (EMA, RSI, Volume, VWAP)
- [ ] Implementer risk manager (stop-loss, take-profit, kill switch)
- [ ] Implementer order executor
- [ ] Byg data-analyse modul (til samarbejde i Claude Code)
- [ ] Opsaet Telegram notifikationer
- [ ] Backtesting paa historisk data
- [ ] Deploy til cloud-server (VPS)

## Tech Stack
- Python 3.12+
- Capital.com REST + WebSocket API
- pandas / pandas-ta (teknisk analyse)
- SQLite (handelslog)
- python-telegram-bot (notifikationer)
- APScheduler (scheduling)
- Docker (til deployment)

## Konfiguration
Alle indstillinger kan justeres i `config.yaml`:
- Risikoprofil (konservativ/moderat/aggressiv)
- Stop-loss og take-profit procenter
- Leverage (standard 2x)
- Coins der handles
- Kill switch (max tab-graense)
- Tidsramme for analyse

## Strategi: Smart Momentum
Multi-signal tilgang - handler kun naar flere indikatorer er enige:

| Signal | Koeb | Saelg |
|--------|------|-------|
| EMA Crossover (9/21) | EMA9 > EMA21 | EMA9 < EMA21 |
| RSI | Under 70 | Over 75 eller under 25 (short) |
| Volume | Over 1.5x gennemsnit | - |
| VWAP | Pris over VWAP | Pris under VWAP |

### Risikostyring
- Stop-loss: Konfigurerbar (standard 3-5%)
- Take-profit: Konfigurerbar (standard 5-8%)
- Trailing stop: Flyt stop-loss til break-even ved +3%
- Max position: 20% af portfolio per trade
- Kill switch: Stop al handel ved konfigurerbart max-tab

## Features
- [x] Kravspecifikation
- [ ] Capital.com API integration
- [ ] Signal engine (EMA, RSI, Volume, VWAP)
- [ ] Risk manager
- [ ] Order executor (long + short)
- [ ] 2x leverage support
- [ ] Multi-strategi (flere demo-konti)
- [ ] Data-analyse modul (Claude Code samarbejde)
- [ ] Telegram notifikationer
- [ ] Backtesting
- [ ] Cloud deployment (VPS)
- [ ] Konfigurerbar risikoprofil via config.yaml

## Installation
```bash
# Klon repository
git clone <repo-url>
cd CryptoBot

# Opret virtuelt miljoe
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Installer dependencies
pip install -r requirements.txt

# Kopier config
cp config.example.yaml config.yaml
# Rediger config.yaml med dine API-nogler

# Koer botten
python main.py
```

## Projektbeslutninger
- **Capital.com** valgt som exchange (brugerens eksisterende platform)
- **CFD-handel** - muliggoer short selling og leverage
- **Python** valgt pga. bedste biblioteker til trading og dataanalyse
- **Multi-signal strategi** - reducerer falske signaler vs. enkelt-indikator
- **Konfigurerbar risikoprofil** - kan justeres uden kodeaendringer
- **Intet dashboard** - Capital.com's platform bruges til overblik
- **Telegram** til notifikationer
- **Cloud-server** for 24/7 drift
- **Data-analyse modul** - saa bot-data kan gennemgaas i Claude Code sessioner
- **Docker** til nem deployment paa VPS
