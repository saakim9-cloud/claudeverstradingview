# TradingView Pine Scripts

Pine Script v5 tools for TradingView.

## `market_structure_bos_choch.pine` — Market Structure (BOS / CHoCH)

Detects and labels Smart Money market structure breaks.

- **BOS — Break of Structure:** price takes out the last swing level *in the
  direction of the current trend*. Continuation.
- **CHoCH — Change of Character:** price takes out the last swing level *against*
  the current trend, flipping it. First sign of a reversal.

How it works:

1. Swing highs/lows are confirmed with a pivot lookback (`Swing Pivot Length`);
   a pivot needs N bars on each side before it counts.
2. The most recent unbroken swing high and swing low are held as pending levels.
3. When price trades (or closes, depending on `Break Confirmation`) beyond one of
   them, the level is marked broken, a line is drawn from the swing to the break
   bar, and the break is tagged `BOS` or `CHoCH` based on the prior trend.
4. The trend flips to the side of the break, so the next break is classified
   against the updated state.

Inputs worth knowing:

| Input | Effect |
| --- | --- |
| `Swing Pivot Length` | Higher = fewer, more significant structure points. 10 is a sane default; 5 for scalping, 20+ for HTF bias. |
| `Break Confirmation` | `Close` requires a candle body beyond the level (fewer false breaks). `Wick` triggers on any touch beyond. |
| `Show Internal Structure` | Adds a second, shorter-pivot structure stream for the minor legs inside each swing. |
| `Show Pending Swing Levels` | Plots the swing high/low that has not been taken out yet — the levels to watch. |
| `Color Bars By Structure Trend` | Tints candles with the current structure trend. |

Five `alertcondition`s are exposed: bullish/bearish BOS, bullish/bearish CHoCH,
and a combined "any swing structure break".

## `gold_scalping_strategy.pine` — Gold Scalping Strategy (XAUUSD)

EMA 9/21 crossover strategy filtered by RSI and Bollinger mid-band, restricted to
the London and New York sessions, with ATR-based stop loss and take profit.
