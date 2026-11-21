"""Humid-heat cases, and Karachi 2015 at district level.

Runs the tuned detector of 01_adm_events.py twice on each unit:
  dry   : on Tm = (Tmax(d) + Tmin(d+1)) / 2, exactly as in 01
  humid : on Tw_day, the wet-bulb from Tmax(d), daily mean dewpoint and
          pressure from the cell's ETOPO1 mean elevation (solver of
          validation/wetbulb_gate/03_compare.py). Same rule, same baseline.

Events and windows (sources in references/sources.md, search summaries only):
  Karachi Jun 2015 : 17 to 24 Jun 2015. Units: the six Karachi districts
                     together (adm2), and Sindh (adm1) for comparison.
  Gulf Jul 2015    : Bandar Mahshahr heat index peak on 30 and 31 Jul 2015.
                     Window 29 Jul to 2 Aug (2 days of margin, my choice).
                     Units: Mahshahr district (adm2), Khuzestan (adm1).
  Bengal Apr 2023  : World Weather Attribution analysed 17 to 20 Apr 2023 over
                     India and Bangladesh; Dhaka record on 15 Apr. Window 15 to
                     22 Apr (my choice). Units: Dhaka division, West Bengal.

TESTS, written on 2026-11-21 BEFORE the first run (definitions as in 01 to 03):
  P1  share_sev reaches 0.50 on a window day.
  P2b the largest admin event overlapping the window is at or above the 95th
      percentile of admin events starting 1991-2020 (02_event_rank.py).
  S   the window total of M ranks in the top 3 against the same calendar
      window in the other years (03_season_total.py).
  A humid case passes if P1 and P2b hold for the HUMID detector under moving
  thresholds. S, the dry detector and fixed thresholds are reported beside it.

Questions for Karachi, stated in advance:
  K1  does the district unit rank the event higher than Sindh does (dry)?
  K2  does the humid detector rank it higher than the dry detector?

Known limits before the run: AgERA5 Tw_day is low against stations in absolute
terms, on the Gulf coast because the humid peak is not at the hour of maximum
temperature (wet-bulb gate, failed). This run tests only whether the RELATIVE
signal is there. Karachi and Mahshahr are small units, below the 30-cell floor
proposed for publishing area shares. Not blind: I know the dry result for Sindh.

Run:  bash tools/py.sh -W ignore validation/event_suite/05_humid_cases.py
Output: validation/event_suite/results/humid_summary.txt, humid_events.csv;
        series in E:/temp/agera5/derived-products/heat-explorer/event-suite/
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
DEM = "E:/temp/dem/etopo180_4558_b013_12d8.nc"
OUT = "E:/temp/agera5/derived-products/heat-explorer/event-suite"
HERE = os.path.dirname(os.path.abspath(__file__))
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h",
        "t2mdp": "Dew_Point_Temperature_2m_Mean_24h"}
YEARS = range(1979, 2027)

UNITS = {  # key: (level, [ids], label)
    "KHI": (2, ["PAK-20230404-7-02", "PAK-20230404-7-04", "PAK-20230404-7-12", "PAK-20230404-7-14",
                "PAK-20230404-7-21", "PAK-20230404-7-29"], "Karachi (6 districts)"),
    "SIN": (1, ["PAK-20230404-7"], "Sindh"),
    "MAH": (2, ["IRN-20230404-15-07"], "Mahshahr district"),
    "KHZ": (1, ["IRN-20230404-15"], "Khuzestan"),
    "DHA": (1, ["BGD-20230404-3"], "Dhaka division"),
    "WBG": (1, ["IND-20230119-36"], "West Bengal"),
}
EVENTS = [("Karachi Jun 2015", "KHI", "2015-06-17", "2015-06-24"),
          ("Karachi Jun 2015", "SIN", "2015-06-17", "2015-06-24"),
          ("Gulf Jul 2015", "MAH", "2015-07-29", "2015-08-02"),
          ("Gulf Jul 2015", "KHZ", "2015-07-29", "2015-08-02"),
          ("Bengal Apr 2023", "DHA", "2023-04-15", "2023-04-22"),
          ("Bengal Apr 2023", "WBG", "2023-04-15", "2023-04-22")]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def unit_masks():
    out = {}
    for key, (lvl, ids, _) in UNITS.items():
        col = f"adm{lvl}_id"
        t = pq.read_table(f"{BND}/adm{lvl}_polygons.parquet", columns=[col, "geometry"], filters=[(col, "in", ids)])
        assert t.num_rows == len(ids), key
        g = shapely.union_all([shapely.from_wkb(w) for w in t.column("geometry").to_pylist()])
        x0, y0, x1, y1 = g.bounds
        i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
        j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
        tr = from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1)
        m = features.rasterize([(g, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1), transform=tr, dtype="uint8").astype(bool)
        out[key] = (i0, i1, j0, j1, m)
    return out


def job(a):
    v, y, boxes = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[VARS[v]]
    t = np.asarray(d.variables["time"][:])
    res = {k: np.asarray(x[:, i0:i1 + 1, j0:j1 + 1])[:, m] for k, (i0, i1, j0, j1, m) in boxes.items()}
    d.close()
    return v, y, t, res


def cell_elev(i0, i1, j0, j1, m):
    """ETOPO1 mean altitude over each 0.1 degree cell (south-first, 1 arc-minute)."""
    dem = nc.Dataset(DEM)
    alt = dem.variables["altitude"]
    ii, jj = np.nonzero(m)
    out = np.empty(len(ii))
    for n, (i, j) in enumerate(zip(ii + i0, jj + j0)):
        clat, clon = 90 - 0.1 * i, -180 + 0.1 * j
        a0, b0 = int(round((clat - 0.05 + 90) * 60)), int(round((clon - 0.05 + 180) * 60))
        out[n] = np.clip(np.asarray(alt[a0:a0 + 7, b0:b0 + 7], dtype="f8"), 0, None).mean()
    dem.close()
    return out


if __name__ == "__main__":
    a1 = load("adm01", os.path.join(HERE, "01_adm_events.py"))
    r2 = load("rank02", os.path.join(HERE, "02_event_rank.py"))
    c3 = load("cmp03", os.path.join(HERE, "..", "wetbulb_gate", "03_compare.py"))
    res_dir = os.path.join(HERE, "results")
    t0 = time.time()
    boxes = unit_masks()
    print({k: int(b[4].sum()) for k, b in boxes.items()}, flush=True)
    jobs = [(v, y, boxes) for y in YEARS for v in VARS]
    got = {}
    with Pool(32) as p:
        for v, y, t, r in p.imap_unordered(job, jobs):
            got[(v, y)] = (t, r)
    print(f"read {time.time() - t0:.0f} s", flush=True)
    tt = {v: np.concatenate([got[(v, y)][0] for y in YEARS]) for v in VARS}
    n = min(len(x) for x in tt.values())
    assert all(np.array_equal(x[:n], tt["t2mmax"][:n]) for x in tt.values()), "time axes differ"
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(tt["t2mmax"][:n], unit="D"))
    lat_all = 90 - 0.1 * np.arange(1801)

    rows, meta = [], []
    for key, (i0, i1, j0, j1, m) in boxes.items():
        cat = lambda v: np.concatenate([got[(v, y)][1][key] for y in YEARS]).astype("f4")[:n]
        tx, tn, td = cat("t2mmax"), cat("t2mmin"), cat("t2mdp")
        land = (tx[0] != -9999.0)
        fix = lambda x: np.where(x[:, land] < 100.0, np.nan, x[:, land] - 273.15).astype("f4")
        tx, tn, td = fix(tx), fix(tn), fix(td)
        elev = cell_elev(i0, i1, j0, j1, m)[land]
        w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1 + 1][:, None], m.shape[1], axis=1)[m][land]))
        w = w / w.sum()
        tm = np.full_like(tx, np.nan)
        tm[:-1] = (tx[:-1] + tn[1:]) / 2
        tw = c3.wetbulb(tx, c3.esat(np.minimum(td, tx)), c3.pressure(elev)[None, :]).astype("f4")
        ser = {"date": idx}
        for det, x in (("dry", tm), ("humid", tw)):
            for name, moving in (("fixed", False), ("moving", True)):
                cls, exc = a1.detect(x, idx, moving)
                ser[f"share_any_{det}_{name}"] = (cls >= 1) @ w
                ser[f"share_sev_{det}_{name}"] = (cls >= 2) @ w
                ser[f"M_{det}_{name}"] = exc @ w
        s = pd.DataFrame(ser).set_index("date")
        s.round(5).to_csv(f"{OUT}/{key}_dryhumid_series.csv.gz")
        meta.append((key, int(land.sum()), float(elev.mean())))
        for ev, k2, d0, d1 in EVENTS:
            if k2 != key:
                continue
            a, b = pd.Timestamp(d0), pd.Timestamp(d1)
            for det in ("dry", "humid"):
                for name in ("moving", "fixed"):
                    sfx = f"{det}_{name}"
                    evs = r2.admin_events(s[f"share_any_{sfx}"], s[f"M_{sfx}"])
                    base = evs[(evs.start.dt.year >= 1991) & (evs.start.dt.year <= 2020)]
                    thr = float(np.percentile(base.mag, 95)) if len(base) else np.nan
                    hit = evs[(evs.end >= a) & (evs.start <= b)]
                    mag = float(hit.mag.max()) if len(hit) else 0.0
                    mser = s[f"M_{sfx}"].fillna(0)
                    tot = pd.Series({y: float(mser.loc[a + pd.DateOffset(years=y - a.year):b + pd.DateOffset(years=y - a.year)].sum())
                                     for y in range(1979, 2026)})
                    p1 = bool(s.loc[d0:d1, f"share_sev_{sfx}"].max() >= 0.5)
                    p2b = bool(len(hit) and mag >= thr)
                    rows.append({"event": ev, "unit": UNITS[key][2], "cells": int(land.sum()), "detector": det, "thresholds": name,
                                 "max_share_sev": round(float(s.loc[d0:d1, f"share_sev_{sfx}"].max()), 2),
                                 "max_share_any": round(float(s.loc[d0:d1, f"share_any_{sfx}"].max()), 2),
                                 "event_mag": round(mag, 1), "p95": round(thr, 1),
                                 "event_rank": int((evs.mag > mag).sum()) + 1 if len(hit) else None, "n_events": len(evs),
                                 "window_rank": int((tot > tot[a.year]).sum()) + 1,
                                 "window_top3": " ".join(f"{y}:{x:.1f}" for y, x in tot.sort_values(ascending=False).head(3).items()),
                                 "P1": p1, "P2b": p2b, "S": bool((tot > tot[a.year]).sum() + 1 <= 3), "pass": p1 and p2b})
        print(key, int(land.sum()), "cells", f"{time.time() - t0:.0f} s", flush=True)

    t = pd.DataFrame(rows)
    t.to_csv(f"{res_dir}/humid_events.csv", index=False)
    pd.set_option("display.width", 320, "display.max_columns", 40, "display.max_colwidth", 50)
    out = ["Humid cases and Karachi at district level. Produced by validation/event_suite/05_humid_cases.py",
           "P1 share_sev >= 0.50 in window; P2b event at or above the 95th percentile of baseline admin events; S window total in top 3.",
           "Units (land cells, mean elevation m): " + "; ".join(f"{UNITS[k][2]} {c}, {e:.0f}" for k, c, e in meta)]
    for name in ("moving", "fixed"):
        out.append(f"\n== {name} thresholds")
        out.append(t[t.thresholds == name].drop(columns="thresholds").to_string(index=False))
    q = t[(t.detector == "humid") & (t.thresholds == "moving")]
    out.append(f"\nHumid detector, moving thresholds, P1 and P2b: {int(q['pass'].sum())} of {len(q)}")
    out.append(f"total {time.time() - t0:.0f} s")
    txt = "\n".join(out)
    with open(f"{res_dir}/humid_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
