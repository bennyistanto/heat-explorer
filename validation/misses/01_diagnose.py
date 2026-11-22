"""Diagnose the two kinds of miss in the held-out suites. DIAGNOSIS, NOT A TEST.

Both held-out suites are spent: their results are known. Anything learned here
is post hoc and can only be confirmed on events not yet looked at.

Miss 1, "severe" not reached (Maryland, 18 to 23 June 2024: 87 percent of the
area in a heat spell, 9 percent severe).
  Suspected cause, stated before running this: the daily class uses the larger
  of two exceedances, one over the calendar-day threshold and one over the
  all-year 95th percentile, and takes its cuts from all spell days pooled. In
  the hottest weeks the all-year threshold sits far below the day's value, so
  those days dominate the top of the pooled distribution, and an event early
  or late in the warm season can hardly reach the cut.
  Check: share of spell days that are severe, by calendar month, in the
  baseline. If the class is fair across the season the share is about the same
  in every month (0.20 by construction overall).
  Alternative looked at (V1): rank each exceedance against its own baseline
  distribution, and call a day severe (extreme) when EITHER is at or above its
  own 80th (95th) percentile.

Miss 2, a city inside a large province (Makkah province, 16 to 18 June 2024;
Karachi inside Sindh, June 2015).
  Check: the same days by district (adm2).

Run:  bash tools/py.sh -W ignore validation/misses/01_diagnose.py
Output: validation/misses/results/diagnose.txt
"""
import importlib.util
import os
import time
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
from rasterio import features
from rasterio.transform import from_origin

RAW = "E:/temp/agera5"
BND = "E:/temp/boundaries"
HERE = os.path.dirname(os.path.abspath(__file__))
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(1979, 2027)
UNITS = {"MDL": ("USA-20230119-24", "Maryland", "2024-06-18", "2024-06-23"),
         "MAK": ("SAU-20230404-02", "Makkah province", "2024-06-16", "2024-06-18"),
         "SIN": ("PAK-20230404-7", "Sindh", "2015-06-17", "2015-06-24")}
_D = {}


def read_job(a):
    v, y, boxes = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[VARS[v]]
    t = np.asarray(d.variables["time"][:])
    res = {k: np.asarray(x[:, b[0]:b[1] + 1, b[2]:b[3] + 1])[:, b[4]] for k, b in boxes.items()}
    d.close()
    return v, y, t, res


def init(days):
    spec = importlib.util.spec_from_file_location("det3", os.path.join(HERE, "..", "detector_v3", "detector.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _D["det"] = m
    _D["idx"] = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))


def cell_job(a):
    k, tm = a
    idx = _D["idx"]
    r = _D["det"].detect(tm.astype("f8"), idx)
    sp, base = r["spell"], np.asarray((idx.year >= 1991) & (idx.year <= 2020))
    f = r["flag"]
    live = f.copy()
    live[2:] &= f[1:-1] & f[:-2]
    live[:2] = False
    ec, ea = r["exc_cal"], r["exc_all"]
    bc, ba = sp & base & (ec > 0), sp & base & (ea > 0)
    c80, c95 = np.percentile(ec[bc], [80, 95]) if bc.sum() > 20 else (np.inf, np.inf)
    a80, a95 = np.percentile(ea[ba], [80, 95]) if ba.sum() > 20 else (np.inf, np.inf)
    v1 = np.where(sp, 1 + ((ec >= c80) | (ea >= a80)).astype(int) + ((ec >= c95) | (ea >= a95)).astype(int), 0)
    return k, r["cls_intensity"].astype("u1"), v1.astype("u1"), live, r["which"].astype("u1")


