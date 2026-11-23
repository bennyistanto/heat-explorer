"""Humid heat spell, yes or no: the experimental layer.

Decisions it carries out (references/indicators.md, Signal 4; the author,
2026-11-21): the humid heat spell is kept, marked "experimental", detection
only (no severity, no ranking), out of every headline, rank, trend and status.

    Tw_day  wet-bulb temperature from the daily maximum temperature, the daily
            mean dewpoint and a pressure estimated from the cell's mean
            elevation (ETOPO1, standard atmosphere). Same psychrometric
            balance as validation/wetbulb_gate/03_compare.py, solved by
            bisection in a numba kernel; compared with that code at start-up.
    spell   the flag and 3-day rule of detector version 1.0
            (pipeline/detector.py) applied to Tw_day in place of Tm. No class.
    shown   under live labelling: the day and the two before it are flagged.

Known and stated on the page: AgERA5 wet-bulb is too low in absolute terms
(station gate failed), so nothing here is a wet-bulb value; and the dewpoint
record drifts, so recent years are flagged far more often than the baseline.
No cold-climate mask is applied: the rule for one is not settled.

Output, outside the repository, in E:/temp/agera5/derived-products/heat-explorer/v1/humid/:
    elev.npz          mean elevation per cell, m (made once)
    humid_recent.npz  live (n, 1801, 3600) uint8 for every day the page can show (pipeline/periods.py):
                      0 no, 1 in a humid heat spell, 254 declined, 255 sea; days
    humid_admin.npz   adm0, adm1: share (n, units) uint16 x 10000 (65535 none) for the same days; days_per_year
                      (2, units) float32, area-mean days shown per year in 1991-2020 and 2021-2025; trail_days
    humid_cells.npz   sd (spread of Tw_day anomalies, K), days_per_year (2, 1801, 3600)

Run:  bash tools/py.sh -W ignore pipeline/run_humid.py            (everything)
      bash tools/py.sh -W ignore pipeline/run_humid.py 600:0      (one tile: prints its numbers, writes nothing)
"""
import os
import sys
import time

os.environ.setdefault("NUMBA_NUM_THREADS", "4")

import netCDF4 as nc
import numba
import numpy as np
import pandas as pd
import zarr
from multiprocessing import Pool
from scipy import sparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pipeline import detector, rawfiles  # noqa: E402
from pipeline import periods as PER  # noqa: E402

RAW = "E:/temp/agera5"
DEM = "E:/temp/dem/etopo180_4558_b013_12d8.nc"
V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
OUT = f"{V1}/humid"
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mdp": "Dew_Point_Temperature_2m_Mean_24h"}
YEARS = range(1979, 2027)
NLAT, NLON, TR, TC = 1801, 3600, 200, 400
RECENT, TRAIL, TAIL, BLOCK = 90, 365, 2, 6000
LEVELS = ("adm0", "adm1")
_G = {}


@numba.njit(parallel=True, cache=True)
def tw_day(tx, td, p):
    """Wet-bulb, deg C. tx, td (time, cells) in kelvin; p (cells) in hPa. NaN where an input is missing."""
    nt, n = tx.shape
    out = np.empty((nt, n), np.float32)
    for j in numba.prange(n):
        pj = p[j]
        for t in range(nt):
            a, b = tx[t, j], td[t, j]
            if not (a > 100.0 and b > 100.0):
                out[t, j] = np.nan
                continue
            tc = a - 273.15
            e = 6.1094 * np.exp(17.625 * (b - 273.15) / (b - 273.15 + 243.04))
            w = 0.622 * e / (pj - e)
            lo, hi = tc - 60.0, tc
            for _ in range(26):
                mid = 0.5 * (lo + hi)
                es = 6.1094 * np.exp(17.625 * mid / (mid + 243.04))
                f = 1005.0 * (tc - mid) - (2.501e6 - 2361.0 * mid) * (0.622 * es / (pj - es) - w)
                if f > 0:
                    lo = mid
                else:
                    hi = mid
            out[t, j] = 0.5 * (lo + hi)
    return out


def elevation():
    """Mean of ETOPO1 (sea set to 0) over each 0.1 degree cell, as in validation/event_suite/05_humid_cases.py."""
    f = f"{OUT}/elev.npz"
    if os.path.exists(f):
        return np.load(f)["elev"]
    d = nc.Dataset(DEM)
    alt = np.clip(np.asarray(d.variables["altitude"][:], "f8"), 0, None)          # south first, 1 arc-minute
    d.close()
    s = np.zeros((alt.shape[0] + 1, alt.shape[1] + 1))
    s[1:, 1:] = alt.cumsum(0).cumsum(1)
    a0 = np.clip(10797 - 6 * np.arange(NLAT), 0, alt.shape[0] - 7)[:, None]
    b0 = np.clip(6 * np.arange(NLON) - 3, 0, alt.shape[1] - 7)[None, :]
    elev = ((s[a0 + 7, b0 + 7] - s[a0, b0 + 7] - s[a0 + 7, b0] + s[a0, b0]) / 49.0).astype("f4")
    np.savez_compressed(f, elev=elev)
    return elev


