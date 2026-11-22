"""Do stations warm as much as AgERA5 in the patches that 01_patches.py read as stepped?

01_patches.py read two patches as LOCAL STEP (Congo basin, south-east Peru,
both breaking in 2020) and one as OWN STEP (coastal Ecuador). The patch around
Lake Victoria's north-west shore is added because its difference from its ring
also rises. This script asks whether AgERA5 has drifted away from the stations
there since 2020.

Data: NOAA ISD-Lite stations with records from 2005 or earlier to 2024 or
later in four boxes; AgERA5 Tmax and Tmin at each station's cell, 2005-2025.
Series: monthly mean of daily (max + min) / 2, AgERA5 minus station, with the
mean annual cycle of the difference removed.
Number per station: change = mean difference 2021-2025 minus mean difference
2010-2019. Positive means AgERA5 warmed more than the station. A station is
used when it has 24 or more months in each period.
"In patch": the 3 by 3 block of cells around the station averages more than
100 severe days a year in 2021-2025.

Reading rule, written on 2026-11-22 before the run, per region:
  CANNOT TEST          fewer than 3 usable stations in the patch.
  AGERA5 DRIFTS WARM   median change of in-patch stations is 0.3 K or more,
                       AND at least two thirds of them are positive, AND the
                       median change of the out-of-patch stations is less
                       than half the in-patch median.
  NOT SHOWN            otherwise.

Limits: ISD-Lite is not quality controlled. Many of these stations report
only by day, and the hours reported change over the years, which moves the
station's own (max + min) / 2; the mean number of reports per day in each
period is printed so that can be seen. Station moves are not consulted. A
"NOT SHOWN" does not clear a patch.

Station files are downloaded from NOAA into E:/temp/station-isd/raw.

Run:  bash tools/py.sh -W ignore validation/tropical_patches/02_station_check.py
Output: validation/tropical_patches/results/station_check.txt, station_check.csv
"""
import glob
import gzip
import importlib.util
import io
import os
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = "E:/temp/agera5"
ISD = "E:/temp/station-isd"
D = "E:/temp/agera5/derived-products/heat-explorer"
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(2005, 2026)
BOXES = {"Congo basin": (-7, 7, 16, 30), "South-east Peru": (-14.5, -9, -75, -68.5), "Lake Victoria north-west": (-2, 2, 30, 34), "Coastal Ecuador": (-3.5, 1.5, -81, -78)}
_P = {}


def init(pts):
    _P["pts"] = pts


def job(a):
    v, y = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    var = d.variables[VARS[v]]
    x = np.stack([np.asarray(var[:, i, j]) for i, j in _P["pts"]], axis=1)
    t = np.asarray(d.variables["time"][:])
    d.close()
    return v, y, t, x


