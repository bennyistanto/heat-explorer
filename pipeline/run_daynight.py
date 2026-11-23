"""Hot days and hot nights: share of each country and province, recent days.

Definition (references/indicators.md, Signal 3; a project definition, NOT part
of frozen detector version 1.0 and not tested on events):

    hot day    daily maximum above its calendar-day 90th percentile
    hot night  daily minimum of the same calendar day above its calendar-day 90th percentile
    percentile 1991-2020, days within 7 days of the calendar day, taken on the
               value minus the mean seasonal cycle (31-day smoothed) and added back
    warm season, per cell: calendar days whose mean seasonal cycle of
               (max + min) / 2 is above that cell's median over the year

For each day the page can show (pipeline/periods.py: the last 365 days and the
days of the listed past events), and each country and province, the share of
land area (cos-latitude weights) that was:
    0 hot by day only, 1 hot by night only, 2 hot by day and night   (cells inside their warm season)
    3 hot by day or night outside the warm season ("warm spell", not counted as heat)

Only the years needed are read: the baseline and the years holding those days.
Raw AgERA5 is opened read-only. Output, outside the repository:
    E:/temp/agera5/derived-products/heat-explorer/v1/admin/daynight.npz
        days (n,) int32 days since 1900-01-01; adm0, adm1 uint16 (4, n, units), share x 10000, 65535 no land cell
        base_rate: in-baseline share of days flagged hot, median over tiles (should be near 0.10)

Run:  bash tools/py.sh -W ignore pipeline/run_daynight.py            (everything)
      bash tools/py.sh -W ignore pipeline/run_daynight.py 600:0      (one tile, prints its numbers, writes nothing)
"""
import os
import sys
import time
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np
import pandas as pd
import zarr
from scipy import sparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import periods as PER  # noqa: E402
import rawfiles  # noqa: E402

RAW = "E:/temp/agera5"
V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
BASE = (1991, 2020)
NLAT, NLON, TR, TC = 1801, 3600, 200, 400
LEVELS = ("adm0", "adm1")
_G = {}


def doy365(idx):
    d = idx.dayofyear.values.copy()
    d[idx.is_leap_year & (d >= 60)] -= 1
    return d


def cal_p90(x, doy, half=7, win=31):
    """Calendar-day 90th percentile with the seasonal cycle removed. x (baseline days, cells). Returns threshold and cycle, (365, cells)."""
    c = pd.DataFrame(x).groupby(doy).mean().reindex(range(1, 366)).interpolate(limit_direction="both")
    h = win // 2
    clim = pd.concat([c.iloc[-h:], c, c.iloc[:h]]).rolling(win, center=True).mean().iloc[h:-h].values.astype("f4")
    ab = x - clim[doy - 1]
    out = np.empty((365, x.shape[1]), "f4")
    for d in range(1, 366):
        dist = np.abs(doy - d)
        out[d - 1] = np.percentile(ab[np.minimum(dist, 365 - dist) <= half], 90, axis=0)
    return clim + out, clim


def read(v, years, r0, r1, c0, c1, land=None):
    parts, tt = [], []
    for path in rawfiles.files(v, years):
        d = nc.Dataset(path)
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


def init(want, years):
    z = np.load(f"{V1}/admin/lookup.npz")
    _G["lk"] = {k: z[k] for k in LEVELS}
    _G["want"], _G["years"] = want, years


