# KrakenMarginBot — Changelog

## [2026-03-15] Margin Ombygning (Runde 6)

Ombygning af KrakenBots (spot) til Kraken Spot Margin trading.

### Tilføjet
- **Margin mode support** i `kraken_adapter.py` — `mode: spot_margin`, `margin_mode: cross/isolated`, `leverage: 2-5x`
- **`_margin_params()`** hjælpemetode — centraliserer leverage params på alle orders
- **`get_account_balance()`** henter margin equity via `private_post_tradebalance()` — returnerer equity, margin_used, free_margin, unrealized_pl, margin_level
- **`get_margin_status()`** ny metode til margin-specifik status
- **Margin-aware risk manager** — `max_leverage` cap, strammere defaults (daily 3%, total 15%), `margin_call_warning_pct`
- **`check_margin_health()`** i manager.py — advarer ved lav margin level
- **Margin call detection** i `_scan_cycle()` — Telegram warning ved margin < 150%
- **Margin info i Telegram** — startup besked viser leverage/mode, `/balance` viser margin details
- **4 bot configs** på VPS: KG1-M (Grid), KT1-M (Trend), KM1-M (MeanRev), KV1-M (Volatility)
- **4 Telegram bots**: @CB_MG1_bot, @CB_MT1_bot, @CB_MM1_bot, @CB_MV1_bot
- **Docker compose** med shared coordinator volume
- **`CHANGELOG.md`** (denne fil)

### Ændret
- `kraken_adapter.py` — leverage params på alle 10 order-steder (market, limit, SL, TP, batch, close, update)
- `manager.py` — leverage for `spot_margin` mode, position sizing med leverage-adjusted risk
- `coordinator.py` — `update_equity()` accepterer margin_info med unrealized P/L
- `main_kraken.py` — margin status ved startup, margin call detection, exposure tracking med fill_price
- `grid_trader.py` — range detection bruger ±5% fra current price i stedet for 24h high/low
- `config.example.yaml` — nye margin-specifikke keys

### Filer berørt
| Fil | Type ændring |
|-----|-------------|
| `src/exchange/kraken_adapter.py` | Margin params, balance, margin status |
| `src/risk/manager.py` | Leverage, strammere limits, margin health check |
| `src/risk/coordinator.py` | Margin equity tracking |
| `main_kraken.py` | Margin detection, startup logging, Telegram |
| `src/strategies/grid_trader.py` | Range detection fix |
| `config.example.yaml` | Margin config keys |
| `docker-compose.yml` | 4 margin bot services |
| `Dockerfile` | Ny |

---

## [2026-03-14] Runde 4 — Execution Safety & Reliability

### Tilføjet
- **Liquidity Guard** — tjekker orderbook depth (5x position) inden trade
- **Strategy-specific spread limits** — Grid 0.15%, Trend/Volatility 0.50%
- **Stale data guard** — skipper scan hvis data ældre end max_age
- **Partial fill tracking** — incremental fills med filled_size/original_size
- **Order timeout** — auto-cancel efter 60 min
- **Multi-tier circuit breaker** — 3%→5min, 5%→10min, 8%→30min
- **Per-coin cross-bot exposure** — max 25% per coin via shared state

### Filer berørt
- `src/executor/trade_executor.py`
- `src/executor/order_manager.py`
- `main_kraken.py`
- `src/risk/coordinator.py`
- `config.example.yaml`

---

## [2026-03-14] Runde 5 — Critical Tweaks & Enhancements

### Tilføjet
- **Full exposure integration** — partial fills opdaterer coin_exposure
- **Global risk kill-switch** — stopper alle bots ved 10% portfolio drawdown
- **Adaptive stale data age** — per-timeframe (1m→10s, 15m→30s, 1h→120s)
- **Liquidity Guard soft fallback** — reducerer size 50% ved API fail
- **Circuit breaker monitoring** — SQLite logging af triggers
- **Cross-strategy priority queue** — højere priority vinder coin lock
- **Order slicing** — max 25% af orderbook per slice, max 4 slices

### Filer berørt
- `src/executor/trade_executor.py`
- `src/executor/order_manager.py`
- `main_kraken.py`
- `src/risk/coordinator.py`
- `config.example.yaml`
