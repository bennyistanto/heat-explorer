"""Wet-bulb gate: compare AgERA5 afternoon wet-bulb with station observations.

Question (references/indicators.md, signal 4b): is AgERA5 Tw_day, computed from
daily maximum temperature and daily mean dewpoint, close enough to observed
daily maximum wet-bulb to support absolute humid-heat bands?

Gate as written before the run: fail if the 99th percentile gap exceeds 1 K,
or if days per year above a band edge differ by more than 2 times.

Station sources
  isd     NOAA ISD-Lite hourly T and Td (01_download_isd.py). Daily maximum
          wet-bulb over the local day; also wet-bulb at the hour of maximum T.
  wxgrid  Indonesian daily records from the wxgrid compiled dataset:
          wet-bulb from TX with 13:00 local humidity (HU13), and daily mean
          wet-bulb from TG with daily mean humidity (HU).

The same wet-bulb solver is used on both sides. Pressure comes from elevation
(standard atmosphere): station elevation for stations, ETOPO1 cell mean for
AgERA5. ISD-Lite and the wxgrid temperature and humidity fields are not fully
quality controlled; the checks here are range and consistency only.

Run:  bash tools/py.sh validation/wetbulb_gate/03_compare.py
Output: validation/wetbulb_gate/results/*.csv and summary.txt
"""
import glob
import gzip
import io
import os

import numpy as np
import pandas as pd

GATE = "E:/temp/agera5/derived-products/heat-explorer/wetbulb-gate"
ISD = "E:/temp/station-isd"
WX = "F:/temp/station/compiled"
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
BANDS = (24.0, 26.0, 28.0, 30.0)
MIN_DAYS = 1500


def esat(tc):
    """Saturation vapour pressure over water, hPa (Magnus form)."""
    return 6.1094 * np.exp(17.625 * tc / (tc + 243.04))


def pressure(elev_m):
    return 1013.25 * (1.0 - 2.25577e-5 * np.asarray(elev_m, "f8")) ** 5.25588


def wetbulb(tc, e, p):
    """Isobaric wet-bulb (deg C) by bisection on the psychrometric balance.

    cp (T - Tw) = Lv (ws(Tw) - w), with mixing ratios from vapour pressure.
    """
    tc, e, p = np.broadcast_arrays(np.asarray(tc, "f8"), np.asarray(e, "f8"), np.asarray(p, "f8"))
    w = 0.622 * e / (p - e)
    lo, hi = tc - 60.0, tc.copy()
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        ws = 0.622 * esat(mid) / (p - esat(mid))
        lv = 2.501e6 - 2361.0 * mid
        f = 1005.0 * (tc - mid) - lv * (ws - w)   # > 0 means mid is too cold
        up = f > 0
        lo = np.where(up, mid, lo)
        hi = np.where(up, hi, mid)
    return 0.5 * (lo + hi)


def load_agera5():
    z = np.load(f"{GATE}/agera5_points.npz", allow_pickle=False)
    # columns follow the row order of points.csv (the pid array in the npz was
    # saved as an object array and is not read)
    pid = pd.read_csv(f"{GATE}/points.csv").pid.values
    out = {}
    for v in ("t2mmax", "t2mmin", "t2mmean", "t2mdp"):
        dates = pd.Timestamp("1900-01-01") + pd.to_timedelta(z[f"time_{v}"], unit="D")
        a = z[v].astype("f8")
        a[a == -9999.0] = np.nan
        out[v] = pd.DataFrame(a - 273.15, index=dates, columns=pid)
    return out


def read_isd(usaf, wban, lon):
    """Hourly T, Td for one station as a frame indexed by local time."""
    parts = []
    for fn in sorted(glob.glob(f"{ISD}/raw/{usaf}-{wban}-*.gz")):
        with gzip.open(fn, "rt") as f:
            txt = f.read()
        if not txt.strip():
            continue
        d = pd.read_csv(io.StringIO(txt), sep=r"\s+", header=None, usecols=range(6),
                        names=["y", "m", "d", "h", "t", "td"])
        parts.append(d)
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    d = d[(d.t != -9999) & (d.td != -9999)]
    utc = pd.to_datetime(dict(year=d.y, month=d.m, day=d.d, hour=d.h))
    d = pd.DataFrame({"t": d.t.values / 10.0, "td": d.td.values / 10.0},
                     index=utc + pd.Timedelta(hours=int(round(lon / 15.0))))
    ok = d.t.between(-60, 58) & d.td.between(-80, 40) & (d.td <= d.t + 1.0)
    d = d[ok]
    d["td"] = np.minimum(d.td, d.t)
    return d


