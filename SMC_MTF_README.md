# SMC MTF Sniper — H4 → H1 → M15 → M5 → M1

A TradingView indicator (Pine v5) that implements a multi-timeframe smart-money
sequence and only prints a **BUY / SELL** signal when every stage lines up.

File: `smc_mtf_sniper.pine`

---

## 1) Stage sequence

| TF | Role | What the script computes |
|---|---|---|
| **H4** | Bias + structure | Confirmed pivots + break of structure → `BULL / BEAR / FLAT` |
| **H1** | SNR / MSNR + POI | Minor S/R (SNR) and major S/R (MSNR), plus POI zones (order block preceding an impulsive move) |
| **M15** | CRT range + BSL/SSL | CRT range = previous M15 candle (or swing pivots). `BSL` = range high, `SSL` = range low, then **liquidity sweep** detection |
| **M5** | MSS / CHoCH + CISD / TCISD | Break of the last M5 swing in the sweep direction (MSS / CHoCH) + break of the delivery-run open (CISD); **TCISD** = full engulf of the delivery leg |
| **M1** | Entry + retest | Requires price to return and retest the broken level, then a confirmation candle |

**Full long condition:** `H4 bullish` → `price at an H1 demand POI` → `SSL swept on M15 with a
close back inside` → `bullish MSS/CISD with displacement on M5` → `retest + confirmation candle on M1`.
Shorts are the exact mirror.

---

## 2) Stop loss and take profit

- **SL** — anchored per the `SL anchor` setting:
  - `Sweep extreme` — behind the furthest extension of the sweep
  - `M5 structure` — behind the M5 structural low/high
  - `Furthest of both` (default) — whichever is further
  - An `SL buffer × ATR` margin is added on top.
- **TP** — nearest opposing liquidity among `BSL/SSL (M15)`, `SNR (H1)`, `MSNR (H1)`,
  `H4 swing`, and `previous day high/low`, subject to `Minimum R:R`.
  If no level qualifies, `Fallback R:R` is used instead.

---

## 3) Optional filters

- **Volume** — `volume > SMA(volume) × mult`
- **CVD** — rolling signed-volume proxy from where each candle closes within its range
  (`math.sum` over the last N bars); longs need positive delta, shorts negative.
  It is an approximation that avoids intrabar data, which is why it does not repaint.
- **Sessions** — London / New York with a configurable timezone.

All three are **off by default** — enable them in the settings when you want them.

---

## 4) Non-repainting

- Every `request.security` call uses `lookahead_off`, and its value is **latched only when the
  higher-timeframe bar closes** (the `f_hold` helper), so historical values never change.
- `Confirm on bar close` is enabled by default: signals resolve only at bar close.
- No future data is referenced anywhere.
- **Stated plainly:** pivots need `N` bars after them to confirm. That is **intentional lag**,
  not repainting. Lowering `pivot length` confirms faster but adds noise.

---

## 5) Alerts

From the TradingView alert dialog:

- `SMC BUY` / `SMC SELL` / `SMC ANY` — via `alertcondition`.
- A dynamic `alert()` message carrying direction, symbol, timeframe, and
  **Entry / SL / TP / R:R** — pick "Any alert() function call" when creating the alert.

---

## 6) How to use

1. TradingView → Pine Editor → paste `smc_mtf_sniper.pine` → **Add to chart**.
2. **Run it on an M1 chart** (M5 at most). The dashboard shows `TOO HIGH` if the chart
   timeframe is above the configured M5 timeframe.
3. Adjust the timeframes in the `1 · Timeframes` group for a different stack
   (e.g. faster scalping: 60 / 15 / 5 / 1 on an M1 chart).
4. Watch the `STAGE` panel in the top right: it shows each stage per direction
   (`SWEPT` → `SHIFTED` → the retest level being waited on).

### Quick tuning
| Symptom | What to change |
|---|---|
| Too few signals | Lower `pivot length`, enable `Allow signals on neutral H4 bias`, turn off `Require TCISD`, or set `Confirmation required = MSS or CISD` |
| Too many / weak signals | Use `MSS and CISD`, raise `Displacement ATR multiple`, enable the session and volume filters |
| Stops hit too often | Raise `SL buffer` and use `Furthest of both` |

---

## 7) Important note

This is an analysis indicator, not an execution system, and it was **not compiled in the Pine
editor during this session** (no Pine compiler exists outside TradingView). If anything errors
on paste, send the message and line number and it will be fixed. Backtest and forward-test on
your own symbol and timeframe before relying on it.
