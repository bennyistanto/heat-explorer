"""Global map of the confidence classes, and a first look at saturation.

For every AgERA5 land cell:
  Tm      = (Tmax(d) + Tmin(d+1)) / 2
  clim    = calendar-day mean of Tm over 1991-2020, smoothed with a centred
            31-day running mean (29 February dropped)
  sd      = standard deviation of Tm - clim over 1991-2020 (all days)
  class   = low (sd < 1.0 K), reduced (1.0 to 1.5 K), normal (>= 1.5 K), the
            provisional rule in references/indicators.md
  exc     = share of days in 2021-2025 with Tm above clim + 1.2816 * sd_doy,
            where sd_doy is the calendar-day sd smoothed over 31 days. Under a
            normal distribution that level is the 90th percentile, so 0.10 is
            expected in the baseline. This is an APPROXIMATION of the detector's
            calendar-day p90 test (no 3-day mean, no empirical percentile); it is
            used only to see where a fixed threshold saturates.
  shift   = mean Tm anomaly of 2021-2025, in K

Questions, written on 2026-11-21 before the run:
  Q1  what share of land area falls in each class, globally and by latitude?
  Q2  are the cells where the fixed threshold saturates (exc >= 0.33, a third
      of all days) the same set as the low-confidence cells? The decision to
      confine moving thresholds to low-confidence cells assumed so.

Note: the skill evidence behind the 1.0 and 1.5 K limits was measured on Tmax
anomalies over each station's own period; this map uses Tm on 1991-2020. The
two are not identical and the limits stay provisional.

Streaming: per 200-row band (the NetCDF chunk height) the script keeps only
calendar-day sums and sums of squares, so memory stays small.

Run:  bash tools/py.sh -W ignore validation/confidence_map/01_confidence_map.py
Output: validation/confidence_map/results/summary.txt, classes.png, saturation.png;
        E:/temp/agera5/derived-products/heat-explorer/confidence/confidence_v0.npz
"""
import os
import time
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np

RAW = "E:/temp/agera5"
OUT = "E:/temp/agera5/derived-products/heat-explorer/confidence"
HERE = os.path.dirname(os.path.abspath(__file__))
TX, TN = "Temperature_Air_2m_Max_24h", "Temperature_Air_2m_Min_24h"
BASE, RECENT = range(1991, 2021), range(2021, 2026)
Z90 = 1.2816


def smooth31(a):
    """Centred 31-day circular running mean along axis 0 (365 rows)."""
    w = np.concatenate([a[-15:], a, a[:15]])
    cs = np.cumsum(np.concatenate([np.zeros((1,) + a.shape[1:], a.dtype), w]), axis=0)
    return (cs[31:] - cs[:-31]) / 31.0


def read(v, name, y, r0, r1, land, first_only=False):
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[name]
    a = np.asarray(x[0:1, r0:r1, :]) if first_only else np.asarray(x[:, r0:r1, :])
    d.close()
    a = a[:, land]
    return np.where(a < 100.0, np.nan, a - 273.15).astype("f4")


def tm_year(y, r0, r1, land):
    """Tm for the 365 calendar days of year y (29 February dropped)."""
    tx = read("t2mmax", TX, y, r0, r1, land)
    tn = read("t2mmin", TN, y, r0, r1, land)
    nxt = read("t2mmin", TN, y + 1, r0, r1, land, first_only=True)
    tm = (tx + np.concatenate([tn[1:], nxt])) / 2
    if tm.shape[0] == 366:
        tm = np.delete(tm, 59, axis=0)
    return tm


def band(a):
    r0, r1 = a
    d = nc.Dataset(f"{RAW}/t2mmax/agera5_t2mmax_2000.nc")
    d.set_auto_mask(False)
    land = np.asarray(d.variables[TX][180, r0:r1, :]) != -9999.0
    d.close()
    n = int(land.sum())
    if n == 0:
        return r0, r1, land, None
    sx, sxx = np.zeros((365, n)), np.zeros((365, n))
    for y in BASE:
        tm = tm_year(y, r0, r1, land).astype("f8")
        sx += tm
        sxx += tm * tm
    nb = len(BASE)
    clim = smooth31(sx / nb)
    ss = sxx - 2 * clim * sx + nb * clim * clim          # sum over years of (x - clim)^2, per calendar day
    sd = np.sqrt(ss.sum(axis=0) / (nb * 365))
    thr = clim + Z90 * np.sqrt(np.clip(smooth31(ss / nb), 0, None))
    cnt, dsum = np.zeros(n), np.zeros(n)
    for y in RECENT:
        tm = tm_year(y, r0, r1, land).astype("f8")
        cnt += (tm > thr).sum(axis=0)
        dsum += (tm - clim).sum(axis=0)
    nd = len(RECENT) * 365
    return r0, r1, land, (sd.astype("f4"), (cnt / nd).astype("f4"), (dsum / nd).astype("f4"))