def stats(obs, mod, label):
    """Quantiles, bias, correlation and band-day counts on common days."""
    c = pd.concat([obs.rename("o"), mod.rename("m")], axis=1).dropna()
    if len(c) < MIN_DAYS:
        return None
    yrs = len(c) / 365.25
    r = {"what": label, "n_days": len(c), "first": c.index.min().date(), "last": c.index.max().date(),
         "bias_mean": (c.m - c.o).mean(), "r": c.o.corr(c.m)}
    for q in (50, 95, 99):
        r[f"obs_p{q}"] = c.o.quantile(q / 100)
        r[f"mod_p{q}"] = c.m.quantile(q / 100)
    r["gap_p99"] = r["mod_p99"] - r["obs_p99"]
    r["obs_max"], r["mod_max"] = c.o.max(), c.m.max()
    for b in BANDS:
        r[f"obs_d{b:.0f}"] = (c.o >= b).sum() / yrs
        r[f"mod_d{b:.0f}"] = (c.m >= b).sum() / yrs
    return r


def run_isd(ag, pts):
    rows = []
    st = pd.read_csv(f"{ISD}/stations.csv", dtype={"usaf": str, "wban": str})
    for s in st.itertuples():
        pid = f"isd:{s.usaf}-{s.wban}"
        if pid not in ag["t2mmax"].columns:
            continue
        p = pts.loc[pid]
        h = read_isd(s.usaf, s.wban, s.lon)
        if h is None or len(h) < 5000:
            continue
        h["tw"] = wetbulb(h.t.values, esat(h.td.values), pressure(s.elev_m))
        day = h.index.floor("D")
        g = h.groupby(day)
        n = g.size()
        aft = h[(h.index.hour >= 11) & (h.index.hour <= 17)].groupby(
            h.index[(h.index.hour >= 11) & (h.index.hour <= 17)].floor("D")).size()
        good = n.index[(n >= 6) & (aft.reindex(n.index).fillna(0) >= 2)]
        tw_max = g.tw.max().reindex(good)
        tx = g.t.max().reindex(good)
        tw_at_tx = h.loc[g.t.idxmax().reindex(good).dropna().values, "tw"]
        tw_at_tx.index = tw_at_tx.index.floor("D")
        td_mean = g.td.mean().reindex(good)

        m_tx, m_td = ag["t2mmax"][pid], ag["t2mdp"][pid]
        m_tw = pd.Series(wetbulb(m_tx.values, esat(m_td.reindex(m_tx.index).values),
                                 pressure(p.cell_elev_m)), index=m_tx.index)
        base = {"pid": pid, "name": s.name.strip(), "ctry": s.ctry, "lat": s.lat, "lon": s.lon,
                "stn_elev": s.elev_m, "cell_elev": p.cell_elev_m,
                "obs_per_day": float(n.reindex(good).median())}
        for obs, mod, lab in ((tw_max, m_tw, "Tw: station daily max vs AgERA5 Tw_day"),
                              (tw_at_tx, m_tw, "Tw: station at hour of Tmax vs AgERA5 Tw_day"),
                              (tx, m_tx, "T: station max of hourly vs AgERA5 Tmax"),
                              (td_mean, m_td, "Td: station daily mean vs AgERA5 dewpoint")):
            r = stats(obs, mod, lab)
            if r:
                rows.append({**base, **r})
    return pd.DataFrame(rows)


