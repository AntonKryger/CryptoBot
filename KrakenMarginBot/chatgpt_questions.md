# ChatGPT Spørgsmål — KrakenBots Multi-Bot System

> **Kontekst til ChatGPT:** Jeg bygger et multi-bot trading system til Kraken (spot + futures).
> Fase 0 er færdig: 4 strategier (Grid, Trend, MeanRev, Volatility), en Coordinator der
> håndterer regime-handoff mellem bot-par, SpotPositionTracker (SQLite), RiskManager,
> og Docker-compose. Alt kører på Python/ccxt. Jeg starter med Par 1 (Grid + Trend).
> Giv mig **konkrete tal, thresholds og pseudokode** — ikke generelle forklaringer.

---

## 1. Regime Detection — ADX Tuning

Jeg bruger ADX til regime-klassificering: ADX ≥ 25 = TRENDING, ADX < 20 = RANGING, 20–25 = NEUTRAL (ingen trading). Beregnet på 1H candles.

**Spørgsmål:** Er ADX 25/20 de optimale thresholds for crypto på 15-min og 1H timeframes? Bør jeg bruge forskellige thresholds per coin (BTC vs altcoins)? Hvor mange candles skal ADX beregnes over (jeg bruger default 14)? Og bør regime-klassificeringen opdateres hvert scan (60 sek) eller sjældnere for at undgå whipsaw?

---

## 2. Regime Detection — Supplerende Indikatorer

Ud over ADX bruger jeg EMA20/50 til retningsbestemmelse. Men ADX alene kan give false signals i choppy markeder.

**Spørgsmål:** Hvilke 1-2 supplerende indikatorer bør jeg tilføje til regime detection for at filtrere false regime shifts? Giv konkrete thresholds. F.eks. ATR expansion ratio, Bollinger Band width, eller volume profil? Og bør regime-skiftet kræve X consecutive candles over threshold før det aktiveres (hysterese)?

---

## 3. Grid Trading — Spacing og Levels

Min Grid Trader bruger: 10 levels, 0.5% spacing, auto-detect 24H high/low som range. Rebalancerer hvis pris drifter > 1.5% fra center. Deaktiverer ved ADX > 25.

**Spørgsmål:** Er 10 levels × 0.5% spacing optimalt for BTC/USD og ETH/USD på Kraken spot? Bør spacing være ATR-baseret i stedet for fixed procent? Hvad er den ideelle rebalancing-trigger (1.5% drift, eller bør det være baseret på antal fills)? Og hvad er minimum range-bredde i % hvor grid trading stadig er profitable efter Kraken's maker/taker fees (0.16%/0.26%)?

---

## 4. Grid Trading — Capital Allocation per Level

Jeg allokerer 30% af available balance til grid setup, fordelt ligeligt over alle levels.

**Spørgsmål:** Er lige fordeling over alle grid levels optimal, eller bør jeg bruge en bell-curve fordeling (mere kapital tæt på midten)? Hvad er den optimale total allocation til en grid bot som del af en multi-bot portefølje? Og bør grid ordrene være limit-only (maker fee 0.16%) eller er der scenarier hvor market orders giver mening?

---

## 5. Trend Following — Entry og Trailing Stop

Min Trend Follower bruger: EMA20/50 crossover (+3 confidence), MACD(12,26,9) confirmation (+2), volume spike 1.5x (+1), ADX > 35 bonus (+1). Min confidence = 4. Trailing stop = ATR × 2.0. Ingen fixed TP (profits run).

**Spørgsmål:** Er EMA 20/50 de bedste perioder for crypto trend following på 15-min candles? Bør trailing stop strammes gradvist (f.eks. starte ved ATR×3.0 og reducere til ATR×1.5 når profit > X%)? Hvad er den optimale "let profits run" mekanik — aldrig tage profit, eller partial exit ved milestones (f.eks. 50% ved 2R, resten trails)? Giv konkret pseudokode for en adaptiv trailing stop.

---

## 6. Coordinator Handoff — Præcis Timing

Når ADX krydser 25 opad, skal Grid bot lukke sine ordrer og Trend bot overtage. Men der er risiko for at Grid lukker for tidligt (ADX spike) eller Trend starter for sent.

