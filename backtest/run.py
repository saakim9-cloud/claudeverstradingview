import sys, numpy as np, pandas as pd
sys.path.insert(0, '.')
from strategies import run_msnr, run_ict, run_smc

df = pd.read_csv(sys.argv[1], parse_dates=['datetime']).set_index('datetime').sort_index()
df.index = pd.to_datetime(df.index, utc=True)
df = df[~df.index.duplicated()]

def htf_bias(df, rule='4h', n=50):
    h = df['close'].resample(rule, label='left', closed='left').last().dropna()
    ema = h.ewm(span=n, adjust=False).mean()
    sig = np.sign(h - ema)                      # value of a completed HTF bar
    sig = sig.shift(1)                          # only known once the next HTF bar starts
    return sig.reindex(df.index, method='ffill').fillna(0).values

bias = htf_bias(df)
fmt = "{:<44} {:>6} {:>7} {:>10} {:>6} {:>7} {:>6}/{:<6}"
print(f"Data: {len(df)} bars  {df.index[0]} -> {df.index[-1]}")
for comm, lab in ((0.02, "Pine settings (0.02% comm/side)"), (0.005, "Low-cost broker (0.005% comm/side)")):
    print("\n==", lab)
    print(fmt.format("Strategy", "Trades", "Win%", "Net %", "PF", "MaxDD%", "L", "S"))
    runs = [
        ("ICT Pre-NY (default: 50% partial)", run_ict(df, comm=comm)),
        ("ICT Pre-NY + H4 EMA50 bias", run_ict(df, comm=comm, bias=bias)),
        ("ICT Pre-NY fixed 1:3", run_ict(df, comm=comm, tp_mode='fixed')),
        ("SMC OB (default, no time filter)", run_smc(df, comm=comm)),
        ("SMC OB + sessions", run_smc(df, comm=comm, use_sess=True)),
        ("SMC OB + H4 EMA50 bias", run_smc(df, comm=comm, bias=bias)),
        ("MSNR (default: next level)", run_msnr(df, comm=comm)),
        ("MSNR fixed 1:2", run_msnr(df, comm=comm, tp_mode='fixed')),
    ]
    for name, e in runs:
        s = e.stats()
        print(fmt.format(name, s['trades'], f"{s['win_rate']:.1f}", f"{s['net_pct']:+.1f}", f"{s['pf']:.2f}",
                         f"{s['max_dd_pct']:.1f}", s['longs'], s['shorts']))
