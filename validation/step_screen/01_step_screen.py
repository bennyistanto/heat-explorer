"""Step screen: cells whose temperature jumps in one year when the region's does not.

Background: validation/confidence_map/02_patch_check.py found that AgERA5 on
the eastern Tibetan Plateau and the Bhutan-Sikkim Himalaya steps up by about
1.5 K in 2020 against stations, while northern Japan's recent warmth is real.
A fixed threshold in a stepped cell flags heat that did not happen.

Method (all project choices, written on 2026-11-21 BEFORE the first run)
  a(y)   annual mean of (Tmax + Tmin) / 2 per cell, 1979-2025, minus the cell's
         1991-2020 mean
  ref(y) regional background: median of a(y) over all land cells in the 5 x 5
         degree window centred on the cell's 1 degree block (needs 200 cells)
  d(y)   a(y) - ref(y): what the cell does that its region does not
  step   for each break year k from 1985 to 2021 (so both sides hold at least
         5 years): step_k = mean d(y >= k) - mean d(y < k);
         score_k = |step_k| / (s * sqrt(1/n1 + 1/n2)), s = residual sd after
         removing the two means. The break year is the k with the highest score.
  flag   "data suspect" when |step| >= 1.0 K and score >= 6

Targets, written before the run, using the patches of 02_patch_check.py
(cells with sd >= 1.5 K and exc >= 0.33 inside each box):
  T1  at least 80 percent of the eastern Tibetan Plateau patch cells and of
      the Bhutan-Sikkim patch cells are flagged, with break year 2019 to 2021
  T2  fewer than 5 percent of the northern Japan patch cells are flagged
  The screen is accepted only if T1 and T2 both hold.

What it cannot see, by construction: a step shared by a whole 5 degree region
(the regional median moves with it); gradual drift such as northern Japan's;
steps in the first or last 5 years. A real local change (a new reservoir, a
city, a glacier retreat) would also be flagged: the flag says "check", not
"wrong". Annual means hide a step confined to one season.

Run:  bash tools/py.sh -W ignore validation/step_screen/01_step_screen.py
Output: validation/step_screen/results/summary.txt, suspect.png;
        E:/temp/agera5/derived-products/heat-explorer/step-screen/
        annual_tm_1979_2025.npz (reused if present), step_screen_v0.npz
"""
import os
import time
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np

RAW = "E:/temp/agera5"
OUT = "E:/temp/agera5/derived-products/heat-explorer/step-screen"
CONF = "E:/temp/agera5/derived-products/heat-explorer/confidence/confidence_v0.npz"
HERE = os.path.dirname(os.path.abspath(__file__))
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = np.arange(1979, 2026)
STEP_MIN, SCORE_MIN = 1.0, 6.0
PATCH = {"Northern Japan": (36.5, 45.6, 138.0, 146.0),
         "Bhutan-Sikkim Himalaya": (26.0, 30.0, 86.5, 91.5),
         "Eastern Tibetan Plateau": (31.0, 37.0, 94.0, 102.0)}


def job(a):
    v, y, r0, r1 = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = np.asarray(d.variables[VARS[v]][:, r0:r1, :])
    d.close()
    mean = x.mean(axis=0, dtype="f8")
    return v, y, r0, r1, mean.astype("f4"), x.min(axis=0)


def annual_means():
    fn = f"{OUT}/annual_tm_1979_2025.npz"
    if os.path.exists(fn):
        return np.load(fn)["tm"]
    acc = np.zeros((len(YEARS), 1801, 3600), "f4")
    bad = np.zeros((1801, 3600), bool)
    jobs = [(v, int(y), r, min(r + 200, 1801)) for y in YEARS for v in VARS for r in range(0, 1801, 200)]
    t0 = time.time()
    with Pool(32) as p:
        for n, (v, y, r0, r1, mean, mn) in enumerate(p.imap_unordered(job, jobs, chunksize=1)):
            acc[y - 1979, r0:r1] += mean / 2
            bad[r0:r1] |= mn < 100.0                      # any fill value in the year
            if n % 100 == 0:
                print(f"read {n}/{len(jobs)} {time.time() - t0:.0f} s", flush=True)
    acc -= 273.15
    acc[:, bad] = np.nan
    np.savez_compressed(fn, tm=acc)
    return acc