**Spørgsmål:** Hvad er den optimale handoff-mekanik? Bør der være en overlap-periode hvor begge bots er aktive? Hvor mange candles skal ADX være over/under threshold før handoff udløses? Bør Grid bot lukke ALLE ordrer ved handoff, eller kun dem langt fra current price? Og hvad sker der med fills der sker under handoff — hvem ejer positionen?

---

## 7. Risk Engine — Correlation Control

Jeg har max exposure limits: Grid 30%, Trend 30%, MeanRev 20%, Volatility 10%. Per-coin limits: majors (BTC/ETH) 25%, altcoins 15%.

**Spørgsmål:** Bør jeg tilføje correlation-baseret risk? F.eks. hvis BTC og ETH begge er i TRENDING regime, bør combined exposure reduceres fordi de er korrelerede? Giv konkrete correlation thresholds og exposure reduction formler. Og bør kill switch (daily loss 5%, total loss 30%) gælde per-bot eller across hele systemet?

---

## 8. Backtesting — Metrics og Statistisk Signifikans

Jeg har ingen backtesting endnu. Strategierne er bygget på teori og parametre fra ChatGPT's analyse.

**Spørgsmål:** Hvad er minimum antal trades for at en backtest er statistisk signifikant per strategi-type? Hvilke metrics bør jeg tracke ud over Sharpe, profit factor og win rate? Giv mig en konkret liste af backtest-scenarier jeg SKAL teste (bull market, bear market, flash crash, low-vol sideways, high-vol sideways). Og hvad er acceptable minimum-værdier for hver metric før en strategi går live?

---

## 9. API Rate Limits — 4 Bots, 1 API Key

Kraken's rate limits: REST API har et "call counter" system (starter ved 15, decay 1/sec for spot). Jeg har 4 bots der alle bruger samme API key.

**Spørgsmål:** Hvad er den optimale scan-stagger strategi for 4 bots på samme Kraken API key? Bør jeg bruge WebSocket i stedet for REST polling for price data? Hvad er den præcise call counter cost for de endpoints jeg bruger (fetch_ohlcv, fetch_balance, create_order, fetch_open_orders)? Og bør jeg implementere en shared rate limiter (via coordinator filen) eller er per-bot stagger nok?

---

## 10. Futures vs Spot — Hvornår Skifte

Kraken futures har leverage, hedging muligheder og short-selling. Min Trend Follower og Volatility Trader kunne potentielt bruge futures.

**Spørgsmål:** For hvilke af mine 4 strategier giver Kraken futures mest mening? Hvad er de konkrete fordele og risici ved at køre Trend Follower på futures med 2-3x leverage vs spot? Bør Volatility Trader bruge futures for shorts (blow-off top), og hvad er funding rate implications? Giv en konkret anbefaling per strategi med begrundelse.

---

## 11. Coin Scanning — Hvilke Coins til Hvilken Strategi

Jeg handler: BTC/USD, ETH/USD, SOL/USD, AVAX/USD, LINK/USD, LTC/USD. Alle coins kører på alle strategier.

**Spørgsmål:** Bør jeg matche coins til strategier baseret på deres karakteristika? F.eks. BTC (lav vol, høj likviditet) → Grid, SOL (høj vol) → Volatility? Giv en konkret coin-strategi matrix med begrundelse. Og bør jeg tilføje volume/liquidity filters der dynamisk fjerner coins fra en strategi hvis de ikke passer til det aktuelle regime?

---

## 12. Kill Switch og Pause Regler

Min kill switch: daily loss ≥ 5% eller total loss ≥ 30%. Men der er ingen gradvis nedtrapning.

**Spørgsmål:** Bør der være mellemliggende trin før kill switch? F.eks. ved 3% daily loss: reducer position sizes med 50%, ved 4%: stop nye trades, ved 5%: luk alt? Giv konkrete thresholds og actions for en graduated risk-off mekanik. Og bør kill switch have en auto-reset (f.eks. efter 4 timer) eller kræve manual intervention?

---

## 13. Performance Tracking og Dynamisk Kapital-Allokering

Jeg tracerer trades i SQLite men har ingen rolling performance metrics eller dynamisk rebalancing.

**Spørgsmål:** Hvad er den optimale rolling window for performance evaluation (7 dage, 30 dage, 100 trades)? Bør kapital-allokering automatisk skifte til den bedst-performende bot? Giv en konkret formel for dynamisk allocation baseret på rolling Sharpe ratio per bot. Og hvad er minimum observation periode før allocation ændres (undgå overfitting til recent performance)?