def tile_job(a):
    r0, c0 = a
    r1, c1 = min(r0 + TR, NLAT), min(c0 + TC, NLON)
    want, years = _G["want"], _G["years"]
    flags, climsum, land, okc, rate = {}, None, None, None, {}
    for v in VARS:
        x, land, tt = read(v, years, r0, r1, c0, c1, land)
        if x is None:
            return None
        x[x < 100.0] = np.nan
        idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(tt, unit="D"))
        doy = doy365(idx)
        base = np.asarray((idx.year >= BASE[0]) & (idx.year <= BASE[1]))
        thr, clim = cal_p90(x[base], doy[base])
        pos = np.searchsorted(tt, want)
        assert np.array_equal(tt[pos], want), "wanted days are not in the files read"
        with np.errstate(invalid="ignore"):
            flags[v] = x[pos] > thr[doy[pos] - 1]
            rate[v] = float((x[base] > thr[doy[base] - 1]).mean())
        ok = np.isfinite(thr).all(axis=0)
        okc = ok if okc is None else okc & ok
        climsum = clim if climsum is None else climsum + clim
        dpos = doy[pos]
        del x, thr
    warm = (climsum > np.nanmedian(climsum, axis=0)[None, :])[dpos - 1]                # (DAYS, cells)
    fx, fn = flags["t2mmax"] & okc[None, :], flags["t2mmin"] & okc[None, :]
    cls = [fx & ~fn & warm, ~fx & fn & warm, fx & fn & warm, (fx | fn) & ~warm]
    lat = np.repeat((90 - 0.1 * np.arange(r0, r1))[:, None], c1 - c0, axis=1)[land]
    w = np.where(okc, np.cos(np.deg2rad(lat)), 0.0)
    res = {}
    for k in LEVELS:
        u = _G["lk"][k][r0:r1, c0:c1][land]
        has = u >= 0
        if not has.any():
            res[k] = (np.zeros(0, "i8"), np.zeros((4, len(want), 0), "f4"), np.zeros(0))
            continue
        ids, inv = np.unique(u[has], return_inverse=True)
        m = sparse.csr_matrix((w[has], (np.where(has)[0], inv)), shape=(len(u), len(ids)))
        res[k] = (ids, np.stack([(m.T @ c.astype("f4").T).T for c in cls]), np.asarray(m.sum(axis=0)).ravel())
    return r0, c0, int(land.sum()), int((~okc).sum()), rate, res, [float(c.mean()) for c in cls]


if __name__ == "__main__":
    t0 = time.time()
    days = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")["time"][:]
    want = np.asarray(days)[PER.all_days(days)]                # every day the page can show
    DAYS = len(want)
    wy = sorted(set((pd.Timestamp("1900-01-01") + pd.to_timedelta(want, unit="D")).year))
    years = sorted(set(range(BASE[0], BASE[1] + 1)) | set(wy))
    one = [tuple(int(v) for v in sys.argv[1].split(":"))] if len(sys.argv) > 1 and ":" in sys.argv[1] else None
    tiles = one or [(r, c) for r in range(0, NLAT, TR) for c in range(0, NLON, TC)]
    nu = {k: len(pd.read_csv(f"{V1}/admin/units_{k}.csv", usecols=[0])) for k in LEVELS}
    num = {k: np.zeros((4, DAYS, nu[k]), "f8") for k in LEVELS}
    den = {k: np.zeros(nu[k], "f8") for k in LEVELS}
    rates, n_land, n_bad = [], 0, 0
    with Pool(1 if one else 6, initializer=init, initargs=(want, years)) as p:
        for i, out in enumerate(p.imap_unordered(tile_job, tiles)):
            if out is not None:
                r0, c0, n, nb, rate, res, means = out
                n_land += n
                n_bad += nb
                rates.append((rate["t2mmax"], rate["t2mmin"]))
                for k in LEVELS:
                    ids, nm, dn = res[k]
                    num[k][:, :, ids] += nm
                    den[k][ids] += dn
                if one:
                    print(f"tile {r0}:{c0} cells {n} declined {nb}; in-baseline rate hot day {rate['t2mmax']:.4f}, hot night {rate['t2mmin']:.4f}; "
                          f"mean share over the {len(want)} days: day only {means[0]:.3f}, night only {means[1]:.3f}, both {means[2]:.3f}, outside warm season {means[3]:.3f}")
            print(f"tile {i + 1}/{len(tiles)} elapsed {time.time() - t0:.0f} s", flush=True)
    if not one:
        out = {"days": want.astype("i4"), "base_rate": np.median(np.array(rates), axis=0)}
        for k in LEVELS:
            ok = den[k] > 0
            with np.errstate(invalid="ignore", divide="ignore"):
                out[k] = np.where(ok[None, None, :], np.clip(np.rint(num[k] / den[k][None, None, :] * 10000), 0, 10000), 65535).astype("u2")
        np.savez_compressed(f"{V1}/admin/daynight.npz", **out)
        print(f"DONE {time.time() - t0:.0f} s; land cells {n_land}, declined {n_bad}; in-baseline rate, median over tiles: hot day {out['base_rate'][0]:.4f}, hot night {out['base_rate'][1]:.4f}; "
              f"years read {years[0]}-{years[-2]} and {wy}", flush=True)
