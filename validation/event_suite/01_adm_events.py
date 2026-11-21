"""Admin-level event suite for the tuned heat spell detector.

Runs the candidate detector (references/indicators.md, signal 1, tuning of
2026-11-21) on every AgERA5 cell of selected admin units over the full record,
aggregates by area, and checks documented heat events.

Detector (per cell, on Tm = (Tmax(d) + Tmin(d+1)) / 2, baseline 1991-2020)
  t3      = 3-day mean centred on the day
  flagged = t3 above its calendar-day p90 (15-day window, seasonal cycle removed)
            and above the all-year median, OR t3 above the all-year p95
  excess  = larger of the two exceedances, divided by the IQR of baseline anomalies
  event   = run of flagged days; magnitude = summed excess
  class   = spell / severe / extreme by the 80th and 95th percentile of the
            cell's baseline event magnitudes
  Two threshold versions: "fixed" (raw series) and "moving" (the cell's linear
  trend of annual mean Tm over 1979-2025 removed first).

Admin measures (cos-latitude weighted over the unit's cells)
  share_sev(t) = share of land area in a severe or extreme event on day t
  M(t)         = area mean of daily excess (zero where not flagged)

PASS CRITERIA, written before the run and not to be edited after it:
  P1  share_sev reaches 0.50 on at least one day of the event window
  P2  the highest 5-day running mean of M inside the window ranks in the top 3
      when compared with the annual maximum of that 5-day mean in every other
      year 1979-2025 (rank 1 = no other year had a higher 5-day peak)
  An event passes if P1 and P2 both hold under the "moving" thresholds, which
  is the version proposed for event detection. "fixed" is reported beside it.

Event windows are the ones used in the 2026-11-20 critique, plus Karachi 2015.
The windows are from memory of published accounts and have not been checked
against a primary source. Humid-heat cases are not in this run.

A cell belongs to a unit when its centre is inside the polygon (rasterised
from the full-resolution boundary). Russia's adm1 level in this boundary set
is the federal district, so the two Russian units are taken from adm2.

Run:  bash tools/py.sh -W ignore validation/event_suite/01_adm_events.py
Output: validation/event_suite/results/ and
        E:/temp/agera5/derived-products/heat-explorer/event-suite/ (admin series)
"""
import os
import time
from multiprocessing import Pool

import netCDF4 as nc
import numba
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
from rasterio import features
from rasterio.transform import from_origin

RAW = "E:/temp/agera5"
BND = "E:/temp/boundaries"
OUT = "E:/temp/agera5/derived-products/heat-explorer/event-suite"
HERE = os.path.dirname(os.path.abspath(__file__))
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(1979, 2027)

UNITS = {  # key: (level, id, label)
    "IDF": (1, "FRA-20230119-13", "Ile-de-France"),
    "MOS": (2, "RUS-20231023-1-09", "Moskva oblast"),
    "TEL": (1, "IND-20230119-32", "Telangana"),
    "AND": (1, "IND-20230119-02", "Andhra Pradesh"),
    "SIN": (1, "PAK-20230404-7", "Sindh"),
    "RAJ": (1, "IND-20230119-29", "Rajasthan"),
    "DEL": (1, "IND-20230119-08", "Delhi"),
    "ORE": (1, "USA-20230119-41", "Oregon"),
    "WAS": (1, "USA-20230119-53", "Washington"),
    "BRC": (1, "CAN-20230119-02", "British Columbia"),
    "NSW": (1, "AUS-20230119-2", "New South Wales"),
    "SAK": (2, "RUS-20231023-2-07", "Sakha"),
}
EVENTS = [("Europe Aug 2003", "IDF", "2003-08-01", "2003-08-15"),
          ("Russia 2010", "MOS", "2010-07-10", "2010-08-20"),
          ("India May 2015", "TEL", "2015-05-18", "2015-06-03"),
          ("India May 2015", "AND", "2015-05-18", "2015-06-03"),
          ("Karachi Jun 2015", "SIN", "2015-06-17", "2015-06-24"),
          ("India-Pakistan 2022", "SIN", "2022-03-10", "2022-05-20"),
          ("India-Pakistan 2022", "RAJ", "2022-03-10", "2022-05-20"),
          ("India-Pakistan 2022", "DEL", "2022-03-10", "2022-05-20"),
          ("Pacific NW Jun 2021", "ORE", "2021-06-25", "2021-07-01"),
          ("Pacific NW Jun 2021", "WAS", "2021-06-25", "2021-07-01"),
          ("Pacific NW Jun 2021", "BRC", "2021-06-25", "2021-07-01"),
          ("SE Australia 2019-20", "NSW", "2019-12-15", "2020-02-05"),
          ("Siberia Jun 2020", "SAK", "2020-06-15", "2020-06-30")]


