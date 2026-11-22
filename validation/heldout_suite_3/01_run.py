"""Run the third held-out suite exactly as registered in PROTOCOL.md of this folder.

Tests A (calendar-day class at admin level) and B (location readout, 3 by 3
cells). Detector: validation/detector_v3/detector.py, field cls_day, called
once per cell. Nothing here chooses an event, window, unit, place or threshold.

Run:  bash tools/py.sh -W ignore validation/heldout_suite_3/01_run.py
Output: validation/heldout_suite_3/results/summary.txt, units.csv;
        E:/temp/agera5/derived-products/heat-explorer/heldout3/<key>_series.csv.gz
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
OUT = "E:/temp/agera5/derived-products/heat-explorer/heldout3"
CELLS = "E:/temp/agera5/derived-products/heat-explorer/critique-2026-11-20/hx_cells.npz"
HERE = os.path.dirname(os.path.abspath(__file__))
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(1979, 2027)
_D = {}


def read_job(a):
    v, y, boxes = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[VARS[v]]
    t = np.asarray(d.variables["time"][:])
    res = {k: np.asarray(x[:, i0:i1 + 1, j0:j1 + 1])[:, m] for k, (i0, i1, j0, j1, m) in boxes.items()}
    d.close()
    return v, y, t, res


def init(days):
    spec = importlib.util.spec_from_file_location("det3", os.path.join(HERE, "..", "detector_v3", "detector.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _D["det"] = m
    _D["idx"] = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))


def cell_job(a):
    """One cell through the single-cell reference. Calendar-day class, live labelling."""
    k, tm = a
    r = _D["det"].detect(tm.astype("f8"), _D["idx"])
    f = r["flag"]
    live = f.copy()
    live[2:] &= f[1:-1] & f[:-2]
    live[:2] = False
    return k, r["cls_day"].astype("u1"), (r["cls_day"] * live).astype("u1"), r["excess"].astype("f4") * r["spell"]


def same_dates(a, b, y):
    return a + pd.DateOffset(years=y - a.year), b + pd.DateOffset(years=y - a.year)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    res_dir = os.path.join(HERE, "results")
    os.makedirs(res_dir, exist_ok=True)
    t0 = time.time()
    ev = pd.read_csv(os.path.join(HERE, "events.csv"))
    boxes = {}
    for u in ev.drop_duplicates("unit_key").itertuples():
        t = pq.read_table(f"{BND}/adm1_polygons.parquet", columns=["adm1_id", "geometry"], filters=[("adm1_id", "in", [u.unit_id])])
        assert t.num_rows == 1, u.unit_id
        g = shapely.from_wkb(t.column("geometry")[0].as_py())
        x0, y0, x1, y1 = g.bounds
        i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
        j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
        m = features.rasterize([(g, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1), transform=from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1), dtype="uint8").astype(bool)
        boxes[u.unit_key] = (i0, i1, j0, j1, m)
    for u in ev.itertuples():                                   # readout blocks, 3 by 3 around the place
        i, j = int(round((90 - u.readout_lat) / 0.1)), int(round((u.readout_lon + 180) / 0.1))
        boxes["R_" + u.event_id] = (i - 1, i + 1, j - 1, j + 1, np.ones((3, 3), bool))
    with Pool(32) as p:
        got = {(v, y): (t, r) for v, y, t, r in p.imap_unordered(read_job, [(v, y, boxes) for y in YEARS for v in VARS])}
    days = np.concatenate([got[("t2mmax", y)][0] for y in YEARS])
    assert np.array_equal(days, np.concatenate([got[("t2mmin", y)][0] for y in YEARS]))
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    print(f"read {time.time() - t0:.0f} s", flush=True)
    lat_all = 90 - 0.1 * np.arange(1801)
    out = ["Third held-out event suite. Produced by validation/heldout_suite_3/01_run.py, run once.",
           "Registered in PROTOCOL.md and events.csv before the run."]

    with Pool(48, initializer=init, initargs=(days,)) as p:
        z = np.load(CELLS)
        if not np.array_equal(z["time"], days):
            raise SystemExit("time axis of the check cells differs from the run; the equality check cannot be made, so the run does not start")
        init(days)
        chk = []
        for site in ("Paris", "Jakarta", "Verkhoyansk", "Phoenix"):
            g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
            chk.append((site, ((g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2).astype("f4").astype("f8")))
        par = {k: a for k, a, _, _ in p.imap_unordered(cell_job, chk)}
        same = [bool(np.array_equal(par[s], _D["det"].detect(tm, _D["idx"])["cls_day"].astype("u1"))) for s, tm in chk]
        out.append(f"Equality check, parallel path against the single-cell reference at 4 cells: {'IDENTICAL' if all(same) else 'DIFFERENT ' + str(same)}")
        assert all(same), "parallel path differs from the reference; the run does not start"

        def run_box(key):
            i0, i1, j0, j1, m = boxes[key]
            cat = lambda v: np.concatenate([got[(v, y)][1][key] for y in YEARS]).astype("f4")
            tx, tn = cat("t2mmax"), cat("t2mmin")
            land = tx[0] != -9999.0
            tx, tn = tx[:, land] - 273.15, tn[:, land] - 273.15
            w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1 + 1][:, None], m.shape[1], axis=1)[m][land]))
            tm = np.full_like(tx, np.nan)
            tm[:-1] = (tx[:-1] + tn[1:]) / 2
            n = tm.shape[1]
            clsl, exc = np.zeros((len(idx), n), "u1"), np.zeros((len(idx), n), "f4")
            for k, _, b, c in p.imap_unordered(cell_job, ((k, tm[:, k]) for k in range(n)), chunksize=8):
                clsl[:, k], exc[:, k] = b, c
            return clsl, exc, w / w.sum(), n

        series, rows = {}, []
        for u in ev.itertuples():
            if u.unit_key not in series:
                clsl, exc, w, n = run_box(u.unit_key)
                s = pd.DataFrame({"share_spell": (clsl >= 1) @ w, "share_sev": (clsl >= 2) @ w, "M": exc @ w}, index=idx)
                s.round(5).to_csv(f"{OUT}/{u.unit_key}_series.csv.gz")
                series[u.unit_key] = (s, n)
            s, n = series[u.unit_key]
            clsr, _, _, nr = run_box("R_" + u.event_id)
            r = pd.Series((clsr >= 2).mean(axis=1), index=idx)             # share of the block's land cells severe, live
            r.round(3).to_csv(f"{OUT}/R_{u.event_id}_series.csv.gz")
            a, b = pd.Timestamp(u.window_start), pd.Timestamp(u.window_end)
            tot, ha, hb = {}, {}, {}
            for y in range(1979, 2026):
                A, B = same_dates(a, b, y)
                tot[y] = float(s.loc[A:B].M.sum())
                ha[y] = bool(s.loc[A:B].share_sev.max() >= 0.5)
                hb[y] = bool(r.loc[A:B].max() > 0.5)
            tot = pd.Series(tot)
            top = tot.sort_values(ascending=False)
            fa, fb = s.loc[a:b].index[s.loc[a:b].share_sev >= 0.5], r.loc[a:b].index[r.loc[a:b] > 0.5]
            oa = [v for y, v in ha.items() if y != a.year]
            ob = [v for y, v in hb.items() if y != a.year]
            rows.append({"event": u.event, "unit": u.unit_name, "cells": n, "confidence": u.confidence, "window": f"{u.window_start}..{u.window_end}",
                         "max_share_spell": round(float(s.loc[a:b].share_spell.max()), 2), "max_share_sev": round(float(s.loc[a:b].share_sev.max()), 2),
                         "A": ha[a.year], "A_first_day": str(fa[0].date()) if len(fa) else "never", "A_base_rate": round(float(np.mean(oa)), 2),
                         "readout": u.readout_name, "readout_cells": nr, "max_block_sev": round(float(r.loc[a:b].max()), 2),
                         "B": hb[a.year], "B_first_day": str(fb[0].date()) if len(fb) else "never", "B_base_rate": round(float(np.mean(ob)), 2),
                         "rank": int((tot > tot[a.year]).sum()) + 1, "first_ranked_year": int(top.index[0])})
            print(u.event_id, f"{time.time() - t0:.0f} s", flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(f"{res_dir}/units.csv", index=False)
    na, nb, ma, mb = int(R.A.sum()), int(R.B.sum()), float(R.A_base_rate.median()), float(R.B_base_rate.median())
    verdict = lambda n, m: "NOT INFORMATIVE (median base rate above 0.15)" if m > 0.15 else ("ACCEPTED" if n >= 8 else "NOT ACCEPTED")
    pd.set_option("display.width", 340, "display.max_columns", 40)
    out += [f"\nA, calendar-day class at admin level: {na} of {len(R)} units severe over half their area on a window day. Median base rate {ma:.2f}. VERDICT: {verdict(na, ma)}",
            f"B, location readout: {nb} of {len(R)} places with most of the 3 by 3 block severe on a window day. Median base rate {mb:.2f}. VERDICT: {verdict(nb, mb)}",
            f"Shown by A or B: {int((R.A | R.B).sum())} of {len(R)} (description only, not a registered test).",
            "\n== All events", R.to_string(index=False),
            "\nDeviations from the protocol: none.", f"total {time.time() - t0:.0f} s"]
    txt = "\n".join(out)
    with open(f"{res_dir}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
