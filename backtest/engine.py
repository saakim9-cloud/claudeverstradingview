"""Minimal bar-by-bar backtest engine that mimics TradingView's broker emulator.

- Strategy logic runs at bar close; orders placed then are live from the next bar.
- Intrabar path: open->high->low->close if open is closer to high, else open->low->high->close.
- Market orders fill at next open (+slippage); limit orders at limit (or open if gapped through);
  stops at stop (or open if gapped) +slippage.
- Commission: percent of notional per side.
"""
import math


class Engine:
    def __init__(self, capital=10000.0, comm_pct=0.02, slip=0.02):
        self.capital = capital
        self.cash = capital          # realised equity
        self.comm = comm_pct / 100.0
        self.slip = slip
        self.pos = None              # dict(dir, qty, entry, exits=[...], id, bar)
        self.pending = {}            # id -> dict(dir, qty, type: 'market'|'limit', price)
        self.exits = {}              # entry id -> list of dict(name, pct, stop, limit)
        self.trades = []             # closed full positions
        self.eq_curve = []
        self.peak = capital
        self.max_dd = 0.0
        self._cur_trade = None

    # ── order API (called at bar close) ─────────────────────────────────────
    def entry(self, oid, direction, qty, limit=None):
        if not (self.pos and self.pos['id'] == oid):
            self.exits.pop(oid, None)
        self.pending[oid] = dict(dir=direction, qty=qty, type='limit' if limit is not None else 'market',
                                 price=limit)

    def exit(self, oid, name, stop=None, limit=None, pct=100.0):
        lst = self.exits.setdefault(oid, [])
        for e in lst:
            if e['name'] == name:
                e.update(stop=stop, limit=limit, pct=pct)
                return
        lst.append(dict(name=name, stop=stop, limit=limit, pct=pct, done=False))

    def cancel(self, oid):
        self.pending.pop(oid, None)

    def close_all(self):
        if self.pos:
            self.pending['__close__'] = dict(dir=0, qty=0, type='close', price=None)

    @property
    def position_size(self):
        if not self.pos:
            return 0.0
        return self.pos['qty'] * self.pos['dir']

    def equity(self, price):
        if not self.pos:
            return self.cash
        return self.cash + (price - self.pos['entry']) * self.pos['qty'] * self.pos['dir']

    # ── internals ───────────────────────────────────────────────────────────
    def _open(self, oid, d, qty, price, bar):
        self.cash -= price * qty * self.comm
        self.pos = dict(id=oid, dir=d, qty=qty, entry=price, bar=bar)
        self._cur_trade = dict(id=oid, dir=d, entry=price, qty0=qty, pnl=-price * qty * self.comm,
                               bar_in=bar, bar_out=None)
        # an entry cancels any other pending entry (pyramiding = 0, no reversal wanted here)
        for k in list(self.pending):
            if k != '__close__':
                self.pending.pop(k)
        for e in self.exits.get(oid, []):
            e['done'] = False
            e['qty'] = None

    def _close_qty(self, qty, price, bar):
        p = self.pos
        pnl = (price - p['entry']) * qty * p['dir'] - price * qty * self.comm
        self.cash += pnl
        self._cur_trade['pnl'] += pnl + 0  # commission on exit already inside pnl
        p['qty'] -= qty
        if p['qty'] <= 1e-12:
            self._cur_trade['bar_out'] = bar
            self._cur_trade['exit'] = price
            self.trades.append(self._cur_trade)
            self.exits.pop(p['id'], None)
            self.pos = None
            self._cur_trade = None

    def _exit_qtys(self):
        """Pine-like allocation: exits in declaration order take pct of the ORIGINAL qty."""
        p = self.pos
        lst = self.exits.get(p['id'], [])
        q0 = self._cur_trade['qty0']
        for e in lst:
            if e.get('qty') is None:
                e['qty'] = q0 * e['pct'] / 100.0
        return lst

    def process_bar(self, i, o, h, l, c):
        # path points
        path = [o, h, l, c] if abs(h - o) < abs(l - o) else [o, l, h, c]
        # market / close orders at open
        if '__close__' in self.pending:
            self.pending.pop('__close__')
            if self.pos:
                px = o - self.slip * self.pos['dir']
                self._close_qty(self.pos['qty'], px, i)
        for oid, od in list(self.pending.items()):
            if od['type'] == 'market' and not self.pos:
                px = o + self.slip * od['dir']
                self.pending.pop(oid)
                self._open(oid, od['dir'], od['qty'], px, i)
        # walk segments
        for s in range(3):
            a, b = path[s], path[s + 1]
            self._walk(i, a, b, first=(s == 0))
        m = self.equity(c)
        self.eq_curve.append(m)
        self.peak = max(self.peak, m)
        self.max_dd = max(self.max_dd, self.peak - m)

    def _walk(self, i, a, b, first):
        up = b > a
        cur = a
        while True:
            at_open = first and cur == a
            lo, hi = min(cur, b), max(cur, b)
            ev = []
            if not self.pos:
                for oid, od in self.pending.items():
                    if od['type'] != 'limit':
                        continue
                    L = od['price']
                    if od['dir'] == 1:
                        if at_open and cur <= L:
                            ev.append((0.0, 1, 'entry', oid, cur))
                        elif not up and lo <= L <= hi:
                            ev.append((cur - L, 1, 'entry', oid, L))
                    else:
                        if at_open and cur >= L:
                            ev.append((0.0, 1, 'entry', oid, cur))
                        elif up and lo <= L <= hi:
                            ev.append((L - cur, 1, 'entry', oid, L))
            else:
                d = self.pos['dir']
                for e in self._exit_qtys():
                    if e['done']:
                        continue
                    st, lm = e['stop'], e['limit']
                    if st is not None:
                        if d == 1:
                            if at_open and cur <= st:
                                ev.append((0.0, 0, 'stop', e, cur))
                            elif not up and lo <= st <= hi:
                                ev.append((cur - st, 0, 'stop', e, st))
                        else:
                            if at_open and cur >= st:
                                ev.append((0.0, 0, 'stop', e, cur))
                            elif up and lo <= st <= hi:
                                ev.append((st - cur, 0, 'stop', e, st))
                    if lm is not None:
                        if d == 1:
                            if at_open and cur >= lm:
                                ev.append((0.0, 1, 'limit', e, cur))
                            elif up and lo <= lm <= hi:
                                ev.append((lm - cur, 1, 'limit', e, lm))
                        else:
                            if at_open and cur <= lm:
                                ev.append((0.0, 1, 'limit', e, cur))
                            elif not up and lo <= lm <= hi:
                                ev.append((cur - lm, 1, 'limit', e, lm))
            if not ev:
                return
            ev.sort(key=lambda x: (x[0], x[1]))
            _, _, kind, ref, px = ev[0]
            if kind == 'entry':
                od = self.pending[ref]
                self._open(ref, od['dir'], od['qty'], px, i)
            elif kind == 'stop':
                self._close_qty(self.pos['qty'], px - self.slip * self.pos['dir'], i)
            else:
                ref['done'] = True
                self._close_qty(min(ref['qty'], self.pos['qty']), px, i)
            cur = px

    # ── stats ───────────────────────────────────────────────────────────────
    def stats(self):
        t = self.trades
        n = len(t)
        wins = [x for x in t if x['pnl'] > 0]
        gp = sum(x['pnl'] for x in t if x['pnl'] > 0)
        gl = -sum(x['pnl'] for x in t if x['pnl'] <= 0)
        net = self.cash - self.capital
        return dict(trades=n, win_rate=(len(wins) / n * 100) if n else 0.0,
                    net=net, net_pct=net / self.capital * 100,
                    pf=(gp / gl) if gl > 0 else float('inf') if gp > 0 else 0.0,
                    max_dd_pct=self.max_dd / self.capital * 100,
                    avg_win=(gp / len(wins)) if wins else 0.0,
                    avg_loss=(gl / (n - len(wins))) if n - len(wins) else 0.0,
                    longs=sum(1 for x in t if x['dir'] == 1), shorts=sum(1 for x in t if x['dir'] == -1))