if __name__ == "__main__":
    t0 = time.time()
    res_dir = os.path.join(HERE, "results")
    os.makedirs(res_dir, exist_ok=True)
    boxes, adm2 = {}, {}
    for key, (uid, name, _, _) in UNITS.items():
        t = pq.read_table(f"{BND}/adm1_polygons.parquet", columns=["adm1_id", "geometry"], filters=[("adm1_id", "in", [uid])])
        g = shapely.from_wkb(t.column("geometry")[0].as_py())
        x0, y0, x1, y1 = g.bounds
        i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
        j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
        tr = from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1)
        m = features.rasterize([(g, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1), transform=tr, dtype="uint8").astype(bool)
        boxes[key] = (i0, i1, j0, j1, m)
        t2 = pq.read_table(f"{BND}/adm2_polygons.parquet", columns=["adm1_id", "adm2_name", "geometry"], filters=[("adm1_id", "in", [uid])])
        nm = t2.column("adm2_name").to_pylist()
        gs = [shapely.from_wkb(w) for w in t2.column("geometry").to_pylist()]
        lab = features.rasterize([(gg, k + 1) for k, gg in enumerate(gs)], out_shape=m.shape, transform=tr, dtype="int32")
        adm2[key] = (nm, lab)
    with Pool(32) as p:
        got = {(v, y): (t, r) for v, y, t, r in p.imap_unordered(read_job, [(v, y, boxes) for y in YEARS for v in VARS])}
    days = np.concatenate([got[("t2mmax", y)][0] for y in YEARS])
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    base = np.asarray((idx.year >= 1991) & (idx.year <= 2020))
    lat_all = 90 - 0.1 * np.arange(1801)
    out = ["Diagnosis of the held-out misses. Produced by validation/misses/01_diagnose.py. POST HOC: not a test.",
           "V0 = current daily class (larger of the two exceedances, pooled cuts). V1 = severe when either exceedance is at or above its own 80th percentile."]
    pd.set_option("display.width", 250, "display.max_rows", 80)
    with Pool(48, initializer=init, initargs=(days,)) as p:
        for key, (uid, name, w0, w1) in UNITS.items():
            i0, i1, j0, j1, m = boxes[key]
            cat = lambda v: np.concatenate([got[(v, y)][1][key] for y in YEARS]).astype("f4")
            tx, tn = cat("t2mmax"), cat("t2mmin")
            land = tx[0] != -9999.0
            tx, tn = tx[:, land] - 273.15, tn[:, land] - 273.15
            w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1 + 1][:, None], m.shape[1], axis=1)[m][land]))
            tm = np.full_like(tx, np.nan)
            tm[:-1] = (tx[:-1] + tn[1:]) / 2
            n = tm.shape[1]
            c0, c1 = np.zeros((len(idx), n), "u1"), np.zeros((len(idx), n), "u1")
            lv, wh = np.zeros((len(idx), n), bool), np.zeros((len(idx), n), "u1")
            for k, a, b, c, d in p.imap_unordered(cell_job, ((k, tm[:, k]) for k in range(n)), chunksize=8):
                c0[:, k], c1[:, k], lv[:, k], wh[:, k] = a, b, c, d
            ww = w / w.sum()
            win = np.asarray((idx >= pd.Timestamp(w0)) & (idx <= pd.Timestamp(w1)))
            out.append(f"\n==== {name}, {w0} to {w1}, {n} cells")
            d = pd.DataFrame({"spell_live": ((c0 >= 1) & lv)[win] @ ww, "sev_V0_live": ((c0 >= 2) & lv)[win] @ ww, "sev_V1_live": ((c1 >= 2) & lv)[win] @ ww,
                              "date_test_only": (wh == 1)[win] @ ww, "place_test_only": (wh == 2)[win] @ ww, "both_tests": (wh == 3)[win] @ ww}, index=idx[win].strftime("%m-%d"))
            out.append("Area shares by day in the window:")
            out.append(d.round(2).to_string())
            # season fairness, baseline: share of spell days that are severe, by month
            mo = idx.month.values
            rows = []
            for mth in range(1, 13):
                s = base & (mo == mth)
                nsp = (c0[s] >= 1).sum()
                if nsp > 200:
                    rows.append({"month": mth, "spell_days_share": nsp / max((c0[base] >= 1).sum(), 1),
                                 "severe_share_V0": (c0[s] >= 2).sum() / nsp, "severe_share_V1": (c1[s] >= 2).sum() / nsp})
            out.append("Baseline 1991-2020, by month: share of all spell days falling in the month, and the share of that month's spell days classed severe or extreme:")
            out.append(pd.DataFrame(rows).round(3).to_string(index=False))
            tot = lambda c: float(((c >= 2) & base[:, None]).sum() / max(((c >= 1) & base[:, None]).sum(), 1))
            y = idx.year.values
            rec = (y >= 2021) & (y <= 2025)
            out.append(f"Severe share of spell days overall, baseline: V0 {tot(c0):.3f}, V1 {tot(c1):.3f}. Severe days per cell-year 2021-25: V0 {(c0[rec] >= 2).sum() / n / 5:.1f}, V1 {(c1[rec] >= 2).sum() / n / 5:.1f}")
            # districts
            nm, lab = adm2[key]
            labc = lab[m][land]
            rows = []
            for k, nme in enumerate(nm):
                q = labc == k + 1
                if q.sum() == 0:
                    continue
                wq = w[q] / w[q].sum()
                rows.append({"district": str(nme)[:28], "cells": int(q.sum()),
                             "max_spell_live": float((((c0 >= 1) & lv)[win][:, q] @ wq).max()),
                             "max_sev_V0_live": float((((c0 >= 2) & lv)[win][:, q] @ wq).max()),
                             "max_sev_V1_live": float((((c1 >= 2) & lv)[win][:, q] @ wq).max())})
            D = pd.DataFrame(rows).sort_values("max_sev_V0_live", ascending=False)
            out.append(f"Districts (adm2): {len(D)} with cells; {int((D.max_sev_V0_live >= 0.5).sum())} reach severe over half their area under V0, {int((D.max_sev_V1_live >= 0.5).sum())} under V1; "
                       f"with 10 or more cells: {int(((D.max_sev_V0_live >= 0.5) & (D.cells >= 10)).sum())} of {int((D.cells >= 10).sum())}")
            out.append(D.head(14).round(2).to_string(index=False))
            print(key, f"{time.time() - t0:.0f} s", flush=True)
    txt = "\n".join(out)
    with open(f"{res_dir}/diagnose.txt", "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt.encode("ascii", "replace").decode())
