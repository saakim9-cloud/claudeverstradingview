"""Python ports of the three Pine strategies in the repo (default inputs)."""
import math
import numpy as np
import pandas as pd
from engine import Engine


def atr_rma(df, n=14):
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    tr = np.empty(len(df))
    tr[0] = h[0] - l[0]
    for i in range(1, len(df)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(len(df), np.nan)
    if len(df) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(df)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def pivots(high, low, L):
    """Pine-like ta.pivothigh/ta.pivotlow(L, L): value known at bar i for center i-L."""
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(2 * L, n):
        c = i - L
        hv = high[c]
        if hv > high[c - L:c].max() and hv >= high[c + 1:i + 1].max():
            ph[i] = hv
        lv = low[c]
        if lv < low[c - L:c].min() and lv <= low[c + 1:i + 1].min():
            pl[i] = lv
    return ph, pl


def htf_events(df, rule):
    """For each chart bar, return (isNewHTF, isA, isV, level, levelTime) like the Pine msnr()
    with lookahead_on and [1]/[2] offsets (confirmed HTF candles only)."""
    htf = df.resample(rule, label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    hstart = htf.index
    idx = np.searchsorted(hstart.values, df.index.values, side='right') - 1
    o, c = htf['open'].values, htf['close'].values
    n = len(df)
    new = np.zeros(n, bool)
    isA = np.zeros(n, bool)
    isV = np.zeros(n, bool)
    lvl = np.full(n, np.nan)
    lt = np.empty(n, dtype=object)
    prev = -1
    for i in range(n):
        j = idx[i]
        if j != prev and prev != -1 and j >= 2:
            new[i] = True
            isA[i] = c[j - 2] > o[j - 2] and c[j - 1] < o[j - 1]
            isV[i] = c[j - 2] < o[j - 2] and c[j - 1] > o[j - 1]
            lvl[i] = c[j - 2]
            lt[i] = hstart[j - 2]
        prev = j
    return new, isA, isV, lvl, lt


def qty_for(eng, price, entry, sl, risk_pct=1.0):
    r = abs(entry - sl)
    return (eng.equity(price) * risk_pct / 100.0) / r if r > 0 else 0.0


# ════════════════════════════════════════════════════════════════════════════
#  MSNR strategy  (msnr_strategy.pine)
# ════════════════════════════════════════════════════════════════════════════
def run_msnr(df, tf1='4h', tf2='1h', use_qm=True, qm_len=5, max_lv=8, sl_mult=0.5,
             tp_mode='next', rr_fixed=2.0, rr_min=1.5, use_sess=True, comm=0.02):
    eng = Engine(comm_pct=comm)
    O, H, L, C = (df[k].values for k in ('open', 'high', 'low', 'close'))
    hrs = df.index.hour + df.index.minute / 60.0
    atr = atr_rma(df)
    n1 = htf_events(df, tf1)
    n2 = htf_events(df, tf2)
    ph, pl = pivots(H, L, qm_len)
    levels = []  # dict(price, isRes, src, born)
    swP, swHi = [], []

    def add(price, is_res, src, i):
        if any(l['src'] == src and l['price'] == price for l in levels):
            return
        levels.append(dict(price=price, isRes=is_res, src=src, born=i))
        cnt = 0
        for k in range(len(levels) - 1, -1, -1):
            if levels[k]['src'] == src:
                cnt += 1
                if cnt > max_lv:
                    levels.pop(k)

    def push_swing(p, hi):
        if swHi and swHi[-1] == hi:
            if (hi and p > swP[-1]) or (not hi and p < swP[-1]):
                swP[-1] = p
        else:
            swP.append(p)
            swHi.append(hi)
            if len(swP) > 6:
                swP.pop(0)
                swHi.pop(0)

    for i in range(len(df)):
        eng.process_bar(i, O[i], H[i], L[i], C[i])
        for (new, a, v, lv, lt), src in ((n1, 'TF1'), (n2, 'TF2')):
            if new[i] and (a[i] or v[i]):
                add(lv[i], bool(a[i]), src, i)
        if not np.isnan(ph[i]):
            push_swing(ph[i], True)
        if not np.isnan(pl[i]):
            push_swing(pl[i], False)
        if use_qm and (not np.isnan(ph[i]) or not np.isnan(pl[i])) and len(swP) >= 4:
            q1, q2, q3, q4 = swP[-4:]
            h1 = swHi[-4]
            if h1 and q3 > q1 and q4 < q2 and C[i] < q1:
                add(q1, True, 'QM', i)
            if (not h1) and q3 < q1 and q4 > q2 and C[i] > q1:
                add(q1, False, 'QM', i)
        if np.isnan(atr[i]):
            continue
        in_ses = (not use_sess) or (8 <= hrs[i] < 12) or (13 <= hrs[i] < 17)
        sig = None
        for k in range(len(levels) - 1, -1, -1):
            l = levels[k]
            if i <= l['born']:
                continue
            broken = C[i] > l['price'] if l['isRes'] else C[i] < l['price']
            touched = H[i] >= l['price'] if l['isRes'] else L[i] <= l['price']
            if broken:
                levels.pop(k)
            elif touched:
                if sig is None:
                    sig = l
                levels.pop(k)
        if sig is not None and eng.position_size == 0 and in_ses:
            sell = sig['isRes']
            stop = sig['price'] + atr[i] * sl_mult if sell else sig['price'] - atr[i] * sl_mult
            risk = abs(C[i] - stop)
            tgt = None
            if tp_mode == 'fixed':
                tgt = C[i] - risk * rr_fixed if sell else C[i] + risk * rr_fixed
            else:
                cands = [l['price'] for l in levels if (sell and not l['isRes'] and l['price'] < C[i]) or
                         ((not sell) and l['isRes'] and l['price'] > C[i])]
                if cands:
                    nt = max(cands) if sell else min(cands)
                    if abs(nt - C[i]) >= risk * rr_min:
                        tgt = nt
            q = qty_for(eng, C[i], C[i], stop)
            if tgt is not None and q > 0:
                oid = 'Sell' if sell else 'Buy'
                eng.entry(oid, -1 if sell else 1, q)
                eng.exit(oid, 'X', stop=stop, limit=tgt)
    return eng


# ════════════════════════════════════════════════════════════════════════════
#  ICT Pre-NY sweep + MSS + FVG  (preny_sweep_strategy.pine)
# ════════════════════════════════════════════════════════════════════════════
def run_ict(df, pv_len=2, entry_mode='edge', min_fvg_atr=0.05, max_trades=1, sl_buf=0.1,
            tp_mode='partial', rr_fixed=3.0, min_rr=1.5, range_h=(8, 9), trade_h=(9, 12), hold_h=(8, 16),
            comm=0.02, bias=None):
    eng = Engine(comm_pct=comm)
    O, H, L, C = (df[k].values for k in ('open', 'high', 'low', 'close'))
    ny = df.index.tz_convert('America/New_York')
    hrs = ny.hour + ny.minute / 60.0
    atr = atr_rma(df)
    ph, pl = pivots(H, L, pv_len)
    n = len(df)
    in_range = (hrs >= range_h[0]) & (hrs < range_h[1])
    in_trade = (hrs >= trade_h[0]) & (hrs < trade_h[1])
    in_hold = (hrs >= hold_h[0]) & (hrs < hold_h[1])

    S = dict(rHi=None, rLo=None, ready=False, trades=0)
    last = dict(PH=None, PL=None)

    def reset_side():
        return dict(swept=False, ext=None, bar=None, mss=None, mssOk=False, top=None, bot=None,
                    placed=False, sl=None, tp=None)

    sh, lg = reset_side(), reset_side()
    prev_pos = 0.0
    for i in range(n):
        eng.process_bar(i, O[i], H[i], L[i], C[i])
        r_start = in_range[i] and (i == 0 or not in_range[i - 1])
        r_end = (not in_range[i]) and i > 0 and in_range[i - 1]
        if r_start:
            S.update(rHi=H[i], rLo=L[i], ready=False, trades=0)
            sh, lg = reset_side(), reset_side()
            eng.cancel('Short')
            eng.cancel('Long')
        elif in_range[i] and S['rHi'] is not None:
            S['rHi'] = max(S['rHi'], H[i])
            S['rLo'] = min(S['rLo'], L[i])
        if r_end and S['rHi'] is not None:
            S['ready'] = True
        pos = eng.position_size
        if pos != 0 and prev_pos == 0:
            S['trades'] += 1
        # (an entry already cancels the other pending entry inside the engine)
        a = atr[i]
        active = S['ready'] and in_trade[i] and S['trades'] < max_trades and not np.isnan(a)
        bear_fvg = i >= 2 and H[i] < L[i - 2] and (L[i - 2] - H[i]) >= a * min_fvg_atr
        bull_fvg = i >= 2 and L[i] > H[i - 2] and (L[i] - H[i - 2]) >= a * min_fvg_atr
        rHi, rLo = S['rHi'], S['rLo']
        if active:
            # SHORT
            s = sh
            if not s['placed']:
                if not s['swept'] and H[i] > rHi:
                    s.update(swept=True, ext=H[i], bar=i, mss=last['PL'])
                elif s['swept'] and not s['mssOk']:
                    s['ext'] = max(s['ext'], H[i])
                if s['swept'] and not s['mssOk'] and not np.isnan(pl[i]) and i - pv_len <= s['bar']:
                    s['mss'] = pl[i]
                if s['swept'] and bear_fvg and i - 1 >= s['bar']:
                    s['top'], s['bot'] = L[i - 2], H[i]
                if s['swept'] and not s['mssOk'] and s['mss'] is not None and C[i] < s['mss']:
                    s['mssOk'] = True
                bias_ok = bias is None or bias[i] == -1
                if s['mssOk'] and s['top'] is not None and eng.position_size == 0 and bias_ok:
                    entry = s['bot'] if entry_mode == 'edge' else (s['top'] + s['bot']) / 2
                    sl = s['ext'] + a * sl_buf
                    tp = entry - (sl - entry) * rr_fixed if tp_mode == 'fixed' else rLo
                    rr = (entry - tp) / (sl - entry) if sl > entry else 0
                    if C[i] < entry and tp < entry and rr >= min_rr:
                        q = qty_for(eng, C[i], entry, sl)
                        if q > 0:
                            eng.entry('Short', -1, q, limit=entry)
                            mid = (rHi + rLo) / 2
                            if tp_mode == 'partial' and tp < mid < entry:
                                eng.exit('Short', 'TP1', stop=sl, limit=mid, pct=50)
                                eng.exit('Short', 'TP2', stop=sl, limit=tp, pct=100)
                            else:
                                eng.exit('Short', 'X', stop=sl, limit=tp)
                            s.update(placed=True, sl=sl, tp=tp)
            # LONG
            s = lg
            if not s['placed']:
                if not s['swept'] and L[i] < rLo:
                    s.update(swept=True, ext=L[i], bar=i, mss=last['PH'])
                elif s['swept'] and not s['mssOk']:
                    s['ext'] = min(s['ext'], L[i])
                if s['swept'] and not s['mssOk'] and not np.isnan(ph[i]) and i - pv_len <= s['bar']:
                    s['mss'] = ph[i]
                if s['swept'] and bull_fvg and i - 1 >= s['bar']:
                    s['top'], s['bot'] = L[i], H[i - 2]
                if s['swept'] and not s['mssOk'] and s['mss'] is not None and C[i] > s['mss']:
                    s['mssOk'] = True
                bias_ok = bias is None or bias[i] == 1
                if s['mssOk'] and s['top'] is not None and eng.position_size == 0 and bias_ok:
                    entry = s['top'] if entry_mode == 'edge' else (s['top'] + s['bot']) / 2
                    sl = s['ext'] - a * sl_buf
                    tp = entry + (entry - sl) * rr_fixed if tp_mode == 'fixed' else rHi
                    rr = (tp - entry) / (entry - sl) if entry > sl else 0
                    if C[i] > entry and tp > entry and rr >= min_rr:
                        q = qty_for(eng, C[i], entry, sl)
                        if q > 0:
                            eng.entry('Long', 1, q, limit=entry)
                            mid = (rHi + rLo) / 2
                            if tp_mode == 'partial' and entry < mid < tp:
                                eng.exit('Long', 'TP1', stop=sl, limit=mid, pct=50)
                                eng.exit('Long', 'TP2', stop=sl, limit=tp, pct=100)
                            else:
                                eng.exit('Long', 'X', stop=sl, limit=tp)
                            s.update(placed=True, sl=sl, tp=tp)
        if not np.isnan(ph[i]):
            last['PH'] = ph[i]
        if not np.isnan(pl[i]):
            last['PL'] = pl[i]
        if eng.position_size == 0:
            if sh['placed'] and (L[i] <= sh['tp'] or H[i] >= sh['sl']):
                eng.cancel('Short')
            if lg['placed'] and (H[i] >= lg['tp'] or L[i] <= lg['sl']):
                eng.cancel('Long')
            if not in_trade[i]:
                eng.cancel('Short')
                eng.cancel('Long')
        if eng.position_size != 0 and not in_hold[i]:
            eng.close_all()
        prev_pos = eng.position_size
    return eng


# ════════════════════════════════════════════════════════════════════════════
#  SMC classic BOS/CHoCH + OB  (smc_ob_strategy.pine)
# ════════════════════════════════════════════════════════════════════════════
def run_smc(df, sw_len=5, sig_mode='both', ob_mode='wick', need_fvg=False, max_look=150, max_pend=40,
            sl_buf=0.1, rr=2.5, use_sess=False, comm=0.02, bias=None):
    eng = Engine(comm_pct=comm)
    O, H, L, C = (df[k].values for k in ('open', 'high', 'low', 'close'))
    ny = df.index.tz_convert('America/New_York')
    hrs = ny.hour + ny.minute / 60.0
    atr = atr_rma(df)
    ph, pl = pivots(H, L, sw_len)
    shP = shB = slP = slB = None
    shBroken = slBroken = True
    trend = 0
    pend = dict(dir=0, bar=None, sl=None)
    for i in range(len(df)):
        eng.process_bar(i, O[i], H[i], L[i], C[i])
        in_ses = (not use_sess) or (3 <= hrs[i] < 6) or (8.5 <= hrs[i] < 11.5)
        if not np.isnan(ph[i]):
            shP, shB, shBroken = ph[i], i - sw_len, False
        if not np.isnan(pl[i]):
            slP, slB, slBroken = pl[i], i - sw_len, False
        a = atr[i]
        bull = (not shBroken) and C[i] > shP
        bear = (not slBroken) and C[i] < slP
        for side in ((1,) if bull else ()) + ((-1,) if bear else ()):
            if side == 1:
                choch = trend == -1
                trend = 1
                shBroken = True
                if pend['dir'] == -1:
                    eng.cancel('Short')
                    pend['dir'] = 0
                span = min(i - shB, max_look)
                o_off, o_val = 0, L[i]
                for k in range(0, span + 1):
                    if L[i - k] < o_val:
                        o_val, o_off = L[i - k], k
                ob = None
                for k in range(o_off, min(o_off + 10, max_look) + 1):
                    if i - k >= 0 and C[i - k] < O[i - k]:
                        ob = k
                        break
                has_fvg = any(L[i - k] > H[i - k - 2] for k in range(0, o_off - 1)) if need_fvg and o_off >= 2 else False
            else:
                choch = trend == 1
                trend = -1
                slBroken = True
                if pend['dir'] == 1:
                    eng.cancel('Long')
                    pend['dir'] = 0
                span = min(i - slB, max_look)
                o_off, o_val = 0, H[i]
                for k in range(0, span + 1):
                    if H[i - k] > o_val:
                        o_val, o_off = H[i - k], k
                ob = None
                for k in range(o_off, min(o_off + 10, max_look) + 1):
                    if i - k >= 0 and C[i - k] > O[i - k]:
                        ob = k
                        break
                has_fvg = any(H[i - k] < L[i - k - 2] for k in range(0, o_off - 1)) if need_fvg and o_off >= 2 else False
            wanted = sig_mode == 'both' or (sig_mode == 'bos' and not choch) or (sig_mode == 'choch' and choch)
            bias_ok = bias is None or bias[i] == side
            if ob is None or not wanted or not in_ses or np.isnan(a) or not bias_ok or (need_fvg and not has_fvg):
                continue
            if eng.position_size != 0:
                continue
            j = i - ob
            top = H[j] if ob_mode == 'wick' else max(O[j], C[j])
            bot = L[j] if ob_mode == 'wick' else min(O[j], C[j])
            if side == 1:
                entry, sl = top, bot - a * sl_buf
                risk = entry - sl
                ok = C[i] > entry and risk > 0
                tp = entry + risk * rr
            else:
                entry, sl = bot, top + a * sl_buf
                risk = sl - entry
                ok = C[i] < entry and risk > 0
                tp = entry - risk * rr
            if ok:
                q = qty_for(eng, C[i], entry, sl)
                oid = 'Long' if side == 1 else 'Short'
                eng.cancel(oid)
                eng.entry(oid, side, q, limit=entry)
                eng.exit(oid, 'X', stop=sl, limit=tp)
                pend.update(dir=side, bar=i, sl=sl)
        if eng.position_size != 0:
            pend['dir'] = 0
        elif pend['dir'] != 0:
            expired = i - pend['bar'] > max_pend
            invalid = C[i] < pend['sl'] if pend['dir'] == 1 else C[i] > pend['sl']
            if expired or invalid or (use_sess and not in_ses):
                eng.cancel('Long' if pend['dir'] == 1 else 'Short')
                pend['dir'] = 0
    return eng
