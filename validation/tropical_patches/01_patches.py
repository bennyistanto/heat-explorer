"""Where are the cells with more than 100 severe days a year in 2021-2025, and
does AgERA5 warm there gradually or in a step?

The global run (pipeline/run_global.py, detector 1.0) shows patches in the
Congo basin, New Guinea and the western Amazon with over 100 severe-or-extreme
days a year in 2021-2025, against about 12 in the baseline. All lie where
day-to-day temperature varies little, so a small shift crosses the thresholds
on many days. The question here is whether the shift is a break in the data.

Method
  Patch: connected group (8 neighbours) of land cells with more than 100
  severe-or-extreme days a year in 2021-2025, north of 60 S. The 12 largest by
  area are examined.
  Ring: land cells within 3 degrees of the patch's bounding box that are not
  in any such group.
  Series: annual mean Tm 1979-2025 (step-screen/annual_tm_1979_2025.npz),
  cos-latitude weighted mean over the patch, over the ring, and patch minus
  ring.
  Two models on each annual series: one break (at least 6 years each side)
  against a straight line, compared by BIC (step charged 3 parameters, line 2).

Reading rule, written on 2026-11-22 before the run:
  LOCAL STEP   patch minus ring favours the step by 6 BIC units or more and
               the step is 0.3 K or more. Real warming is smooth in space, so
               a step against the surroundings points at the data.
  OWN STEP     the patch series itself favours a step by 6 BIC units and the
               step is 0.4 K or more, but patch minus ring does not: the
               surroundings step with it, which the ring cannot judge. Needs
               stations.
  GRADUAL      neither.
Limits: 47 annual values is a short series; El Nino years can look like a
step; a ring that shares the same data problem hides it. This is a screen. It
cannot clear a patch, only point at one.

Run:  bash tools/py.sh -W ignore validation/tropical_patches/01_patches.py
Output: validation/tropical_patches/results/patches.txt, patches.csv, patches.png
"""
import os

import numpy as np
import pandas as pd
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
D = "E:/temp/agera5/derived-products/heat-explorer"
YEARS = np.arange(1979, 2026)
LIMIT, NTOP = 100.0, 12


