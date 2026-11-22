"""Measure what a "severe patch" rule would do, to choose its size threshold.

Candidate rule: besides the share of a unit's area that is severe, report the
largest connected patch of severe cells, and say "severe heat in part of the
area" when that patch reaches a stated size while the unit as a whole stays
under half.

Definitions used here
  severe cell  calendar-day class 2 or 3 (detector.py cls_day), live labelling
               (the day and the two before it all flagged)
  patch        8-connected severe cells inside the unit on one day
  size         sum of cell areas, 123.6 km2 x cos(latitude) per 0.1 degree cell

Measured for candidate thresholds of 1,000, 2,500, 5,000 and 10,000 km2, in
three units of very different size and shape (Maryland, Makkah province,
Sindh): how many days a year the rule would speak in the baseline, how many of
those are days the area share already says "most of the area", and what it
does on the documented event days.

POST HOC and for specification only. The three events are spent. The
threshold chosen from this is a candidate to be tested on new events.

Run:  bash tools/py.sh -W ignore validation/misses/04_patch_rule.py
Output: validation/misses/results/patch_rule.txt
"""
import importlib.util
import os
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
TS = (1000, 2500, 5000, 10000)
_D = {}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


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
    r = _D["det"].detect(tm.astype("f8"), _D["idx"])
    f = r["flag"]
    live = f.copy()
    live[2:] &= f[1:-1] & f[:-2]
    live[:2] = False
    return k, ((r["cls_day"] >= 2) & live)


if __name__ == "__main__":
    t0 = time.time()
    d1 = load("diag01", os.path.join(HERE, "01_diagnose.py"))
    c2 = load("c02", os.path.join(HERE, "02_calendar_classes.py"))
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
    got = {}
    with Pool(32) as p:
        for v, y, t, r in p.imap_unordered(read_job, [(v, y, boxes) for y in d1.YEARS for v in d1.VARS]):
            got[(v, y)] = (t, r)
    days = np.concatenate([got[("t2mmax", y)][0] for y in d1.YEARS])
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    yv = idx.year.values
    base, rec = (yv >= 1991) & (yv <= 2020), (yv >= 2021) & (yv <= 2025)
    lat_all, lon_all = 90 - 0.1 * np.arange(1801), -180 + 0.1 * np.arange(3600)
    out = ["Severe patch rule: what each size threshold would do. Produced by validation/misses/04_patch_rule.py. POST HOC, for specification."]
    S8 = np.ones((3, 3))
    with Pool(48, initializer=init, initargs=(days,)) as p:
        for key, (uid, name, w0, w1) in d1.UNITS.items():
            i0, i1, j0, j1, m = boxes[key]
            cat = lambda v: np.concatenate([got[(v, y)][1][key] for y in d1.YEARS]).astype("f4")
            tx, tn = cat("t2mmax"), cat("t2mmin")
            land = tx[0] != -9999.0
            tx, tn = tx[:, land] - 273.15, tn[:, land] - 273.15
            ii, jj = np.nonzero(m)
            ii, jj = ii[land], jj[land]
            la = lat_all[ii + i0]
            area = 123.6 * np.cos(np.deg2rad(la))
            tm = np.full_like(tx, np.nan)
            tm[:-1] = (tx[:-1] + tn[1:]) / 2
            n = tm.shape[1]
            sev = np.zeros((len(idx), n), bool)
            for k, a in p.imap_unordered(cell_job, ((k, tm[:, k]) for k in range(n)), chunksize=8):
                sev[:, k] = a
            share = sev @ (area / area.sum())
            big = np.zeros(len(idx))
            cen = np.full((len(idx), 2), np.nan)
            agrid = np.zeros(m.shape)
            agrid[ii, jj] = area
            for t in np.flatnonzero(sev.any(axis=1)):
                g = np.zeros(m.shape, bool)
                g[ii, jj] = sev[t]
                lab, nl = ndimage.label(g, structure=S8)
                sz = ndimage.sum(agrid, lab, range(1, nl + 1))
                k = int(np.argmax(sz))
                big[t] = sz[k]
                cy, cx = ndimage.center_of_mass(g, lab, k + 1)
                cen[t] = (lat_all[i0] - 0.1 * cy, lon_all[j0] + 0.1 * cx)
            cname, cla, clo = c2.CITY[key]
            win = np.asarray((idx >= pd.Timestamp(w0)) & (idx <= pd.Timestamp(w1)))
            out.append(f"\n==== {name}: {n} cells, {area.sum():,.0f} km2. Event window {w0} to {w1}.")
            out.append(f"Baseline days a year with half the area severe ('most of the area'): {(share[base] >= 0.5).sum() / 30:.1f}; 2021-25: {(share[rec] >= 0.5).sum() / 5:.1f}")
            out.append("threshold_km2  days/yr patch>=T (baseline)  of which share<0.5 (the rule's own days)  2021-25 rule days/yr  share of unit area at T")
            for T in TS:
                hit = big >= T
                own = hit & (share < 0.5)
                out.append(f"  {T:>8,}          {hit[base].sum() / 30:6.1f}                      {own[base].sum() / 30:6.1f}                          {own[rec].sum() / 5:6.1f}              {T / area.sum():.3f}")
            dfw = pd.DataFrame({"share_severe": share[win], "largest_patch_km2": big[win], "patch_share_of_unit": big[win] / area.sum(),
                                f"patch_centre_km_from_{cname}": np.hypot(cen[win, 0] - cla, (cen[win, 1] - clo) * np.cos(np.deg2rad(cla))) * 111}, index=idx[win].strftime("%m-%d"))
            out.append("Event window, by day:")
            out.append(dfw.round(2).to_string())
            print(key, f"{time.time() - t0:.0f} s", flush=True)
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "patch_rule.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
