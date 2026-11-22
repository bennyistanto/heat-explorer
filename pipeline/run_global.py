"""Run detector version 1.0 on every AgERA5 land cell, 1979 to the end of the record.

Reads daily maximum and minimum temperature by tile (200 rows by 400 columns,
the chunk shape of the source files, so each compressed chunk is read once),
runs pipeline/detector.py, and writes a Zarr store:

    cls_day   uint8   (time, lat, lon)   0 none, 1 heat spell, 2 severe, 3 extreme;
                                          253 not yet classed (the last two days of the record),
                                          254 land cell the detector declined, 255 no data (sea)
    excess    float16 (time, lat, lon)   excess over threshold in units of local spread
                                          on spell days (NOT part of the frozen definition)
    thr       float32 (doy, 3, lat, lon) calendar-day thresholds in deg C: 90th, 95th, 99th
    allyear   float32 (3, lat, lon)      all-year median, 95th percentile, spread (IQR)
    time      int32   days since 1900-01-01
    lat, lon  float32 cell centres

"Live" labelling is not stored: a day is live when it and the two days before
it are spell days, which can be read off cls_day.

Raw AgERA5 is opened read-only. Nothing is written inside the repository.

Run:  bash tools/py.sh -W ignore pipeline/run_global.py                (everything)
      bash tools/py.sh -W ignore pipeline/run_global.py --tiles 600:0  (chosen tiles, row:col of the top-left corner)
Options: --out PATH, --workers N
"""
import argparse
import os
import sys
import time

os.environ.setdefault("NUMBA_NUM_THREADS", "1")     # one thread per worker process; the workers are the parallelism

import netCDF4 as nc
import numpy as np
import zarr
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pipeline import detector  # noqa: E402

RAW = "E:/temp/agera5"
OUT = "E:/temp/agera5/derived-products/heat-explorer/v1/heat_state.zarr"
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(1979, 2027)
NLAT, NLON, TR, TC = 1801, 3600, 200, 400
TCHUNK = 64
TAIL = 2              # days at the end of the record that cannot be classed yet
BLOCK = 6000          # cells per call to the detector
_G = {}


def time_axis():
    out = []
    for y in YEARS:
        d = nc.Dataset(f"{RAW}/t2mmax/agera5_t2mmax_{y}.nc")
        out.append(np.asarray(d.variables["time"][:]))
        d.close()
    return np.concatenate(out)


def read_tile(v, r0, r1, c0, c1, land=None):
    parts, tt = [], []
    for y in YEARS:
        d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
        d.set_auto_mask(False)
        x = np.asarray(d.variables[VARS[v]][:, r0:r1, c0:c1])
        tt.append(np.asarray(d.variables["time"][:]))
        d.close()
        if land is None:
            land = x[0] != -9999.0
            if not land.any():
                return None, land, None
        parts.append(x[:, land])
    return np.concatenate(parts), land, np.concatenate(tt)


def init(out, days):
    _G["z"] = zarr.open_group(out, mode="r+")
    _G["days"] = days