---

## 14. Orderbook Analyse — Support/Resistance

Min KrakenAdapter har `fetch_order_book(depth=20)` men det bruges ikke aktivt i nogen strategi.

**Spørgsmål:** Hvordan kan jeg bruge orderbook data til at forbedre mine strategier? Giv konkret pseudokode for: (a) bid/ask imbalance signal (hvornår er det bullish/bearish), (b) detection af store limit ordrer (support/resistance walls), (c) optimal grid level placement baseret på orderbook clusters. Hvad er minimum orderbook depth jeg skal hente, og hvor ofte skal det opdateres?

---

## 15. Fee Optimization — Maker vs Taker

Kraken fees: maker 0.16%, taker 0.26%. Grid Trader bruger primært limit orders (maker), men Trend Follower bruger market orders (taker) for hurtig entry.

**Spørgsmål:** Hvad er break-even kalkulationen for each strategi givet disse fees? Bør Trend Follower bruge aggressive limit orders (limit price = current price ± 0.01%) i stedet for market orders for at spare 0.10% per trade? Hvad er risikoen for missed fills? Og ved hvilken trade-frekvens (per dag) bliver fee-forskellen material for total performance?

---

## 16. Mean Reversion — Crash Protection

Min MeanReverter har `max_entries_per_crash: 2` og bruger BB(20,2) + RSI(14) med oversold=25, overbought=75.

**Spørgsmål:** Er RSI 25/75 for aggressivt eller for konservativt for crypto mean reversion? Bør BB multiplier være 2.0 eller 2.5 for crypto's højere volatilitet? Hvordan skelner jeg mellem en mean-reversion opportunity og starten på en ny trend (regime shift)? Giv konkret logik for "dette er IKKE mean reversion, det er et trend break" — f.eks. volume explosion + ADX acceleration combo.

---

## 17. Statistical Arbitrage — Ny Strategi

ChatGPT nævnte coin-pair trading (f.eks. BTC/ETH ratio). Jeg har ikke implementeret dette endnu.

**Spørgsmål:** Er statistical arbitrage realistisk på Kraken spot med mine 6 coins? Hvilke par har historisk højest mean-reversion (cointegration)? Giv konkret implementering: (a) hvordan beregnes spread/ratio, (b) hvad er entry/exit z-score thresholds, (c) position sizing for pair trades, (d) maximum holding period. Og hvad er minimum kapital for at stat arb er profitable efter fees?

---

## 18. Volatility Trader — Flash Crash Parametre

Min Volatility Trader trigger: price drop ≥ 3% i 4 candles (1H), ATR expansion ≥ 2.5x, bounce target 1.5%, max hold 30 min, cooldown 15 min.

**Spørgsmål:** Er 3% drop threshold korrekt for BTC vs altcoins? (Altcoins dropper oftere 3%+). Bør bounce target (1.5%) og max hold (30 min) variere per coin? Hvad er den historiske success rate for "buy the dip" efter 3%+ drops på crypto? Og bør jeg tilføje et "continuation filter" der IKKE køber dippen hvis momentum stadig er negativ (f.eks. selling volume accelererer)?

---

## 19. Multi-Timeframe Analyse

Alle mine strategier scanner på én timeframe (primært 15-min). Regime detection bruger 1H.

**Spørgsmål:** Bør mine strategier bruge multi-timeframe confirmation? F.eks. Grid Trader scanner 15-min men confirmer range på 4H? Trend Follower entry på 15-min men trend confirmation på 1H og 4H? Giv konkret implementation: hvilke timeframes per strategi, og hvordan kombineres signals fra forskellige timeframes (alle skal agree, eller majority vote)?

---

## 20. Position Sizing — Kelly Criterion vs Fixed

Jeg bruger confidence-baseret position sizing: confidence 4 = 25% af max, confidence 10 = 100% af max. Max per major = 25%, max per altcoin = 15%.

**Spørgsmål:** Bør jeg bruge Kelly Criterion i stedet for min confidence multiplier tabel? Giv den præcise formel tilpasset crypto (med adjustments for fat tails). Hvad er "half Kelly" og hvornår bør det bruges? Og hvordan integrerer jeg Kelly med min existing confidence score — f.eks. Kelly beregnet fra historisk win rate × confidence multiplier?
