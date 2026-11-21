"""Day-to-day skill of AgERA5 against stations, on anomalies.

Purpose: decide where relative heat indicators (percentile exceedance, spells)
can be trusted, and find a quantity available at every grid cell that predicts
that skill, so a low-confidence mask can be drawn without stations.

For each station and variable, on common days:
  acc       correlation of anomalies (day-of-year mean removed, 31-day smoothed)
  hit       share of station hot days (above its own monthly 90th percentile)
            that AgERA5 also flags above its own monthly 90th percentile
  sd_mod    standard deviation of AgERA5 anomalies (the candidate predictor)

Uses the files made by 01 and 02. wxgrid day labels can be off by one, so the
best of lags -1, 0, +1 is reported for those sites.

Run:  bash tools/py.sh validation/wetbulb_gate/04_anomaly_skill.py
Output: validation/wetbulb_gate/results/anomaly_skill.csv, anomaly_skill.txt
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cmp03", os.path.join(HERE, "03_compare.py"))
c3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c3)

MIN_DAYS = 1500


def anomaly(s):
    """Remove a smoothed day-of-year mean computed from the series itself."""
    doy = s.index.dayofyear.where(s.index.dayofyear < 366, 365)
    clim = s.groupby(doy).mean().reindex(range(1, 366)).interpolate(limit_direction="both")
    wrapped = pd.concat([clim.iloc[-15:], clim, clim.iloc[:15]])
    smooth = wrapped.rolling(31, center=True).mean().iloc[15:-15]
    return s - smooth.reindex(doy).values


def hot(s):
    """True where the value exceeds the series' own 90th percentile for that month."""
    return s > s.groupby(s.index.month).transform(lambda x: x.quantile(0.9))


def skill(obs, mod, lags=(0,)):
    best = None
    for k in lags:
        c = pd.concat([obs.rename("o"), mod.shift(k).rename("m")], axis=1).dropna()
        if len(c) < MIN_DAYS:
            continue
        ao, am = anomaly(c.o), anomaly(c.m)
        ho, hm = hot(c.o), hot(c.m)
        r = {"n_days": len(c), "lag": k, "acc": ao.corr(am), "hit": (ho & hm).sum() / max(ho.sum(), 1),
             "sd_obs": ao.std(), "sd_mod": am.std()}
        if best is None or r["acc"] > best["acc"]:
            best = r
    return best


if __name__ == "__main__":
    pts = pd.read_csv(f"{c3.GATE}/points.csv").set_index("pid")
    ag = c3.load_agera5()
    rows = []

    st = pd.read_csv(f"{c3.ISD}/stations.csv", dtype={"usaf": str, "wban": str})
    for s in st.itertuples():
        pid = f"isd:{s.usaf}-{s.wban}"
        h = c3.read_isd(s.usaf, s.wban, s.lon)
        if h is None or pid not in pts.index:
            continue
        h["tw"] = c3.wetbulb(h.t.values, c3.esat(h.td.values), c3.pressure(s.elev_m))
        g = h.groupby(h.index.floor("D"))
        good = g.size()[g.size() >= 6].index
        p = pts.loc[pid]
        m_tw = pd.Series(c3.wetbulb(ag["t2mmax"][pid].values,
                                    c3.esat(ag["t2mdp"][pid].reindex(ag["t2mmax"].index).values),
                                    c3.pressure(p.cell_elev_m)), index=ag["t2mmax"].index)
        for var, obs, mod in (("tmax", g.t.max().reindex(good), ag["t2mmax"][pid]),
                              ("tmin", g.t.min().reindex(good), ag["t2mmin"][pid]),
                              ("tw", g.tw.max().reindex(good), m_tw)):
            r = skill(obs, mod)
            if r:
                rows.append({"pid": pid, "name": s.name.strip(), "src": "isd", "lat": s.lat, "var": var, **r})

    def merged(v, lo, hi):
        d = pd.read_csv(f"{c3.WX}/merged_{v}.csv.gz", usecols=["site_id", "date", "value", "flag"], low_memory=False)
        d = d[d.flag.isna() & d.value.between(lo, hi) & (d.date >= "1979-01-01")]
        d["date"] = pd.to_datetime(d.date)
        return d.pivot_table(index="date", columns="site_id", values="value", aggfunc="first")
    tx, tn = merged("TX", 15, 45), merged("TN", 5, 35)
    for pid in [c for c in pts.index if c.startswith("wx:")]:
        sid = pid[3:]
        for var, tab, mod in (("tmax", tx, ag["t2mmax"][pid]), ("tmin", tn, ag["t2mmin"][pid])):
            if sid in tab:
                r = skill(tab[sid], mod, lags=(-1, 0, 1))
                if r:
                    rows.append({"pid": pid, "name": pts.loc[pid, "name"], "src": "wxgrid",
                                 "lat": pts.loc[pid, "lat"], "var": var, **r})

    df = pd.DataFrame(rows)
    res = os.path.join(HERE, "results")
    df.round(3).to_csv(f"{res}/anomaly_skill.csv", index=False)

    out = ["Anomaly skill of AgERA5 against stations. Produced by validation/wetbulb_gate/04_anomaly_skill.py",
           "acc = anomaly correlation; hit = share of station hot days (monthly p90) also flagged by AgERA5;",
           "a hit rate of 0.10 is what chance gives."]
    for (src, var), d in df.groupby(["src", "var"]):
        out.append(f"\n== {src} {var}: {len(d)} stations; acc median {d.acc.median():.2f} "
                   f"(range {d.acc.min():.2f} to {d.acc.max():.2f}); hit median {d.hit.median():.2f}")
        out.append(f"   rank correlation of acc with sd_mod: {d.acc.corr(d.sd_mod, method='spearman'):+.2f}; "
                   f"of hit with sd_mod: {d.hit.corr(d.sd_mod, method='spearman'):+.2f}")
    allt = df[df["var"].isin(["tmax", "tmin"])]
    out.append("\n== Skill by AgERA5 anomaly spread (tmax and tmin, all stations)")
    bins = [0, 0.75, 1.0, 1.5, 2.5, 20]
    tab = allt.groupby(pd.cut(allt.sd_mod, bins), observed=True).agg(
        n=("acc", "size"), acc_median=("acc", "median"), acc_p25=("acc", lambda x: x.quantile(.25)),
        hit_median=("hit", "median"), hit_p25=("hit", lambda x: x.quantile(.25)))
    out.append(tab.round(2).to_string())
    out.append("\n== ISD stations")
    piv = df[df.src == "isd"].pivot(index="name", columns="var", values=["acc", "hit", "sd_mod"]).round(2)
    out.append(piv.sort_values(("acc", "tmax")).to_string())
    txt = "\n".join(out)
    with open(f"{res}/anomaly_skill.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
