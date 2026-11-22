"""Heat spell detector, version 1.0: many cells at once.

This is the production implementation of the frozen definition in
docs/detector-v1-frozen.md. The reference is the single-cell code in
validation/detector_v3/detector.py; this module must give the same `flag`,
`spell` and `cls_day` on every day at every cell. That is checked by
validation/detector_v3/03_fast_equals_reference.py and must be re-checked
after any change here.

To stay identical it deliberately uses the same library operations as the
reference (pandas group means and rolling means, numpy linear-interpolated
percentiles), applied to all cells of a block at once.

Use
    out = detect_block(tm, days)
    tm    array (time, cells), daily Tm in deg C, NaN where missing.
          Tm(d) = (Tmax(d) + Tmin(d+1)) / 2, computed by the caller.
    days  the file time axis, days since 1900-01-01, same length as tm.
Returns a dict of arrays (time, cells):
    flag      bool   flagged day
    spell     bool   day in a run of at least MIN_RUN flagged days
    cls_day   uint8  0 none, 1 heat spell, 2 severe, 3 extreme (frozen class)
    live      bool   flagged on the day and on the two days before it
    excess    float32  excess over threshold in units of local spread on spell
                     days, else 0 (NOT part of the frozen definition)
and "ok", a bool array (cells,): False where the cell has missing values
inside the baseline and was left empty for the caller to handle.
With thresholds=True the dict also holds what is needed to class a new day
without the full record: "thr" (365, 3, cells) float32, the calendar-day 90th,
95th and 99th percentile thresholds in deg C by day of year (365-day calendar),
and "allyear" (3, cells) float32: the all-year median, 95th percentile and
the inter-quartile range of baseline anomalies.
"""
import numba
import numpy as np
import pandas as pd

VERSION = "1.0"
BASE_YEARS = (1991, 2020)
MIN_RUN = 3          # days
CAL_Q = 90           # calendar-day percentile for the flag
SEV_Q = (95, 99)     # calendar-day percentiles for severe and extreme
ALL_Q = (50, 95)     # all-year floor and all-year test
HALF_WIN = 7         # days either side of the calendar day (15-day window)
CLIM_WIN = 31        # days of the centred running mean of the seasonal cycle


def doy365(idx):
    """Day of year on a 365-day calendar; 29 February shares 28 February."""
    d = idx.dayofyear.values.copy()
    d[idx.is_leap_year & (d >= 60)] -= 1
    return d


@numba.njit(parallel=True, cache=True)
def _spells(flag, min_run):
    """Days belonging to runs of at least min_run flagged days."""
    t_n, n = flag.shape
    out = np.zeros((t_n, n), np.bool_)
    for j in numba.prange(n):
        t = 0
        while t < t_n:
            if flag[t, j]:
                s = t
                while t < t_n and flag[t, j]:
                    t += 1
                if t - s >= min_run:
                    for u in range(s, t):
                        out[u, j] = True
            else:
                t += 1
    return out


def detect_block(tm, days, thresholds=False):
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(np.asarray(days), unit="D"))
    tm = np.asarray(tm, dtype="f8")
    t_n, n = tm.shape
    t3 = pd.DataFrame(tm).rolling(3, center=True).mean().values
    doy = doy365(idx)
    in_base = np.asarray((idx.year >= BASE_YEARS[0]) & (idx.year <= BASE_YEARS[1]))
    ok = np.isfinite(t3[in_base]).all(axis=0)
    res = {"flag": np.zeros((t_n, n), bool), "spell": np.zeros((t_n, n), bool), "cls_day": np.zeros((t_n, n), "u1"),
           "live": np.zeros((t_n, n), bool), "excess": np.zeros((t_n, n), "f4"), "ok": ok}
    if not ok.any():
        return res
    x = t3[:, ok]
    xb, db = x[in_base], doy[in_base]
    c = pd.DataFrame(xb).groupby(db).mean().reindex(range(1, 366)).interpolate(limit_direction="both")
    h = CLIM_WIN // 2
    clim = pd.concat([c.iloc[-h:], c, c.iloc[:h]]).rolling(CLIM_WIN, center=True).mean().iloc[h:-h].values      # (365, cells)
    ab = xb - clim[db - 1]
    qs = (CAL_Q,) + SEV_Q
    pq = np.empty((365, len(qs), x.shape[1]))
    for d in range(1, 366):
        dist = np.abs(db - d)
        pq[d - 1] = np.percentile(ab[np.minimum(dist, 365 - dist) <= HALF_WIN], qs, axis=0)
    cd = clim[doy - 1]
    thr, hi1, hi2 = cd + pq[doy - 1, 0], cd + pq[doy - 1, 1], cd + pq[doy - 1, 2]
    p50, p95 = np.percentile(xb, ALL_Q, axis=0)
    q25, q75 = np.percentile(ab, [25, 75], axis=0)
    iqr = q75 - q25
    fin = np.isfinite(x)
    with np.errstate(invalid="ignore"):
        flag = (fin & (x > thr) & (x > p50)) | (fin & (x > p95))
        spell = _spells(flag, MIN_RUN)
        cls = np.where(spell, 1 + (x > hi1).astype("u1") + (x > hi2).astype("u1"), 0).astype("u1")
        exc = np.where(spell, np.fmax((x - thr) / iqr, (x - p95) / iqr), 0.0)
    live = flag.copy()
    live[2:] &= flag[1:-1] & flag[:-2]
    live[:2] = False
    if thresholds:
        res["thr"] = np.full((365, 3, n), np.nan, "f4")
        res["thr"][:, :, ok] = (clim[:, None, :] + pq).astype("f4")
        res["allyear"] = np.full((3, n), np.nan, "f4")
        res["allyear"][:, ok] = np.stack([p50, p95, iqr]).astype("f4")
    res["flag"][:, ok], res["spell"][:, ok], res["cls_day"][:, ok] = flag, spell, cls
    res["live"][:, ok], res["excess"][:, ok] = live, np.nan_to_num(exc).astype("f4")
    return res