def reports_per_day(usaf, wban, y0, y1):
    n = days = 0
    for y in range(y0, y1 + 1):
        for fn in glob.glob(f"{ISD}/raw/{usaf}-{wban}-{y}.gz"):
            with gzip.open(fn, "rt") as f:
                txt = f.read()
            if txt.strip():
                d = pd.read_csv(io.StringIO(txt), sep=r"\s+", header=None, usecols=range(5), names=["y", "m", "d", "h", "t"])
                d = d[d.t != -9999]
                n += len(d)
                days += d.groupby(["m", "d"]).ngroups
    return n / days if days else np.nan


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("pc", os.path.join(HERE, "..", "confidence_map", "02_patch_check.py"))
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    S = np.load(f"{D}/v1/run_summary_global.npz")["days_per_year"][3]
    h = pd.read_csv(f"{ISD}/isd-history.csv", dtype=str).rename(columns={"STATION NAME": "NAME", "ELEV(M)": "ELEV"})
    for c in ("LAT", "LON"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h["b"], h["e"] = h.BEGIN.str[:4].astype(int), h.END.str[:4].astype(int)
    sel = []
    for nm, (a, b, c, d) in BOXES.items():
        s = h[(h.b <= 2005) & (h.e >= 2024) & h.LAT.between(a, b) & h.LON.between(c, d)].sort_values("b").drop_duplicates("USAF").copy()
        s["region"] = nm
        sel.append(s)
    st = pd.concat(sel).drop_duplicates("USAF").reset_index(drop=True)
    st["i"], st["j"] = np.round((90 - st.LAT) / 0.1).astype(int), np.round((st.LON + 180) / 0.1).astype(int)
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(pc.fetch, [(r.USAF, r.WBAN, y) for r in st.itertuples() for y in YEARS]))
    pts = list(zip(st.i, st.j))
    with Pool(32, initializer=init, initargs=(pts,)) as p:
        got = {(v, y): (t, x) for v, y, t, x in p.imap_unordered(job, [(v, y) for y in YEARS for v in VARS])}
    dates = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(np.concatenate([got[("t2mmax", y)][0] for y in YEARS]), unit="D"))
    tx = np.concatenate([got[("t2mmax", y)][1] for y in YEARS]).astype("f4")
    tn = np.concatenate([got[("t2mmin", y)][1] for y in YEARS]).astype("f4")

    rows = []
    for k, r in enumerate(st.itertuples()):
        if tx[0, k] == -9999.0:
            continue
        sd = pc.station_daily(r.USAF, r.WBAN, r.LON)
        if sd is None:
            continue
        ag = pd.Series((tx[:, k] + tn[:, k]) / 2 - 273.15, index=dates)
        both = pd.concat([sd.rename("s"), ag.rename("a")], axis=1).dropna()
        if both.empty:
            continue
        ms, ma = pc.monthly(both.s), pc.monthly(both.a)
        df = (ma - ms).dropna()
        df = df - df.groupby(df.index.month).transform("mean")
        e, l = df[(df.index.year >= 2010) & (df.index.year <= 2019)], df[df.index.year >= 2021]
        blk = S[r.i - 1:r.i + 2, r.j - 1:r.j + 2]
        sev = float(np.nanmean(blk)) if np.isfinite(blk).any() else np.nan
        sa, aa = ms - ms.groupby(ms.index.month).transform("mean"), ma - ma.groupby(ma.index.month).transform("mean")
        w = lambda x, y0, y1: float(x[(x.index.year >= y0) & (x.index.year <= y1)].mean())
        yr = df.groupby(df.index.year).mean()
        rows.append({"region": r.region, "usaf": r.USAF, "name": str(r.NAME).strip()[:18], "lat": r.LAT, "lon": r.LON, "sev_days": round(sev, 0),
                     "in_patch": bool(sev > 100), "months_10_19": len(e), "months_21_25": len(l), "usable": len(e) >= 24 and len(l) >= 24,
                     "change_K": round(float(l.mean() - e.mean()), 2) if len(e) and len(l) else np.nan,
                     "agera5_warm_K": round(w(aa, 2021, 2025) - w(aa, 2010, 2019), 2), "station_warm_K": round(w(sa, 2021, 2025) - w(sa, 2010, 2019), 2),
                     "rep_day_10_19": round(reports_per_day(r.USAF, r.WBAN, 2010, 2019), 1), "rep_day_21_25": round(reports_per_day(r.USAF, r.WBAN, 2021, 2025), 1),
                     "diff_2016_2025": " ".join("  n/a" if not np.isfinite(v) else f"{v:+.1f}" for v in yr.reindex(range(2016, 2026)).values)})
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(HERE, "results", "station_check.csv"), index=False)
    pd.set_option("display.width", 400, "display.max_columns", 40, "display.max_colwidth", 90)
    out = ["Stations against AgERA5 in the stepped patches. Produced by validation/tropical_patches/02_station_check.py",
           "change_K: (AgERA5 minus station) in 2021-2025 minus the same in 2010-2019. agera5_warm_K, station_warm_K: each one's own change on the months both have.",
           f"Stations listed by ISD in the boxes: {len(st)}; with any overlapping data: {len(t)}; usable (24 months in each period): {int(t.usable.sum())}", ""]
    for nm in BOXES:
        g = t[t.region == nm].sort_values(["in_patch", "sev_days"], ascending=False)
        out.append(f"== {nm}")
        out.append(g.drop(columns=["region"]).to_string(index=False))
        u = g[g.usable]
        ins, outs = u[u.in_patch].change_K, u[~u.in_patch].change_K
        if len(ins) < 3:
            v = "CANNOT TEST"
        elif ins.median() >= 0.3 and (ins > 0).mean() >= 2 / 3 and (len(outs) == 0 or outs.median() < ins.median() / 2):
            v = "AGERA5 DRIFTS WARM"
        else:
            v = "NOT SHOWN"
        med = lambda x: f"{x.median():+.2f} K (n={len(x)})" if len(x) else "none"
        out.append(f"usable in patch: {med(ins)}; usable out of patch: {med(outs)}; all usable: {med(u.change_K)}; positive among all usable: {int((u.change_K > 0).sum())} of {len(u)}")
        out.append(f"READING by the rule written first: {v}\n")
    u = t[t.usable & np.isfinite(t.sev_days)]
    if len(u) >= 8:
        out.append(f"All regions, usable stations (n={len(u)}): rank correlation of change_K with severe days per year at the station: {u.change_K.corr(u.sev_days, method='spearman'):+.2f}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "station_check.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)