def regional_median(a):
    """Median of a over the 5 x 5 degree window around each 1 degree block."""
    ref = np.full_like(a, np.nan)
    land = np.isfinite(a[0])
    for bi in range(180):
        r0, r1 = bi * 10, min(bi * 10 + 10, 1801) if bi < 179 else 1801
        w0, w1 = max(r0 - 20, 0), min(r0 + 30, 1801)
        if not land[w0:w1].any():
            continue
        for bj in range(360):
            c0 = bj * 10
            if not land[r0:r1, c0:c0 + 10].any():
                continue
            cols = np.arange(c0 - 20, c0 + 30) % 3600
            win = a[:, w0:w1][:, :, cols]
            m = land[w0:w1][:, cols]
            if m.sum() < 200:
                continue
            ref[:, r0:r1, c0:c0 + 10] = np.median(win[:, m], axis=1)[:, None, None]
    return ref


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    res = os.path.join(HERE, "results")
    os.makedirs(res, exist_ok=True)
    t0 = time.time()
    tm = annual_means()
    base = (YEARS >= 1991) & (YEARS <= 2020)
    a = tm - tm[base].mean(axis=0)
    print(f"annual means {time.time() - t0:.0f} s", flush=True)
    ref = regional_median(a)
    print(f"regional median {time.time() - t0:.0f} s", flush=True)
    ok = np.isfinite(a).all(axis=0) & np.isfinite(ref).all(axis=0)
    d = (a - ref)[:, ok].astype("f8")
    n = len(YEARS)
    cs = np.cumsum(d, axis=0)
    tot, ss = cs[-1], (d * d).sum(axis=0)
    best = np.zeros(d.shape[1])
    step = np.zeros(d.shape[1])
    brk = np.zeros(d.shape[1], "i2")
    for k in range(6, n - 4):                       # break year YEARS[k], 1985..2021
        n1, n2 = k, n - k
        m1, m2 = cs[k - 1] / n1, (tot - cs[k - 1]) / n2
        sse = np.clip(ss - n1 * m1 * m1 - n2 * m2 * m2, 1e-12, None)
        sc = np.abs(m2 - m1) / (np.sqrt(sse / (n - 2)) * np.sqrt(1 / n1 + 1 / n2))
        up = sc > best
        best[up], step[up], brk[up] = sc[up], (m2 - m1)[up], YEARS[k]
    flag = (np.abs(step) >= STEP_MIN) & (best >= SCORE_MIN)

    def grid(x, fill=np.nan, dt="f4"):
        g = np.full((1801, 3600), fill, dt)
        g[ok] = x
        return g
    G_flag, G_step, G_brk, G_score = grid(flag, False, bool), grid(step), grid(brk, 0, "i2"), grid(best)
    np.savez_compressed(f"{OUT}/step_screen_v0.npz", suspect=G_flag, step=G_step, break_year=G_brk, score=G_score, screened=ok)

    lat = 90 - 0.1 * np.arange(1801)
    lon = -180 + 0.1 * np.arange(3600)
    W = np.repeat(np.cos(np.deg2rad(lat))[:, None], 3600, axis=1)
    land = np.isfinite(tm[0])
    out = ["Step screen. Produced by validation/step_screen/01_step_screen.py",
           f"Flag: |step| >= {STEP_MIN} K against the 5 degree regional median and score >= {SCORE_MIN}. Break years 1985-2021.",
           f"Land cells {int(land.sum())}; screened {int(ok.sum())}; not screened (too few neighbours or missing years) {int((land & ~ok).sum())}",
           f"Flagged: {int(flag.sum())} cells, {W[G_flag].sum() / W[ok].sum():.4f} of screened land area; "
           f"north of 60 S: {int((G_flag & (lat[:, None] > -60)).sum())} cells, {W[G_flag & (lat[:, None] > -60)].sum() / W[ok & (lat[:, None] > -60)].sum():.4f}",
           f"Of flagged cells: warm steps {int((step[flag] > 0).sum())}, cold steps {int((step[flag] < 0).sum())}; median |step| {np.median(np.abs(step[flag])):.2f} K", ""]
    z = np.load(CONF)
    out.append("== Targets")
    t_ok = []
    for name, (a0, a1, o0, o1) in PATCH.items():
        box = (lat[:, None] >= a0) & (lat[:, None] <= a1) & (lon[None, :] >= o0) & (lon[None, :] <= o1)
        pc = box & (z["sd"] >= 1.5) & (z["exc_recent"] >= 0.33) & ok
        rest = box & ok & ~pc
        f = G_flag[pc].mean()
        f20 = (G_flag[pc] & (G_brk[pc] >= 2019) & (G_brk[pc] <= 2021)).mean()
        out.append(f"  {name}: patch cells {int(pc.sum())}, flagged {f:.3f}, flagged with break 2019-2021 {f20:.3f}; "
                   f"median step {np.nanmedian(G_step[pc]):+.2f} K, median score {np.nanmedian(G_score[pc]):.1f}; rest of box flagged {G_flag[rest].mean():.3f}")
        t_ok.append(f < 0.05 if name == "Northern Japan" else f20 >= 0.80)
    out.append(f"  T1 and T2: {'ALL HOLD' if all(t_ok) else 'NOT ALL HOLD ' + str(t_ok)}")
    out.append("\n== Flagged cells by break year")
    yrs, cnt = np.unique(brk[flag], return_counts=True)
    out.append("  " + " ".join(f"{y}:{c}" for y, c in zip(yrs, cnt)))
    from scipy import ndimage
    lab, nl = ndimage.label(G_flag, structure=np.ones((3, 3)))
    sz = ndimage.sum(G_flag, lab, range(1, nl + 1))
    out.append(f"\n== Largest of {nl} flagged groups")
    for k in np.argsort(sz)[::-1][:25]:
        q = lab == k + 1
        ii, jj = np.nonzero(q)
        by, bc = np.unique(G_brk[q], return_counts=True)
        out.append(f"  {int(sz[k]):6d} cells  lat {lat[ii].min():6.1f}..{lat[ii].max():6.1f}  lon {lon[jj].min():7.1f}..{lon[jj].max():7.1f}  "
                   f"median step {np.median(G_step[q]):+.2f} K  commonest break {by[bc.argmax()]} ({bc.max() / bc.sum():.0%})")
    out.append(f"\ntotal {time.time() - t0:.0f} s")
    txt = "\n".join(out)
    with open(f"{res}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=130)
    ax.imshow(np.where(land, 0.0, np.nan), extent=[-180.05, 179.95, -90.05, 90.05], cmap="Greys", vmin=-1, vmax=4, interpolation="nearest")
    im = ax.imshow(np.where(G_flag, G_step, np.nan), extent=[-180.05, 179.95, -90.05, 90.05], cmap="RdBu_r", vmin=-3, vmax=3, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7, label="step against the regional median, K")
    ax.set_ylim(-60, 85)
    ax.set_title("Data-suspect cells: single-year step of 1 K or more that the surrounding 5 degrees do not share")
    fig.tight_layout()
    fig.savefig(f"{res}/suspect.png")