def fit(y):
    n, t = len(y), np.arange(len(y), dtype="f8")
    best = (np.inf, None, 0.0)
    for k in range(6, n - 5):
        sse = ((y[:k] - y[:k].mean()) ** 2).sum() + ((y[k:] - y[k:].mean()) ** 2).sum()
        if sse < best[0]:
            best = (sse, k, y[k:].mean() - y[:k].mean())
    p = np.polyfit(t, y, 1)
    sse_l = ((y - np.polyval(p, t)) ** 2).sum()
    gain = (n * np.log(sse_l / n) + 2 * np.log(n)) - (n * np.log(best[0] / n) + 3 * np.log(n))
    return int(YEARS[best[1]]), float(best[2]), float(gain), float(p[0] * 10)


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    S = np.load(f"{D}/v1/run_summary_global.npz")["days_per_year"]
    tm = np.load(f"{D}/step-screen/annual_tm_1979_2025.npz")["tm"]
    conf = np.load(f"{D}/confidence/confidence_v0.npz")["sd"]
    scr = np.load(f"{D}/step-screen/step_screen_v0.npz")
    lat = 90 - 0.1 * np.arange(1801)
    lon = -180 + 0.1 * np.arange(3600)
    w2 = np.repeat(np.cos(np.deg2rad(lat))[:, None], 3600, axis=1)
    area = w2 * (11.1195 ** 2)                                   # km2 per cell
    land = np.isfinite(S[3]) & (lat[:, None] > -60)
    hot = land & (S[3] > LIMIT)
    lab, n = ndimage.label(hot, structure=np.ones((3, 3)))
    a = ndimage.sum(area, lab, index=np.arange(1, n + 1))
    order = np.argsort(a)[::-1]
    out = ["Cells with more than 100 severe-or-extreme days a year in 2021-2025. Produced by validation/tropical_patches/01_patches.py",
           f"Such cells: {int(hot.sum()):,} of {int(land.sum()):,} land cells north of 60 S ({hot.sum() / land.sum():.1%}); area {area[hot].sum() / 1e6:.2f} million km2; {n} connected groups.",
           f"Share of them in the low-confidence class (sd of anomalies below 1.0 K): {(conf[hot] < 1.0).mean():.1%}; within 15 degrees of the equator: {(np.abs(w2 * 0 + lat[:, None])[hot] <= 15).mean():.1%}",
           f"Share flagged by step screen v0 (not accepted): {scr['suspect'][hot].mean():.1%} of those screened ({scr['screened'][hot].mean():.1%} were screened)",
           f"The {NTOP} largest groups hold {a[order[:NTOP]].sum() / a.sum():.1%} of that area.", ""]
    rows = []
    for rank, li in enumerate(order[:NTOP], 1):
        m = lab == li + 1
        ii, jj = np.where(m)
        i0, i1, j0, j1 = max(ii.min() - 30, 0), min(ii.max() + 31, 1801), max(jj.min() - 30, 0), min(jj.max() + 31, 3600)
        ring = np.zeros_like(m)
        ring[i0:i1, j0:j1] = True
        ring &= land & ~hot
        sp = (tm[:, m] * w2[m]).sum(axis=1) / w2[m].sum()
        sr = (tm[:, ring] * w2[ring]).sum(axis=1) / w2[ring].sum() if ring.sum() >= 50 else np.full(len(YEARS), np.nan)
        base = (YEARS >= 1991) & (YEARS <= 2020)
        rec = YEARS >= 2021
        fp = fit(sp)
        fd = fit(sp - sr) if np.isfinite(sr).all() else (0, np.nan, np.nan, np.nan)
        if fd[2] >= 6 and abs(fd[1]) >= 0.3:
            v = "LOCAL STEP"
        elif fp[2] >= 6 and abs(fp[1]) >= 0.4:
            v = "OWN STEP"
        else:
            v = "GRADUAL"
        rows.append({"rank": rank, "lat": round(float((lat[ii] * w2[m][...]).sum() / w2[m].sum()), 1), "lon": round(float(lon[jj].mean()), 1),
                     "box": f"{lat[ii.max()]:.1f} to {lat[ii.min()]:.1f}, {lon[jj.min()]:.1f} to {lon[jj.max()]:.1f}",
                     "cells": int(m.sum()), "area_1000km2": round(float(area[m].sum() / 1e3), 0),
                     "sev_days_base": round(float(np.nanmean(S[1][m])), 1), "sev_days_2021_25": round(float(np.nanmean(S[3][m])), 0),
                     "sd_K": round(float(np.nanmedian(conf[m])), 2),
                     "warm_K": round(float(sp[rec].mean() - sp[base].mean()), 2), "ring_warm_K": round(float(sr[rec].mean() - sr[base].mean()), 2),
                     "break": fp[0], "step_K": round(fp[1], 2), "bic_gain": round(fp[2], 1), "line_K_dec": round(fp[3], 2),
                     "diff_break": fd[0], "diff_step_K": round(fd[1], 2), "diff_bic_gain": round(fd[2], 1), "reading": v,
                     "patch_2015_2025": " ".join(f"{x:+.2f}" for x in (sp - sp[base].mean())[-11:]),
                     "diff_2015_2025": " ".join(f"{x:+.2f}" for x in ((sp - sr) - (sp - sr)[base].mean())[-11:])})
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(HERE, "results", "patches.csv"), index=False)
    pd.set_option("display.width", 400, "display.max_columns", 40, "display.max_colwidth", 90)
    out.append(t.drop(columns=["patch_2015_2025", "diff_2015_2025"]).to_string(index=False))
    out.append("\nwarm_K: mean annual Tm 2021-2025 minus 1991-2020 in the patch; ring_warm_K: the same in the ring.")
    out.append("break, step_K, bic_gain, line_K_dec: step model and line on the patch series; diff_*: on patch minus ring.")
    out.append("\nAnnual anomaly from the 1991-2020 mean, 2015 to 2025, K")
    for r in rows:
        out.append(f"  {r['rank']:2d} patch          {r['patch_2015_2025']}")
        out.append(f"     patch - ring   {r['diff_2015_2025']}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "patches.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(14, 10), dpi=110)
    ax = fig.add_subplot(2, 1, 1)
    im = ax.imshow(np.where(land, S[3], np.nan)[600:1200], extent=[-180.05, 179.95, -30.05, 30.05], cmap="magma_r", vmin=0, vmax=150, interpolation="nearest")
    for r in rows:
        ax.text(r["lon"], r["lat"], str(r["rank"]), color="cyan", fontsize=9, ha="center", va="center", weight="bold")
    fig.colorbar(im, ax=ax, shrink=0.7, label="days per year")
    ax.set_title("Severe or extreme days per year, 2021-2025; numbers mark the 12 largest groups above 100")
    ax2 = fig.add_subplot(2, 1, 2)
    for li, r in zip(order[:6], rows[:6]):
        m = lab == li + 1
        sp = (tm[:, m] * w2[m]).sum(axis=1) / w2[m].sum()
        ax2.plot(YEARS, sp - sp[(YEARS >= 1991) & (YEARS <= 2020)].mean(), label=f"{r['rank']}: {r['lat']}, {r['lon']} ({r['reading']})")
    ax2.axhline(0, color="k", lw=0.5)
    ax2.set_ylabel("annual mean Tm, K from 1991-2020")
    ax2.set_title("Six largest groups: annual mean temperature in AgERA5")
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "results", "patches.png"))