def read(v, r0, r1, c0, c1, land=None):
    parts, tt = [], []
    for path in rawfiles.files(v, YEARS):
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


def init(days, elev, sel):
    z = np.load(f"{V1}/admin/lookup.npz")
    _G["lk"] = {k: z[k] for k in LEVELS}
    _G["days"], _G["elev"], _G["sel"] = days, elev, sel


def tile_job(a):
    r0, c0 = a
    r1, c1 = min(r0 + TR, NLAT), min(c0 + TC, NLON)
    t0 = time.time()
    days = _G["days"]
    tx, land, tt = read("t2mmax", r0, r1, c0, c1)
    if tx is None:
        return None
    assert np.array_equal(tt, days), "time axis differs from the heat-state store"
    td, _, tt2 = read("t2mdp", r0, r1, c0, c1, land)
    if not np.array_equal(tt2, days):                          # the dewpoint files run one day longer: keep the days of the store
        pos = np.searchsorted(tt2, days)
        assert pos.max() < len(tt2) and np.array_equal(tt2[pos], days), "dewpoint days do not cover the heat-state store's days"
        td = td[pos]
    p = (1013.25 * (1.0 - 2.25577e-5 * _G["elev"][r0:r1, c0:c1][land].astype("f8")) ** 5.25588).astype("f4")
    tw = tw_day(tx, td, p)
    del tx, td
    nt, n = tw.shape
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    yr = idx.year.values
    base, rec = (yr >= 1991) & (yr <= 2020), (yr >= 2021) & (yr <= 2025)
    doyb = detector.doy365(idx)[base]
    live = np.zeros((nt, n), bool)
    okc = np.zeros(n, bool)
    sd = np.full(n, np.nan, "f4")
    for b0 in range(0, n, BLOCK):
        sl = slice(b0, min(b0 + BLOCK, n))
        r = detector.detect_block(tw[:, sl], days)
        okc[sl] = r["ok"]
        live[:, sl] = r["live"] & r["ok"][None, :]
        xb = tw[base][:, sl]
        c = pd.DataFrame(xb).groupby(doyb).mean().reindex(range(1, 366)).interpolate(limit_direction="both")
        clim = pd.concat([c.iloc[-15:], c, c.iloc[:15]]).rolling(31, center=True).mean().iloc[15:-15].values.astype("f4")
        sd[sl] = np.nanstd(xb - clim[doyb - 1], axis=0)
    del tw
    shape = (r1 - r0, c1 - c0)
    sel = _G["sel"]                                            # positions of the days the page can show
    recent = np.full((len(sel),) + shape, 255, "u1")
    recent[:, land] = np.where(okc[None, :], live[sel], 254)
    dpy = np.stack([live[base].sum(axis=0) / 30.0, live[rec].sum(axis=0) / 5.0]).astype("f4")           # (2, n)
    dense = np.full((3,) + shape, np.nan, "f4")
    dense[0][land], dense[1][land], dense[2][land] = np.where(okc, sd, np.nan), np.where(okc, dpy[0], np.nan), np.where(okc, dpy[1], np.nan)
    lat = np.repeat((90 - 0.1 * np.arange(r0, r1))[:, None], c1 - c0, axis=1)[land]
    w = np.where(okc, np.cos(np.deg2rad(lat)), 0.0)
    tr = live[sel].astype("f4")
    res = {}
    for k in LEVELS:
        u = _G["lk"][k][r0:r1, c0:c1][land]
        has = u >= 0
        if not has.any():
            continue
        ids, inv = np.unique(u[has], return_inverse=True)
        m = sparse.csr_matrix((w[has], (np.where(has)[0], inv)), shape=(n, len(ids)))
        res[k] = (ids, (m.T @ tr.T).T, (m.T @ dpy.T).T, np.asarray(m.sum(axis=0)).ravel())
    return r0, c0, int(n), int((~okc).sum()), recent, dense, res, time.time() - t0