def run_wxgrid(ag, pts):
    def merged(v, lo, hi):
        d = pd.read_csv(f"{WX}/merged_{v}.csv.gz", usecols=["site_id", "date", "value", "flag"], low_memory=False)
        d = d[d.flag.isna() & d.value.between(lo, hi) & (d.date >= "1979-01-01")]
        d["date"] = pd.to_datetime(d.date)
        return d.pivot_table(index="date", columns="site_id", values="value", aggfunc="first")
    tx, tg = merged("TX", 15, 45), merged("TG", 10, 40)
    hu, hu13 = merged("HU", 20, 100), merged("HU13", 15, 100)
    rows = []
    for pid in [c for c in ag["t2mmax"].columns if c.startswith("wx:")]:
        sid = pid[3:]
        p = pts.loc[pid]
        elev = p.elev_m if np.isfinite(p.elev_m) and p.elev_m > 0 else p.cell_elev_m
        m_tx, m_tm, m_td = ag["t2mmax"][pid], ag["t2mmean"][pid], ag["t2mdp"][pid]
        pc = pressure(p.cell_elev_m)
        m_tw_day = pd.Series(wetbulb(m_tx.values, esat(m_td.reindex(m_tx.index).values), pc), index=m_tx.index)
        m_tw_mean = pd.Series(wetbulb(m_tm.values, esat(m_td.reindex(m_tm.index).values), pc), index=m_tm.index)
        base = {"pid": pid, "name": p["name"], "ctry": "ID", "lat": p.lat, "lon": p.lon,
                "stn_elev": p.elev_m, "cell_elev": p.cell_elev_m}
        pairs = []
        if sid in tx and sid in hu13:
            o = pd.concat([tx[sid], hu13[sid]], axis=1, keys=["t", "rh"]).dropna()
            pairs.append((pd.Series(wetbulb(o.t.values, esat(o.t.values) * o.rh.values / 100, pressure(elev)),
                                    index=o.index), m_tw_day, "Tw: station TX with 13h RH vs AgERA5 Tw_day"))
        if sid in tg and sid in hu:
            o = pd.concat([tg[sid], hu[sid]], axis=1, keys=["t", "rh"]).dropna()
            pairs.append((pd.Series(wetbulb(o.t.values, esat(o.t.values) * o.rh.values / 100, pressure(elev)),
                                    index=o.index), m_tw_mean, "Tw: station daily mean vs AgERA5 daily mean"))
        if sid in tx:
            pairs.append((tx[sid], m_tx, "T: station TX vs AgERA5 Tmax"))
        for obs, mod, lab in pairs:
            r = stats(obs, mod, lab)
            if r:
                # day labels in the source can be off by one: report the best lag
                c = pd.concat([obs.rename("o"), mod.rename("m")], axis=1)
                r["r_best_lag"] = max(c.o.corr(c.m.shift(k)) for k in (-1, 0, 1))
                rows.append({**base, **r})
    return pd.DataFrame(rows)


def verdict(df, label, band_edges=(26.0, 28.0)):
    """Apply the pre-stated gate to one comparison type."""
    d = df[df.what == label]
    lines = [f"\n== {label}: {len(d)} stations"]
    if d.empty:
        return lines
    lines.append(f"   p99 gap (AgERA5 minus station), K: median {d.gap_p99.median():+.2f}, "
                 f"range {d.gap_p99.min():+.2f} to {d.gap_p99.max():+.2f}; "
                 f"|gap| > 1 K at {(d.gap_p99.abs() > 1).sum()} of {len(d)}")
    lines.append(f"   mean bias K: median {d.bias_mean.median():+.2f}; daily r: median {d.r.median():.2f}")
    for b in band_edges:
        o, m = d[f"obs_d{b:.0f}"], d[f"mod_d{b:.0f}"]
        use = (o >= 1) | (m >= 1)                      # stations where the band occurs at all
        ratio = (m[use] + 0.1) / (o[use] + 0.1)
        bad = ((ratio > 2) | (ratio < 0.5)).sum()
        lines.append(f"   days/yr >= {b:.0f} C: {use.sum()} stations where it occurs; "
                     f"ratio AgERA5/station median {ratio.median():.2f}; outside 0.5 to 2 at {bad}")
    return lines


if __name__ == "__main__":
    os.makedirs(RES, exist_ok=True)
    pts = pd.read_csv(f"{GATE}/points.csv").set_index("pid")
    ag = load_agera5()
    isd = run_isd(ag, pts)
    wx = run_wxgrid(ag, pts)
    isd.round(3).to_csv(f"{RES}/isd_comparison.csv", index=False)
    wx.round(3).to_csv(f"{RES}/wxgrid_comparison.csv", index=False)

    out = ["Wet-bulb gate, AgERA5 against stations. Produced by validation/wetbulb_gate/03_compare.py",
           f"Gate: fail if |p99 gap| > 1 K, or days per year above a band edge differ by more than 2 times."]
    for lab in isd.what.unique():
        out += verdict(isd, lab)
    for lab in wx.what.unique():
        out += verdict(wx, lab)
    main = isd[isd.what == "Tw: station daily max vs AgERA5 Tw_day"]
    cols = ["name", "ctry", "n_days", "obs_per_day", "obs_p99", "mod_p99", "gap_p99", "obs_max", "mod_max",
            "obs_d26", "mod_d26", "obs_d28", "mod_d28", "obs_d30", "mod_d30", "r"]
    out.append("\n== ISD stations, daily maximum wet-bulb (deg C; d26 = days per year at or above 26 C)")
    out.append(main[cols].sort_values("obs_p99", ascending=False).round(2).to_string(index=False))
    txt = "\n".join(out)
    with open(f"{RES}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