def unit_masks():
    """Cell-centre masks on the AgERA5 grid, as bounding box plus boolean block."""
    out = {}
    for lvl in (1, 2):
        ids = [u[1] for u in UNITS.values() if u[0] == lvl]
        col = f"adm{lvl}_id"
        t = pq.read_table(f"{BND}/adm{lvl}_polygons.parquet", columns=[col, "geometry"], filters=[(col, "in", ids)])
        for uid, wkb in zip(t.column(col).to_pylist(), t.column("geometry").to_pylist()):
            key = [k for k, u in UNITS.items() if u[1] == uid][0]
            g = shapely.from_wkb(wkb)
            x0, y0, x1, y1 = g.bounds
            i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
            j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
            i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(i1, 1800), min(j1, 3599)
            # pixel (i, j) is centred on lat 90 - 0.1 i, lon -180 + 0.1 j
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


def doy365(idx):
    d = idx.dayofyear.values.copy()
    d[idx.is_leap_year & (d >= 60)] -= 1
    return d


def cal_p90(t3, idx):
    """Calendar-day p90 of t3 with the seasonal cycle removed; also clim-based outputs."""
    doy = doy365(idx)
    keep = (idx.year >= 1991) & (idx.year <= 2020) & ~((idx.month == 2) & (idx.day == 29))
    b = t3[keep].reshape(30, 365, -1)
    clim = np.nanmean(b, axis=0)
    w = np.concatenate([clim[-15:], clim, clim[:15]])
    cs = np.cumsum(np.concatenate([np.zeros((1, w.shape[1]), w.dtype), w]), axis=0)
    clim = ((cs[31:] - cs[:-31]) / 31.0).astype("f4")            # centred 31-day mean, 365 rows
    an = b - clim[None]
    p90 = np.empty_like(clim)
    for d in range(365):
        p90[d] = np.nanpercentile(an[:, (d + np.arange(-7, 8)) % 365].reshape(450, -1), 90, axis=0)
    q25, q75 = np.nanpercentile(an.reshape(30 * 365, -1), [25, 75], axis=0)
    return (clim + p90)[doy - 1], (q75 - q25).astype("f4")


