"""Second diagnosis step: a season-fair class, and a look at the cells around a city.

01_diagnose.py showed that the daily intensity class is badly uneven across
the year. In Maryland 4.7 percent of June spell days are classed severe, 16
percent of July's, 41 percent of April's and 84 percent of March's. The reason
is that excess is divided by one all-year spread, while day-to-day spread is
much larger in the cool half of the year. So "severe" mostly marks cool-season
warmth, and an early-summer heat wave can hardly earn it. V1 (ranking the two
exceedances separately) did not fix this.

V2, tried here: class by calendar-day percentiles of the 3-day mean, the same
way the spell threshold itself is built (15-day window, seasonal cycle removed,
1991-2020):
    heat spell  as now (calendar p90 with the median floor, OR all-year p95)
    severe      a spell day above its calendar-day 95th percentile
    extreme     a spell day above its calendar-day 99th percentile
A day's class then depends only on how unusual it is for its own date, so
every part of the year has the same chance of a severe day. It is causal and
final when written, like V0.

Also here: for a city inside a large province, the share of cells within 50 km
of the city that are in a spell and severe (Mecca, Karachi, Baltimore), and
the largest connected patch of severe cells in the province.

POST HOC. The held-out events used here are spent. This is diagnosis to choose
what to register for a future test; nothing here can pass or fail.

Run:  bash tools/py.sh -W ignore validation/misses/02_calendar_classes.py
Output: validation/misses/results/calendar_classes.txt
"""
import importlib.util
import os
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
_D = {}
CITY = {"MDL": ("Baltimore", 39.29, -76.61), "MAK": ("Mecca", 21.42, 39.83), "SIN": ("Karachi", 24.86, 67.01)}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cal_multi(p1, x, idx, qs):
    """Calendar-day percentiles (list qs) with the seasonal cycle removed; same construction as 03_tune_detector.cal_threshold."""
    doy = p1.doy365(idx)
    base = (idx.year >= 1991) & (idx.year <= 2020) & np.isfinite(x)
    clim = p1.smooth_clim(x, doy, base)
    ab, db = (x - clim[doy - 1])[base], doy[base]
    pq = np.empty((365, len(qs)))
    for d in range(1, 366):
        dist = np.abs(db - d)
        pq[d - 1] = np.percentile(ab[np.minimum(dist, 365 - dist) <= 7], qs)
    return clim[doy - 1][:, None] + pq[doy - 1]


def read_job(a):
    import netCDF4 as nc
    v, y, boxes = a
    d = nc.Dataset(f"E:/temp/agera5/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[{"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}[v]]
    t = np.asarray(d.variables["time"][:])
    res = {k: np.asarray(x[:, b[0]:b[1] + 1, b[2]:b[3] + 1])[:, b[4]] for k, b in boxes.items()}
    d.close()
    return v, y, t, res


def init(days):
    _D["det"] = load("det3", os.path.join(HERE, "..", "detector_v3", "detector.py"))
    _D["idx"] = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))


def cell_job(a):
    k, tm = a
    det, idx = _D["det"], _D["idx"]
    tm = tm.astype("f8")
    r = det.detect(tm, idx)
    t3 = pd.Series(tm).rolling(3, center=True).mean().values
    thr = cal_multi(det.p1, t3, idx, [95, 99])
    sp = r["spell"]
    with np.errstate(invalid="ignore"):
        v2 = np.where(sp, 1 + (t3 > thr[:, 0]).astype(int) + (t3 > thr[:, 1]).astype(int), 0)
    f = r["flag"]
    live = f.copy()
    live[2:] &= f[1:-1] & f[:-2]
    live[:2] = False
    return k, r["cls_intensity"].astype("u1"), v2.astype("u1"), live