def wshare(mask, w):
    return float(w[mask].sum() / w.sum()) if w.sum() > 0 else float("nan")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    res = os.path.join(HERE, "results")
    os.makedirs(res, exist_ok=True)
    t0 = time.time()
    bands = [(r, min(r + 200, 1801)) for r in range(0, 1801, 200)]
    sd = np.full((1801, 3600), np.nan, "f4")
    exc, shift = sd.copy(), sd.copy()
    with Pool(len(bands)) as p:
        for r0, r1, land, out in p.imap_unordered(band, bands):
            if out is not None:
                sd[r0:r1][land], exc[r0:r1][land], shift[r0:r1][land] = out
            print(f"rows {r0}-{r1} {int(land.sum())} cells {time.time() - t0:.0f} s", flush=True)
    np.savez_compressed(f"{OUT}/confidence_v0.npz", sd=sd, exc_recent=exc, shift_recent=shift)

    lat = 90 - 0.1 * np.arange(1801)
    W = np.repeat(np.cos(np.deg2rad(lat))[:, None], 3600, axis=1)
    ok = np.isfinite(sd)
    cls = np.where(sd < 1.0, 0, np.where(sd < 1.5, 1, 2))
    names = ["low (<1.0 K)", "reduced (1.0-1.5 K)", "normal (>=1.5 K)"]
    out = ["Global confidence classes. Produced by validation/confidence_map/01_confidence_map.py",
           f"Land cells with data: {int(ok.sum())}. Shares are of land area (cos-latitude weights).",
           "sd = sd of Tm anomalies 1991-2020. exc = share of 2021-2025 days above a normal-approximation",
           "calendar-day 90th percentile (0.10 expected in the baseline).", ""]

    def block(title, sel):
        w = np.where(sel, W, 0)
        out.append(f"== {title}: {int(sel.sum())} cells")
        for c in range(3):
            m = sel & (cls == c)
            out.append(f"  {names[c]:22s} area share {wshare(m, w):.3f}   median exc {np.nanmedian(exc[m]) if m.any() else float('nan'):.2f}"
                       f"   share of class with exc>=0.33: {wshare(m & (exc >= 0.33), np.where(m, W, 0)):.3f}")
        out.append(f"  below 0.75 K           area share {wshare(sel & (sd < 0.75), w):.3f}")
        sat = sel & (exc >= 0.33)
        ws = np.where(sat, W, 0)
        out.append(f"  saturating (exc>=0.33) area share {wshare(sat, w):.3f}; of it low {wshare(sat & (cls == 0), ws):.3f}, "
                   f"reduced {wshare(sat & (cls == 1), ws):.3f}, normal {wshare(sat & (cls == 2), ws):.3f}")
        out.append(f"  median exc {np.nanmedian(exc[sel]):.2f}; median shift {np.nanmedian(shift[sel]):.2f} K; median sd {np.nanmedian(sd[sel]):.2f} K")
        out.append("")

    latg = np.repeat(lat[:, None], 3600, axis=1)
    block("All land", ok)
    block("Land north of 60 S (Antarctica excluded)", ok & (latg > -60))
    out.append("== By 10 degree latitude band (area shares within the band)")
    out.append("  band        cells    low  reduced  normal   median_sd  median_exc  sat_share  low_share_of_sat")
    for a in range(80, -70, -10):
        sel = ok & (latg <= a + 10 if a == 80 else latg < a + 10) & (latg >= a)
        if not sel.any():
            continue
        w = np.where(sel, W, 0)
        sat = sel & (exc >= 0.33)
        ws = np.where(sat, W, 0)
        out.append(f"  {a:4d}..{a + 10:<4d} {int(sel.sum()):7d}  {wshare(sel & (cls == 0), w):.3f}   {wshare(sel & (cls == 1), w):.3f}   "
                   f"{wshare(sel & (cls == 2), w):.3f}      {np.nanmedian(sd[sel]):.2f}        {np.nanmedian(exc[sel]):.2f}      "
                   f"{wshare(sat, w):.3f}      {wshare(sat & (cls == 0), ws):.3f}")
    r = np.corrcoef(sd[ok], exc[ok])[0, 1]
    out.append(f"\nCorrelation of sd and exc across cells: {r:.2f}")
    out.append(f"total {time.time() - t0:.0f} s")
    txt = "\n".join(out)
    with open(f"{res}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    ext = [-180.05, 179.95, -90.05, 90.05]
    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=130)
    cm = ListedColormap(["#b2182b", "#f4a582", "#d1e5f0"])
    im = ax.imshow(np.where(ok, cls, np.nan), extent=ext, cmap=cm, norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3), interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1, 2], shrink=0.7)
    cb.ax.set_yticklabels(names)
    ax.set_ylim(-60, 85)
    ax.set_title("Confidence class: sd of daily Tm anomalies, AgERA5 1991-2020 (provisional limits)")
    fig.tight_layout()
    fig.savefig(f"{res}/classes.png")
    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=130)
    im = ax.imshow(exc, extent=ext, cmap="magma_r", vmin=0.1, vmax=0.6, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7, label="share of days")
    ax.set_ylim(-60, 85)
    ax.set_title("Share of 2021-2025 days above an approximate calendar-day 90th percentile of 1991-2020 (0.10 expected)")
    fig.tight_layout()
    fig.savefig(f"{res}/saturation.png")