@numba.njit(parallel=True, cache=True)
def classify(flag, exc, base_day):
    """Per cell: runs of flagged days, magnitudes, class per day (1 spell, 2 severe, 3 extreme)."""
    T, N = flag.shape
    cls = np.zeros((T, N), np.uint8)
    for j in numba.prange(N):
        starts = np.empty(T // 2 + 2, np.int64)
        ends = np.empty(T // 2 + 2, np.int64)
        mags = np.empty(T // 2 + 2, np.float64)
        n = 0
        t = 0
        while t < T:
            if flag[t, j]:
                s = t
                m = 0.0
                while t < T and flag[t, j]:
                    m += exc[t, j]
                    t += 1
                starts[n] = s
                ends[n] = t - 1
                mags[n] = m
                n += 1
            else:
                t += 1
        nb = 0
        bm = np.empty(n, np.float64)
        for k in range(n):
            if base_day[starts[k]]:
                bm[nb] = mags[k]
                nb += 1
        if nb < 5:
            continue
        srt = np.sort(bm[:nb])
        q80 = srt[min(nb - 1, int(0.80 * nb))]
        q95 = srt[min(nb - 1, int(0.95 * nb))]
        for k in range(n):
            c = 1
            if mags[k] >= q80:
                c = 2
            if mags[k] >= q95:
                c = 3
            for u in range(starts[k], ends[k] + 1):
                cls[u, j] = c
    return cls


def detect(tm, idx, moving):
    tm = tm.copy()
    if moving:
        yr = idx.year.values
        yrs = np.arange(1979, 2026)
        ann = np.stack([np.nanmean(tm[yr == y], axis=0) for y in yrs])
        slope = np.polyfit(yrs.astype("f8"), ann.astype("f8"), 1)[0].astype("f4")
        tt = (yr + (idx.dayofyear.values - 0.5) / 365.25 - 2006.0).astype("f4")
        tm -= tt[:, None] * slope[None, :]
    t3 = np.full_like(tm, np.nan)
    t3[1:-1] = (tm[:-2] + tm[1:-1] + tm[2:]) / 3
    thr, iqr = cal_p90(t3, idx)
    base = (idx.year >= 1991) & (idx.year <= 2020)
    p50, p95 = np.nanpercentile(t3[base], [50, 95], axis=0)
    ok = np.isfinite(t3)
    flag = ok & (((t3 > thr) & (t3 > p50)) | (t3 > p95))
    exc = np.where(flag, np.fmax((t3 - thr) / iqr, (t3 - p95) / iqr), 0).astype("f4")
    cls = classify(flag, exc, np.asarray(base))
    return cls, exc


def run5(x):
    c = np.cumsum(np.concatenate([[0.0], x]))
    r = np.full(len(x), np.nan)
    r[4:] = (c[5:] - c[:-5]) / 5
    return r


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    res_dir = os.path.join(HERE, "results")
    os.makedirs(res_dir, exist_ok=True)
    t0 = time.time()
    boxes = unit_masks()
    print({k: int(b[4].sum()) for k, b in boxes.items()}, f"masks {time.time() - t0:.0f} s", flush=True)

    jobs = [(v, y, boxes) for y in YEARS for v in VARS]
    got = {}
    with Pool(32) as p:
        for n, (v, y, t, r) in enumerate(p.imap_unordered(job, jobs)):
            got[(v, y)] = (t, r)
            if n % 16 == 0:
                print(f"read {n}/{len(jobs)} {time.time() - t0:.0f} s", flush=True)
    tx_t = np.concatenate([got[("t2mmax", y)][0] for y in YEARS])
    tn_t = np.concatenate([got[("t2mmin", y)][0] for y in YEARS])
    assert np.array_equal(tx_t, tn_t), "t2mmax and t2mmin time axes differ"
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(tx_t, unit="D"))
    lat_all = 90 - 0.1 * np.arange(1801)

    rows, meta = [], []
    for key, (i0, i1, j0, j1, m) in boxes.items():
        t1 = time.time()
        cat = lambda v: np.concatenate([got[(v, y)][1][key] for y in YEARS]).astype("f4")
        tx, tn = cat("t2mmax"), cat("t2mmin")
        land = (tx[0] != -9999.0)
        tx, tn = tx[:, land] - 273.15, tn[:, land] - 273.15
        w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1 + 1][:, None], m.shape[1], axis=1)[m][land]))
        w = w / w.sum()
        tm = np.full_like(tx, np.nan)
        tm[:-1] = (tx[:-1] + tn[1:]) / 2
        ser = {"date": idx}
        for name, moving in (("fixed", False), ("moving", True)):
            cls, exc = detect(tm, idx, moving)
            ser[f"share_any_{name}"] = (cls >= 1) @ w
            ser[f"share_sev_{name}"] = (cls >= 2) @ w
            ser[f"M_{name}"] = exc @ w
            del cls, exc
        s = pd.DataFrame(ser).set_index("date")
        s.round(5).to_csv(f"{OUT}/{key}_series.csv.gz")
        meta.append({"unit": key, "label": UNITS[key][2], "cells_in_polygon": int(m.sum()), "land_cells": int(land.sum())})
        for ev, k2, a, b in EVENTS:
            if k2 != key:
                continue
            r = {"event": ev, "unit": UNITS[key][2], "land_cells": int(land.sum())}
            for name in ("fixed", "moving"):
                win = s.loc[a:b]
                m5 = pd.Series(run5(s[f"M_{name}"].values), index=s.index)
                peak = m5.loc[a:b].max()
                ann = m5.groupby(m5.index.year).max().loc[1979:2025]
                ey = sorted({pd.Timestamp(a).year, pd.Timestamp(b).year})
                rank = int((ann.drop(ey) > peak).sum() + 1)
                r.update({f"max_share_sev_{name}": win[f"share_sev_{name}"].max(),
                          f"days_share_ge50_{name}": int((win[f"share_sev_{name}"] >= 0.5).sum()),
                          f"max_share_any_{name}": win[f"share_any_{name}"].max(),
                          f"rank_{name}": rank,
                          f"P1_{name}": bool(win[f"share_sev_{name}"].max() >= 0.5), f"P2_{name}": rank <= 3})
                r[f"pass_{name}"] = r[f"P1_{name}"] and r[f"P2_{name}"]
            r["window_days"] = len(win)
            rows.append(r)
        print(key, int(land.sum()), "cells", f"{time.time() - t1:.0f} s", flush=True)

    ev = pd.DataFrame(rows)
    ev.round(3).to_csv(f"{res_dir}/events.csv", index=False)
    pd.DataFrame(meta).to_csv(f"{res_dir}/units.csv", index=False)
    pd.set_option("display.width", 250)
    cols = ["event", "unit", "land_cells", "window_days"]
    out = ["Admin-level event suite. Produced by validation/event_suite/01_adm_events.py",
           "P1: severe-or-extreme share reaches 0.50 in the window. P2: 5-day peak of area-mean excess ranks top 3 of the years 1979-2025.",
           "\n== Moving thresholds (the version proposed for event detection)",
           ev[cols + ["max_share_sev_moving", "days_share_ge50_moving", "max_share_any_moving", "rank_moving", "P1_moving", "P2_moving", "pass_moving"]].round(2).to_string(index=False),
           "\n== Fixed 1991-2020 thresholds",
           ev[cols + ["max_share_sev_fixed", "days_share_ge50_fixed", "max_share_any_fixed", "rank_fixed", "P1_fixed", "P2_fixed", "pass_fixed"]].round(2).to_string(index=False),
           f"\nPassed: moving {int(ev.pass_moving.sum())} of {len(ev)}; fixed {int(ev.pass_fixed.sum())} of {len(ev)}",
           f"total {time.time() - t0:.0f} s"]
    txt = "\n".join(out)
    with open(f"{res_dir}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