if __name__ == "__main__":
    t0 = time.time()
    d1 = load("diag01", os.path.join(HERE, "01_diagnose.py"))
    import pyarrow.parquet as pq
    import shapely
    from rasterio import features
    from rasterio.transform import from_origin
    boxes = {}
    for key, (uid, name, _, _) in d1.UNITS.items():
        t = pq.read_table(f"{d1.BND}/adm1_polygons.parquet", columns=["adm1_id", "geometry"], filters=[("adm1_id", "in", [uid])])
        g = shapely.from_wkb(t.column("geometry")[0].as_py())
        x0, y0, x1, y1 = g.bounds
        i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
        j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
        m = features.rasterize([(g, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1), transform=from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1), dtype="uint8").astype(bool)
        boxes[key] = (i0, i1, j0, j1, m)
    jobs = [(v, y, boxes) for y in d1.YEARS for v in d1.VARS]
    got = {}
    with Pool(32) as p:
        for v, y, t, r in p.imap_unordered(read_job, jobs):
            got[(v, y)] = (t, r)
    days = np.concatenate([got[("t2mmax", y)][0] for y in d1.YEARS])
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    base = np.asarray((idx.year >= 1991) & (idx.year <= 2020))
    yv, mo = idx.year.values, idx.month.values
    rec = (yv >= 2021) & (yv <= 2025)
    lat_all, lon_all = 90 - 0.1 * np.arange(1801), -180 + 0.1 * np.arange(3600)
    pd.set_option("display.width", 250, "display.max_rows", 80)
    out = ["Calendar-day classes (V2) against the current daily class (V0). Produced by validation/misses/02_calendar_classes.py. POST HOC: not a test."]
    with Pool(48, initializer=init, initargs=(days,)) as p:
        # the 17 single cells first: fairness by month
        init(days)
        det = _D["det"]
        z = np.load(det.p1.CELLS)
        if np.array_equal(z["time"], days):
            rows = []
            sites = list(det.p1.ELEV)
            def tm_site(s):
                g = lambda v: np.where(z[f"{v}__{s}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{s}"][:, 5, 5].astype("f8") - 273.15)
                return (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
            for s, a, b, _ in p.imap_unordered(cell_job, [(s, tm_site(s)) for s in sites]):
                sh0, sh2 = [], []
                for mth in range(1, 13):
                    q = base & (mo == mth)
                    if (a[q] >= 1).sum() >= 30:
                        sh0.append((a[q] >= 2).sum() / (a[q] >= 1).sum())
                        sh2.append((b[q] >= 2).sum() / (b[q] >= 1).sum())
                rows.append({"site": s, "months": len(sh0), "V0_min": min(sh0), "V0_max": max(sh0), "V2_min": min(sh2), "V2_max": max(sh2),
                             "sev_share_V0": (a[base] >= 2).sum() / (a[base] >= 1).sum(), "sev_share_V2": (b[base] >= 2).sum() / (b[base] >= 1).sum(),
                             "ext_share_V2": (b[base] >= 3).sum() / (b[base] >= 1).sum(),
                             "sev_days_yr_V0_2125": (a[rec] >= 2).sum() / 5, "sev_days_yr_V2_2125": (b[rec] >= 2).sum() / 5})
            S = pd.DataFrame(rows).set_index("site").loc[sites]
            out.append("\n== 17 single cells, baseline: share of a month's spell days classed severe or extreme, lowest and highest month (months with 30 or more spell days)")
            out.append(S.round(2).to_string())
            out.append(f"Spread between months (max minus min), median over cells: V0 {(S.V0_max - S.V0_min).median():.2f}, V2 {(S.V2_max - S.V2_min).median():.2f}")
        for key, (uid, name, w0, w1) in d1.UNITS.items():
            i0, i1, j0, j1, m = boxes[key]
            cat = lambda v: np.concatenate([got[(v, y)][1][key] for y in d1.YEARS]).astype("f4")
            tx, tn = cat("t2mmax"), cat("t2mmin")
            land = tx[0] != -9999.0
            tx, tn = tx[:, land] - 273.15, tn[:, land] - 273.15
            ii, jj = np.nonzero(m)
            ii, jj = ii[land], jj[land]
            la, lo = lat_all[ii + i0], lon_all[jj + j0]
            w = np.cos(np.deg2rad(la))
            tm = np.full_like(tx, np.nan)
            tm[:-1] = (tx[:-1] + tn[1:]) / 2
            n = tm.shape[1]
            c0, c2, lv = np.zeros((len(idx), n), "u1"), np.zeros((len(idx), n), "u1"), np.zeros((len(idx), n), bool)
            for k, a, b, c in p.imap_unordered(cell_job, ((k, tm[:, k]) for k in range(n)), chunksize=8):
                c0[:, k], c2[:, k], lv[:, k] = a, b, c
            ww = w / w.sum()
            win = np.asarray((idx >= pd.Timestamp(w0)) & (idx <= pd.Timestamp(w1)))
            cname, cla, clo = CITY[key]
            near = np.hypot(la - cla, (lo - clo) * np.cos(np.deg2rad(cla))) * 111 <= 50
            wn = w[near] / w[near].sum() if near.any() else None
            out.append(f"\n==== {name}, {w0} to {w1}, {n} cells; {int(near.sum())} cells within 50 km of {cname}")
            patch = []
            for t in np.flatnonzero(win):
                g = np.zeros(m.shape, bool)
                g[ii, jj] = (c2[t] >= 2) & lv[t]
                lab, nl = ndimage.label(g, structure=np.ones((3, 3)))
                patch.append(int(ndimage.sum(g, lab, range(1, nl + 1)).max()) if nl else 0)
            d = pd.DataFrame({"spell_live": ((c0 >= 1) & lv)[win] @ ww, "sev_V0": ((c0 >= 2) & lv)[win] @ ww, "sev_V2": ((c2 >= 2) & lv)[win] @ ww,
                              "ext_V2": ((c2 >= 3) & lv)[win] @ ww,
                              f"near_{cname}_spell": ((c0 >= 1) & lv)[win][:, near] @ wn, f"near_{cname}_sev_V0": ((c0 >= 2) & lv)[win][:, near] @ wn,
                              f"near_{cname}_sev_V2": ((c2 >= 2) & lv)[win][:, near] @ wn, "largest_sev_patch_V2_cells": patch}, index=idx[win].strftime("%m-%d"))
            out.append(d.round(2).to_string())
            rows = []
            for mth in range(1, 13):
                q = base & (mo == mth)
                nsp = (c0[q] >= 1).sum()
                if nsp > 200:
                    rows.append({"month": mth, "severe_share_V0": (c0[q] >= 2).sum() / nsp, "severe_share_V2": (c2[q] >= 2).sum() / nsp, "extreme_share_V2": (c2[q] >= 3).sum() / nsp})
            out.append("Baseline, share of the month's spell days classed severe or extreme:")
            out.append(pd.DataFrame(rows).round(3).to_string(index=False))
            # base rate of "severe over half the area on a window day", same calendar window, other years, live labelling
            a, b = pd.Timestamp(w0), pd.Timestamp(w1)
            br0, br2 = [], []
            for y in range(1979, 2026):
                if y == a.year:
                    continue
                q = np.asarray((idx >= a + pd.DateOffset(years=y - a.year)) & (idx <= b + pd.DateOffset(years=y - a.year)))
                br0.append((((c0 >= 2) & lv)[q] @ ww).max() >= 0.5)
                br2.append((((c2 >= 2) & lv)[q] @ ww).max() >= 0.5)
            out.append(f"Severe over half the area on a window day: V0 {bool(d.sev_V0.max() >= 0.5)}, V2 {bool(d.sev_V2.max() >= 0.5)}. Same dates in other years (base rate): V0 {np.mean(br0):.2f}, V2 {np.mean(br2):.2f}")
            out.append(f"Severe days per cell-year: baseline V0 {(c0[base] >= 2).sum() / n / 30:.1f}, V2 {(c2[base] >= 2).sum() / n / 30:.1f}; 2021-25 V0 {(c0[rec] >= 2).sum() / n / 5:.1f}, V2 {(c2[rec] >= 2).sum() / n / 5:.1f}")
            print(key, f"{time.time() - t0:.0f} s", flush=True)
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "calendar_classes.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt.encode("ascii", "replace").decode())
