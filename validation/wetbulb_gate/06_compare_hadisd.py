"""Repeat the station comparison with HadISD in place of ISD-Lite.

HadISD is the quality-controlled version of the same underlying NOAA archive:
observations failing its tests are replaced by a flagged value and are dropped
here. This run answers one question: do the conclusions drawn from ISD-Lite
(03_compare.py, 04_anomaly_skill.py) survive quality control?

Same wet-bulb solver, same AgERA5 points, same statistics, same day rules.
26 of the 29 stations are in HadISD.

Run:  bash tools/py.sh -W ignore validation/wetbulb_gate/06_compare_hadisd.py
Output: validation/wetbulb_gate/results/hadisd_comparison.csv, hadisd_skill.csv,
        hadisd_summary.txt
"""
import glob
import importlib.util
import os

import netCDF4 as nc
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


c3 = load("cmp03", "03_compare.py")
s4 = load("skill04", "04_anomaly_skill.py")
HAD = "E:/temp/station-hadisd/nc"


def read_hadisd(sid, lon):
    f = glob.glob(f"{HAD}/*_{sid}.nc")
    if not f:
        return None, None
    d = nc.Dataset(f[0])
    d.set_auto_mask(False)
    hrs = np.asarray(d.variables["time"][:])
    t = np.asarray(d.variables["temperatures"][:])
    td = np.asarray(d.variables["dewpoints"][:])
    n_flag = int(((t < -1.5e30) | (td < -1.5e30)).sum())      # removed by HadISD QC
    d.close()
    utc = pd.Timestamp("1931-01-01") + pd.to_timedelta(np.round(hrs).astype("int64"), unit="h")
    ok = (t > -1e29) & (td > -1e29) & (utc >= pd.Timestamp("1979-01-01"))
    h = pd.DataFrame({"t": t[ok], "td": td[ok]}, index=utc[ok] + pd.Timedelta(hours=int(round(lon / 15.0))))
    h = h[h.t.between(-60, 58) & h.td.between(-80, 40) & (h.td <= h.t + 1.0)]
    h["td"] = np.minimum(h.td, h.t)
    return h[~h.index.duplicated()], n_flag


if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    pts = pd.read_csv(f"{c3.GATE}/points.csv").set_index("pid")
    ag = c3.load_agera5()
    st = pd.read_csv(f"{c3.ISD}/stations.csv", dtype={"usaf": str, "wban": str})
    rows, sk = [], []
    for s in st.itertuples():
        sid = f"{s.usaf}-{s.wban}"
        pid = f"isd:{sid}"
        h, n_flag = read_hadisd(sid, s.lon)
        if h is None or len(h) < 5000:
            continue
        p = pts.loc[pid]
        h["tw"] = c3.wetbulb(h.t.values, c3.esat(h.td.values), c3.pressure(s.elev_m))
        day = h.index.floor("D")
        g = h.groupby(day)
        n = g.size()
        am = (h.index.hour >= 11) & (h.index.hour <= 17)
        aft = h[am].groupby(h.index[am].floor("D")).size()
        good = n.index[(n >= 6) & (aft.reindex(n.index).fillna(0) >= 2)]
        tw_max, tx, tn = g.tw.max().reindex(good), g.t.max().reindex(good), g.t.min().reindex(good)
        tw_at_tx = h.loc[g.t.idxmax().reindex(good).dropna().values, "tw"]
        tw_at_tx.index = tw_at_tx.index.floor("D")
        m_tx, m_tn, m_td = ag["t2mmax"][pid], ag["t2mmin"][pid], ag["t2mdp"][pid]
        m_tw = pd.Series(c3.wetbulb(m_tx.values, c3.esat(m_td.reindex(m_tx.index).values),
                                    c3.pressure(p.cell_elev_m)), index=m_tx.index)
        base = {"pid": pid, "name": s.name.strip(), "ctry": s.ctry, "qc_removed_obs": n_flag,
                "obs_per_day": float(n.reindex(good).median())}
        for obs, mod, lab in ((tw_max, m_tw, "Tw: station daily max vs AgERA5 Tw_day"),
                              (tw_at_tx, m_tw, "Tw: station at hour of Tmax vs AgERA5 Tw_day"),
                              (tx, m_tx, "T: station max of hourly vs AgERA5 Tmax"),
                              (g.td.mean().reindex(good), m_td, "Td: station daily mean vs AgERA5 dewpoint")):
            r = c3.stats(obs, mod, lab)
            if r:
                rows.append({**base, **r})
        for var, obs, mod in (("tmax", tx, m_tx), ("tmin", tn, m_tn), ("tw", tw_max, m_tw)):
            r = s4.skill(obs, mod)
            if r:
                sk.append({"pid": pid, "name": s.name.strip(), "var": var, **r})
    had, hsk = pd.DataFrame(rows), pd.DataFrame(sk)
    had.round(3).to_csv(f"{res}/hadisd_comparison.csv", index=False)
    hsk.round(3).to_csv(f"{res}/hadisd_skill.csv", index=False)

    # the same stations from the ISD-Lite runs, for a like-for-like table
    isd = pd.read_csv(f"{res}/isd_comparison.csv")
    isd = isd[isd.pid.isin(had.pid.unique())]
    isk = pd.read_csv(f"{res}/anomaly_skill.csv")
    isk = isk[(isk.src == "isd") & isk.pid.isin(hsk.pid.unique())]

    pd.set_option("display.width", 250)
    out = ["HadISD repeat of the station comparison. Produced by validation/wetbulb_gate/06_compare_hadisd.py",
           f"HadISD 3.4.3.2025f, {had.pid.nunique()} stations. ISD-Lite figures are for the same stations."]
    for lab in had.what.unique():
        out.append("\n-- HadISD" + "".join(c3.verdict(had, lab)).replace("\n", " ").replace("   ", "\n   "))
        out.append("-- ISD-Lite" + "".join(c3.verdict(isd, lab)).replace("\n", " ").replace("   ", "\n   "))
    out.append("\n== Anomaly skill, medians across stations (acc = anomaly correlation, hit = hot-day hit rate)")
    cmp = pd.concat([hsk.groupby("var")[["acc", "hit"]].median().add_prefix("hadisd_"),
                     isk.groupby("var")[["acc", "hit"]].median().add_prefix("isdlite_")], axis=1)
    cmp["rank_corr_acc_sd_hadisd"] = [hsk[hsk["var"] == v].acc.corr(hsk[hsk["var"] == v].sd_mod, method="spearman") for v in cmp.index]
    out.append(cmp.round(2).to_string())
    a = had[had.what.str.startswith("Tw: station daily max")].set_index("name")
    b = isd[isd.what.str.startswith("Tw: station daily max")].set_index("name")
    t = pd.DataFrame({"qc_removed": a.qc_removed_obs, "max_hadisd": a.obs_max, "max_isdlite": b.obs_max,
                      "p99_hadisd": a.obs_p99, "p99_isdlite": b.obs_p99, "agera5_p99": a.mod_p99,
                      "gap_p99_hadisd": a.gap_p99, "gap_p99_isdlite": b.gap_p99,
                      "d28_hadisd": a.obs_d28, "d28_isdlite": b.obs_d28, "d28_agera5": a.mod_d28})
    out.append("\n== Daily maximum wet-bulb by station (deg C; d28 = days per year at or above 28 C)")
    out.append(t.sort_values("p99_hadisd", ascending=False).round(2).to_string())
    txt = "\n".join(out)
    with open(f"{res}/hadisd_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
