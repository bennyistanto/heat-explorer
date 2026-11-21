"""Extract AgERA5 daily series at station points for the wet-bulb gate.

Points: the ISD stations chosen by 01_download_isd.py, plus Indonesian sites
from the wxgrid compiled dataset (F:/temp/station/compiled) that have daily
maximum temperature with either 13:00 local humidity or daily mean humidity.

For each point the nearest AgERA5 cell is used; if that cell is ocean (fill),
the nearest land cell within one cell is taken and the shift is recorded.
Cell elevation is the mean ETOPO1 altitude over the 0.1 degree cell.

Raw AgERA5 is opened read-only. Points sharing a NetCDF chunk are read as one
block so each compressed chunk is decompressed once per file.

Run:  bash tools/py.sh validation/wetbulb_gate/02_extract_agera5_points.py
Output: E:/temp/agera5/derived-products/heat-explorer/wetbulb-gate/
        points.csv, agera5_points.npz
"""
import os
import time
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np
import pandas as pd

RAW = "E:/temp/agera5"
OUT = "E:/temp/agera5/derived-products/heat-explorer/wetbulb-gate"
WX = "F:/temp/station/compiled"
ISD = "E:/temp/station-isd/stations.csv"
DEM = "E:/temp/dem/etopo180_4558_b013_12d8.nc"
VARS = {
    "t2mmax": "Temperature_Air_2m_Max_24h",
    "t2mmin": "Temperature_Air_2m_Min_24h",
    "t2mmean": "Temperature_Air_2m_Mean_24h",
    "t2mdp": "Dew_Point_Temperature_2m_Mean_24h",
}
YEARS = range(1979, 2027)
CH_LAT, CH_LON = 200, 400  # chunk shape in the files (measured)


def wxgrid_sites():
    sites = pd.read_csv(f"{WX}/sites.csv")
    n = {}
    for v in ("TX", "HU13", "HU"):
        d = pd.read_csv(f"{WX}/merged_{v}.csv.gz", usecols=["site_id", "date"])
        n[v] = d[d.date >= "1979-01-01"].groupby("site_id").size()
    c = pd.concat(n, axis=1).fillna(0)
    keep = c[(c.TX >= 1000) & ((c.HU13 >= 1000) | (c.HU >= 3650))].index
    s = sites[sites.site_id.isin(keep) & (sites.country == "ID")]
    return pd.DataFrame({
        "pid": "wx:" + s.site_id, "name": s.name.values, "lat": s.lat.values,
        "lon": s.lon.values, "elev_m": s.elev_m.values, "src": "wxgrid",
    })


def isd_sites():
    s = pd.read_csv(ISD, dtype={"usaf": str, "wban": str})
    return pd.DataFrame({
        "pid": "isd:" + s.usaf + "-" + s.wban, "name": s.name.values, "lat": s.lat.values,
        "lon": s.lon.values, "elev_m": s.elev_m.values, "src": "isd",
    })


def locate(pts):
    """Nearest land cell and its ETOPO1 mean elevation."""
    d = nc.Dataset(f"{RAW}/t2mmax/agera5_t2mmax_2000.nc")
    d.set_auto_mask(False)
    land = d.variables[VARS["t2mmax"]][180] != -9999.0
    d.close()
    dem = nc.Dataset(DEM)
    alt = dem.variables["altitude"]
    rows = []
    for p in pts.itertuples():
        i0 = int(round((90 - p.lat) / 0.1))
        j0 = int(round((p.lon + 180) / 0.1)) % 3600
        best = None
        for di in (0, -1, 1):
            for dj in (0, -1, 1):
                i, j = i0 + di, (j0 + dj) % 3600
                if 0 <= i < 1801 and land[i, j]:
                    dist = np.hypot(di, dj)
                    if best is None or dist < best[2]:
                        best = (i, j, dist)
        if best is None:
            rows.append((np.nan, np.nan, np.nan, np.nan))
            continue
        i, j, dist = best
        clat, clon = 90 - i * 0.1, -180 + j * 0.1
        # ETOPO1 is south-first, 1 arc-minute, grid-registered
        a0 = int(round((clat - 0.05 + 90) * 60))
        b0 = int(round((clon - 0.05 + 180) * 60))
        blk = np.asarray(alt[a0:a0 + 7, b0:b0 + 7], dtype="f8")
        rows.append((i, j, dist, float(np.clip(blk, 0, None).mean())))
    dem.close()
    pts[["i", "j", "cell_shift", "cell_elev_m"]] = rows
    return pts.dropna(subset=["i"]).astype({"i": int, "j": int})


def job(a):
    v, y, ii, jj = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[VARS[v]]
    t = np.asarray(d.variables["time"][:])
    out = np.empty((len(t), len(ii)), "f4")
    key = (ii // CH_LAT) * 100 + (jj // CH_LON)
    for k in np.unique(key):
        m = np.where(key == k)[0]
        i0, i1, j0, j1 = ii[m].min(), ii[m].max(), jj[m].min(), jj[m].max()
        blk = np.asarray(x[:, i0:i1 + 1, j0:j1 + 1])
        out[:, m] = blk[:, ii[m] - i0, jj[m] - j0]
    d.close()
    return v, y, t, out


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    pts = locate(pd.concat([isd_sites(), wxgrid_sites()], ignore_index=True))
    pts.to_csv(f"{OUT}/points.csv", index=False)
    print(len(pts), "points;", pts.src.value_counts().to_dict(),
          "; shifted to a neighbour land cell:", int((pts.cell_shift > 0).sum()), flush=True)
    ii, jj = pts.i.values, pts.j.values
    jobs = [(v, y, ii, jj) for y in YEARS for v in VARS]
    res = {}
    with Pool(48) as p:
        for n, (v, y, t, out) in enumerate(p.imap_unordered(job, jobs)):
            res[(v, y)] = (t, out)
            if n % 24 == 0:
                print(f"{n}/{len(jobs)} files, {time.time() - t0:.0f} s", flush=True)
    save = {}
    for v in VARS:
        save[f"time_{v}"] = np.concatenate([res[(v, y)][0] for y in YEARS])
        save[v] = np.concatenate([res[(v, y)][1] for y in YEARS])
    np.savez_compressed(f"{OUT}/agera5_points.npz", pid=pts.pid.values.astype(str), **save)
    print("done", f"{time.time() - t0:.0f} s", {v: save[v].shape for v in VARS})