if __name__ == "__main__":
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    days = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")["time"][:]
    elev = elevation()
    # the kernel against the validated solver, on random inputs
    import importlib.util
    spec = importlib.util.spec_from_file_location("cmp03", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "validation", "wetbulb_gate", "03_compare.py"))
    rng = np.random.default_rng(0)
    tc, dep, el = rng.uniform(-30, 48, 4000), rng.uniform(0, 30, 4000), rng.uniform(0, 4500, 4000)
    pr = 1013.25 * (1.0 - 2.25577e-5 * el) ** 5.25588
    try:
        c3 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(c3)
        ref = c3.wetbulb(tc, c3.esat(tc - dep), pr)
        got = tw_day((tc + 273.15).astype("f4")[None, :], (tc - dep + 273.15).astype("f4")[None, :], pr.astype("f4"))[0]
        print(f"wet-bulb kernel against validation/wetbulb_gate/03_compare.py on 4,000 random cases: largest difference {float(np.abs(got - ref).max()):.4f} K", flush=True)
        assert np.abs(got - ref).max() < 0.01
    except ImportError as e:
        print("reference solver could not be loaded:", e)
    one = [tuple(int(v) for v in sys.argv[1].split(":"))] if len(sys.argv) > 1 and ":" in sys.argv[1] else None
    tiles = one or [(r, c) for r in range(0, NLAT, TR) for c in range(0, NLON, TC)]
    nu = {k: len(pd.read_csv(f"{V1}/admin/units_{k}.csv", usecols=[0])) for k in LEVELS}
    sel = PER.all_days(days)
    num = {k: np.zeros((len(sel), nu[k]), "f8") for k in LEVELS}
    dnum = {k: np.zeros((2, nu[k]), "f8") for k in LEVELS}
    den = {k: np.zeros(nu[k], "f8") for k in LEVELS}
    recent = np.full((len(sel), NLAT, NLON), 255, "u1")
    cells = np.full((3, NLAT, NLON), np.nan, "f4")
    n_land = n_bad = 0
    with Pool(1 if one else 8, initializer=init, initargs=(days, elev, sel)) as p:
        for i, out in enumerate(p.imap_unordered(tile_job, tiles)):
            if out is not None:
                r0, c0, n, nb, rc, dn, res, dt = out
                n_land += n
                n_bad += nb
                recent[:, r0:r0 + rc.shape[1], c0:c0 + rc.shape[2]] = rc
                cells[:, r0:r0 + dn.shape[1], c0:c0 + dn.shape[2]] = dn
                for k, (ids, nm, dd, dv) in res.items():
                    num[k][:, ids] += nm
                    dnum[k][:, ids] += dd
                    den[k][ids] += dv
                if one:
                    print(f"tile {r0}:{c0} cells {n} declined {nb} {dt:.0f} s; spread of Tw_day anomalies, median {np.nanmedian(dn[0]):.2f} K; days shown per year, median: 1991-2020 {np.nanmedian(dn[1]):.1f}, 2021-2025 {np.nanmedian(dn[2]):.1f}; "
                          f"share of cells in a humid spell on the last day {float((rc[-1] == 1).sum() / max(1, (rc[-1] <= 1).sum())):.3f}")
            print(f"tile {i + 1}/{len(tiles)} elapsed {time.time() - t0:.0f} s", flush=True)
    if not one:
        np.savez_compressed(f"{OUT}/humid_recent.npz", live=recent, days=np.asarray(days)[sel].astype("i4"))
        adm = {"trail_days": np.asarray(days)[sel].astype("i4")}
        for k in LEVELS:
            ok = den[k] > 0
            with np.errstate(invalid="ignore", divide="ignore"):
                adm[k] = np.where(ok[None, :], np.clip(np.rint(num[k] / den[k][None, :] * 10000), 0, 10000), 65535).astype("u2")
                adm[k + "_days_per_year"] = np.where(ok[None, :], dnum[k] / den[k][None, :], np.nan).astype("f4")
        np.savez_compressed(f"{OUT}/humid_admin.npz", **adm)
        np.savez_compressed(f"{OUT}/humid_cells.npz", sd=cells[0], days_per_year=cells[1:])
        north = np.repeat((90 - 0.1 * np.arange(NLAT) > -60)[:, None], NLON, axis=1) & np.isfinite(cells[0])
        print(f"DONE {time.time() - t0:.0f} s; land cells {n_land}, declined {n_bad}. North of 60 S: days shown per year, median 1991-2020 {np.nanmedian(cells[1][north]):.1f}, 2021-2025 {np.nanmedian(cells[2][north]):.1f} "
              f"(95th percentile of cells {np.nanpercentile(cells[2][north], 95):.1f}); spread below 1.0 K at {(cells[0][north] < 1.0).mean():.1%} of cells, 1.0 to 1.5 K at {((cells[0][north] >= 1.0) & (cells[0][north] < 1.5)).mean():.1%}", flush=True)
