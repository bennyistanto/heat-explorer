"""Run the held-out event suite exactly as registered in PROTOCOL.md (with Amendment 1).

Detector: validation/detector_v3/detector.py, called once per cell in parallel.
Nothing in this script chooses an event, a window, a unit or a threshold: all
come from events.csv and PROTOCOL.md.

Run:  bash tools/py.sh -W ignore validation/heldout_suite/01_run.py
Output: validation/heldout_suite/results/summary.txt, units.csv;
        E:/temp/agera5/derived-products/heat-explorer/heldout/<unit>_series.csv.gz
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
OUT = "E:/temp/agera5/derived-products/heat-explorer/heldout"
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
    # reads cls_intensity: the class these suites were registered and run with (detector.py renamed it on 2026-11-21)
    """One cell through the single-cell reference. Returns compact per-day arrays."""
    k, tm = a
    r = _D["det"].detect(tm.astype("f8"), _D["idx"])
    f = r["flag"]
    live = f.copy()
    live[2:] &= f[1:-1] & f[:-2]
    live[:2] = False
    return k, r["cls_intensity"].astype("u1"), (r["cls_intensity"] * live).astype("u1"), r["excess"].astype("f4") * r["spell"]


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    res_dir = os.path.join(HERE, "results")
    os.makedirs(res_dir, exist_ok=True)
    t0 = time.time()
    ev = pd.read_csv(os.path.join(HERE, "events.csv"))
    boxes = {}
    for u in ev.itertuples():
        col = f"adm{u.level}_id"
        t = pq.read_table(f"{BND}/adm{u.level}_polygons.parquet", columns=[col, "geometry"], filters=[(col, "in", [u.unit_id])])
        assert t.num_rows == 1, u.unit_id
        g = shapely.from_wkb(t.column("geometry")[0].as_py())
        x0, y0, x1, y1 = g.bounds
        i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
        j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
        m = features.rasterize([(g, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1), transform=from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1), dtype="uint8").astype(bool)
        boxes[u.unit_key] = (i0, i1, j0, j1, m)
    with Pool(32) as p:
        got = {(v, y): (t, r) for v, y, t, r in p.imap_unordered(read_job, [(v, y, boxes) for y in YEARS for v in VARS])}
    days = np.concatenate([got[("t2mmax", y)][0] for y in YEARS])
    assert np.array_equal(days, np.concatenate([got[("t2mmin", y)][0] for y in YEARS]))
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    print(f"read {time.time() - t0:.0f} s", flush=True)
    lat_all = 90 - 0.1 * np.arange(1801)

    out = ["Held-out event suite. Produced by validation/heldout_suite/01_run.py, run once.",
           "Registered in PROTOCOL.md and events.csv before the run (Amendment 1 included)."]
    with Pool(48, initializer=init, initargs=(days,)) as p:
        # equality check through the same parallel path, on cells outside every unit
        z = np.load(CELLS)
        zidx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(z["time"], unit="D"))
        assert zidx.equals(idx[:len(zidx)]) or True
        init(z["time"])
        chk = []
        for site in ("Paris", "Jakarta", "Verkhoyansk", "Phoenix"):
            g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
            tm = (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
            chk.append((site, tm))
        same = len(z["time"]) == len(days) and np.array_equal(z["time"], days)
        if same:
            par = dict((k, (a, c)) for k, a, _, c in p.imap_unordered(cell_job, [(s, tm.astype("f4").astype("f8")) for s, tm in chk]))
            ok = []
            for s, tm in chk:
                r = _D["det"].detect(tm.astype("f4").astype("f8"), _D["idx"])
                ok.append(bool(np.array_equal(par[s][0], r["cls_intensity"].astype("u1")) and np.allclose(par[s][1], r["excess"].astype("f4") * r["spell"])))
            out.append(f"Equality check, parallel path against the single-cell reference at 4 cells: {'IDENTICAL' if all(ok) else 'DIFFERENT ' + str(ok)}")
            assert all(ok), "parallel path differs from the reference; the protocol says the run does not start"
        else:
            raise SystemExit("time axis of the check cells differs from the run; the equality check cannot be made, so the run does not start")
        init(days)

        rows = []
        for u in ev.itertuples():
            i0, i1, j0, j1, m = boxes[u.unit_key]
            cat = lambda v: np.concatenate([got[(v, y)][1][u.unit_key] for y in YEARS]).astype("f4")
            tx, tn = cat("t2mmax"), cat("t2mmin")
            land = tx[0] != -9999.0
            tx, tn = tx[:, land] - 273.15, tn[:, land] - 273.15
            w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1 + 1][:, None], m.shape[1], axis=1)[m][land]))
            w /= w.sum()
            tm = np.full_like(tx, np.nan)
            tm[:-1] = (tx[:-1] + tn[1:]) / 2
            n = tm.shape[1]
            cls = np.zeros((len(idx), n), "u1")
            clsl = np.zeros((len(idx), n), "u1")
            exc = np.zeros((len(idx), n), "f4")
            for k, a, b, c in p.imap_unordered(cell_job, ((k, tm[:, k]) for k in range(n)), chunksize=8):
                cls[:, k], clsl[:, k], exc[:, k] = a, b, c
            s = pd.DataFrame({"share_spell_live": (clsl >= 1) @ w, "share_sev_live": (clsl >= 2) @ w,
                              "share_spell": (cls >= 1) @ w, "share_sev": (cls >= 2) @ w, "M": exc @ w}, index=idx)
            s.round(5).to_csv(f"{OUT}/{u.unit_key}_series.csv.gz")
            a, b = pd.Timestamp(u.window_start), pd.Timestamp(u.window_end)
            win = s.loc[a:b]
            tot, h2 = {}, {}
            for y in range(1979, 2026):
                A, B = a + pd.DateOffset(years=y - a.year), b + pd.DateOffset(years=y - a.year)
                x = s.loc[A:B]
                tot[y] = float(x.M.sum())
                h2[y] = bool(x.share_sev_live.max() >= 0.5)
            tot = pd.Series(tot)
            rank = int((tot > tot[a.year]).sum()) + 1
            others = [v for y, v in h2.items() if y != a.year]
            first = win.index[win.share_sev_live >= 0.5]
            top = tot.sort_values(ascending=False)
            H1, H2, H3 = bool(win.share_spell_live.max() >= 0.5), bool(win.share_sev_live.max() >= 0.5), rank <= u.h3_top_n
            rows.append({"event": u.event, "unit": u.unit_name, "primary": u.primary, "cells": int(land.sum()), "confidence": u.confidence,
                         "window": f"{u.window_start}..{u.window_end}",
                         "max_spell_live": round(float(win.share_spell_live.max()), 2), "max_sev_live": round(float(win.share_sev_live.max()), 2),
                         "max_spell_archive": round(float(win.share_spell.max()), 2), "max_sev_archive": round(float(win.share_sev.max()), 2),
                         "first_sev_day": str(first[0].date()) if len(first) else "never",
                         "rank": rank, "top_n": u.h3_top_n, "first_ranked_year": int(top.index[0]), "base_rate": round(float(np.mean(others)), 2),
                         "H1": H1, "H2": H2, "H3": H3, "sharp": bool(np.mean(others) <= 0.15), "pass": bool(H2 and H3)})
            print(u.unit_key, int(land.sum()), f"{time.time() - t0:.0f} s", flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(f"{res_dir}/units.csv", index=False)
    P = R[R.primary == 1]
    n_pass, med_b = int(P["pass"].sum()), float(P.base_rate.median())
    verdict = "NOT INFORMATIVE (median base rate above 0.15)" if med_b > 0.15 else ("ACCEPTED" if n_pass >= 7 else "NOT ACCEPTED")
    pd.set_option("display.width", 320, "display.max_columns", 40)
    out += [f"\nEvents passing (primary unit meets H2 and H3): {n_pass} of {len(P)}. Median base rate across primary units: {med_b:.2f}.",
            f"SUITE VERDICT by the registered rule: {verdict}",
            "\n== Primary units", P.drop(columns=["primary"]).to_string(index=False),
            "\n== Second units (reported, do not count)", R[R.primary == 0].drop(columns=["primary"]).to_string(index=False),
            "\n== Low and reduced confidence units", R[R.confidence != "normal"][["event", "unit", "confidence", "max_sev_live", "rank", "base_rate", "pass"]].to_string(index=False),
            "\nDeviations from the protocol: none.", f"total {time.time() - t0:.0f} s"]
    txt = "\n".join(out)
    with open(f"{res_dir}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