def tile_job(a):
    r0, c0 = a
    r1, c1 = min(r0 + TR, NLAT), min(c0 + TC, NLON)
    t0 = time.time()
    tx, land, tt = read_tile("t2mmax", r0, r1, c0, c1)
    if tx is None:
        return r0, c0, 0, 0, None, time.time() - t0
    days = _G["days"]
    assert np.array_equal(tt, days), "time axis of t2mmax differs from the store"
    tn, _, tt2 = read_tile("t2mmin", r0, r1, c0, c1, land)
    assert np.array_equal(tt2, days), "time axis of t2mmin differs from the store"
    bad = (tx < 100.0) | (tn < 100.0)                       # fill values inside a land cell's record
    tx, tn = tx - np.float32(273.15), tn - np.float32(273.15)
    tm = np.full_like(tx, np.nan)
    tm[:-1] = (tx[:-1] + tn[1:]) / 2
    tm[:-1][bad[:-1] | bad[1:]] = np.nan
    del tx, tn, bad
    n, nt = tm.shape[1], len(days)
    cls = np.full((nt, n), 254, "u1")
    exc = np.zeros((nt, n), "f2")
    thr = np.full((365, 3, n), np.nan, "f4")
    ally = np.full((3, n), np.nan, "f4")
    okc = np.zeros(n, bool)
    for b0 in range(0, n, BLOCK):
        sl = slice(b0, min(b0 + BLOCK, n))
        r = detector.detect_block(tm[:, sl], days, thresholds=True)
        k = r["ok"]
        okc[sl] = k
        c = r["cls_day"]
        c[:, ~k] = 254
        cls[:, sl], exc[:, sl], thr[:, :, sl], ally[:, sl] = c, r["excess"].astype("f2"), r["thr"], r["allyear"]
    # the centred 3-day mean of day d needs Tmin of day d+2: the last two days cannot be classed yet
    tail = cls[-TAIL:]
    tail[tail <= 3] = 253
    del tm
    shape = (r1 - r0, c1 - c0)
    z = _G["z"]
    dense = np.full((nt,) + shape, 255, "u1")
    dense[:, land] = cls
    z["cls_day"][:, r0:r1, c0:c1] = dense
    dense = np.full((nt,) + shape, np.nan, "f2")
    dense[:, land] = exc
    z["excess"][:, r0:r1, c0:c1] = dense
    del dense
    d4 = np.full((365, 3) + shape, np.nan, "f4")
    d4[:, :, land] = thr
    z["thr"][:, :, r0:r1, c0:c1] = d4
    d3 = np.full((3,) + shape, np.nan, "f4")
    d3[:, land] = ally
    z["allyear"][:, r0:r1, c0:c1] = d3
    # per-cell summaries for the run report: days per year by period
    import pandas as pd
    yr = (pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D")).year.values
    b, rc = (yr >= 1991) & (yr <= 2020), (yr >= 2021) & (yr <= 2025)
    summ = np.full((4,) + shape, np.nan, "f4")
    ok2 = cls[0] != 254
    for i, (m, ny, lev) in enumerate(((b, 30, 1), (b, 30, 2), (rc, 5, 1), (rc, 5, 2))):
        v = ((cls[m] >= lev) & (cls[m] <= 3)).sum(axis=0) / ny
        s2 = np.full(shape, np.nan, "f4")
        s2[land] = np.where(ok2, v, np.nan)
        summ[i] = s2
    return r0, c0, int(n), int((~okc).sum()), summ, time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--tiles", default="")
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()
    t0 = time.time()
    days = time_axis()
    nt = len(days)
    tiles = [(r, c) for r in range(0, NLAT, TR) for c in range(0, NLON, TC)]
    if a.tiles:
        tiles = [tuple(int(v) for v in t.split(":")) for t in a.tiles.split(",")]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    comp = zarr.codecs.BloscCodec(cname="zstd", clevel=3, shuffle=zarr.codecs.BloscShuffle.shuffle)
    if not os.path.exists(a.out):
        g = zarr.open_group(a.out, mode="w")
        g.create_array("cls_day", shape=(nt, NLAT, NLON), chunks=(TCHUNK, TR, TC), dtype="u1", fill_value=255, compressors=comp)
        g.create_array("excess", shape=(nt, NLAT, NLON), chunks=(TCHUNK, TR, TC), dtype="f2", fill_value=np.nan, compressors=comp)
        g.create_array("thr", shape=(365, 3, NLAT, NLON), chunks=(365, 3, TR, TC), dtype="f4", fill_value=np.nan, compressors=comp)
        g.create_array("allyear", shape=(3, NLAT, NLON), chunks=(3, TR, TC), dtype="f4", fill_value=np.nan, compressors=comp)
        for name, arr in (("time", days.astype("i4")), ("lat", (90 - 0.1 * np.arange(NLAT)).astype("f4")), ("lon", (-180 + 0.1 * np.arange(NLON)).astype("f4"))):
            g.create_array(name, shape=arr.shape, chunks=arr.shape, dtype=arr.dtype)[:] = arr
        g.attrs.update({"detector_version": detector.VERSION, "definition": "docs/detector-v1-frozen.md", "source": "AgERA5 t2mmax, t2mmin",
                        "baseline": "1991-2020", "time_units": "days since 1900-01-01", "cls_day_codes": "0 none, 1 heat spell, 2 severe, 3 extreme, 253 not yet classed (the last days of the record), 254 declined, 255 no data", "unclassed_tail_days": TAIL,
                        "thr_axis1": "calendar-day 90th, 95th, 99th percentile threshold of the 3-day mean, deg C", "allyear_axis0": "all-year median, 95th percentile, IQR of baseline anomalies",
                        "excess_note": "not part of the frozen definition"})
    summ = np.full((4, NLAT, NLON), np.nan, "f4")
    n_land = n_bad = 0
    with Pool(a.workers, initializer=init, initargs=(a.out, days)) as p:
        for k, (r0, c0, n, nb, s, dt) in enumerate(p.imap_unordered(tile_job, tiles)):
            n_land += n
            n_bad += nb
            if s is not None:
                summ[:, r0:r0 + s.shape[1], c0:c0 + s.shape[2]] = s
            print(f"tile {r0}:{c0} cells {n} declined {nb} {dt:.0f} s  [{k + 1}/{len(tiles)}] elapsed {time.time() - t0:.0f} s", flush=True)
    np.savez_compressed(os.path.join(os.path.dirname(a.out), "run_summary_" + ("part" if a.tiles else "global") + ".npz"), days_per_year=summ,
                        names=np.array(["spell 1991-2020", "severe+ 1991-2020", "spell 2021-2025", "severe+ 2021-2025"]))
    print(f"DONE cells {n_land} declined {n_bad} total {time.time() - t0:.0f} s -> {a.out}", flush=True)
