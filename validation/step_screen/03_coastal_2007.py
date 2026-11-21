"""Map the 2007 coastal step across all coasts.

02_tsugaru_check.py found AgERA5 stepping up by 0.65 to 1.7 K against nine
coastal stations in northern Japan between June and October 2007, with inland
stations unaffected. The suspected cause (ERA5's sea surface temperature source
changing on 1 September 2007) would act on coasts everywhere. This script looks
for the same signature in AgERA5 alone, from the annual means saved by
01_step_screen.py. No raw file is read.

Definitions (project choices, written on 2026-11-21 BEFORE the first run)
  dist    distance from a land cell to the nearest cell without data (sea or
          large lake), in grid cells (0.1 degree; not corrected for latitude)
  D(k)    mean of years k+1..k+5 minus mean of years k-5..k-1, per cell: the
          change across year k, with year k left out
  ref(k)  median of D(k) over land cells with dist >= 5 in the 15 x 15 degree
          window around the cell's 1 degree block (all land cells if fewer
          than 100 such cells)
  E(k)    D(k) - ref(k): the change at the cell that the interior of its
          region does not share
  noise   standard deviation of E(k) at the cell over placebo years
          k = 1984..2001 and 2013..2019, whose windows do not touch 2007
  flag    |E(2007)| >= 0.5 K and |E(2007)| >= 3 x noise

Questions and targets, written before the run
  Q1  Is 2007 special? Compare, among cells with dist <= 3, the share with
      |E(k)| >= 0.5 K for k = 2007 against the same share for each placebo
      year. "Special" if the 2007 share is larger than every placebo year's.
  Q2  Is it coastal? Median |E(2007)| and flagged share by distance band.
      "Coastal" if the flagged share falls steadily with distance.
  Q3  Does it recover northern Japan? At the nine station cells that stepped,
      at least seven should have E(2007) >= 0.4 K; at the inland station cells
      the median should be below 0.2 K.
  Where: the largest groups of flagged cells, and a map.

Limits: this is AgERA5 against itself, so it shows where coastal cells changed
relative to their hinterland in 2007, not that the change is wrong. Only the
northern Japan group has station evidence. A real coastal change (a marine
heatwave regime, sea ice loss) would look the same. Islands and narrow land
have no interior reference nearby and borrow one from up to 7.5 degrees away.
Antarctica is left out of the summaries.

Run:  bash tools/py.sh -W ignore validation/step_screen/03_coastal_2007.py
Output: validation/step_screen/results/coastal_2007.txt, coastal_2007.png;
        E:/temp/agera5/derived-products/heat-explorer/step-screen/coastal_2007_v0.npz
"""
import os
import time

import numpy as np
from scipy import ndimage

OUT = "E:/temp/agera5/derived-products/heat-explorer/step-screen"
HERE = os.path.dirname(os.path.abspath(__file__))
YEARS = np.arange(1979, 2026)
KS = np.arange(1984, 2021)
PLACEBO = np.array([k for k in KS if k <= 2001 or 2013 <= k <= 2019])
COAST_ST = {"Mutsu": (41.283, 141.217), "Esashi": (41.867, 140.117), "Tomakomai": (42.617, 141.550), "Hakodate": (41.817, 140.750),
            "Fukaura": (40.650, 139.933), "Muroran": (42.317, 140.983), "Suttsu": (42.800, 140.217), "Otaru": (43.183, 141.017),
            "Hakodate 2": (41.770, 140.822)}
INLAND_ST = {"Sapporo": (43.067, 141.333), "Kutchan": (42.900, 140.750), "Iwamizawa": (43.217, 141.783), "Chitose": (42.794, 141.666),
             "Aomori": (40.817, 140.767), "Hachinohe": (40.533, 141.517)}


def regional(D, inland, land):
    ref = np.full_like(D, np.nan)
    for bi in range(180):
        r0, r1 = bi * 10, (bi * 10 + 10 if bi < 179 else 1801)
        if not land[r0:r1].any():
            continue
        w0, w1 = max(r0 - 70, 0), min(r0 + 80, 1801)
        for bj in range(360):
            c0 = bj * 10
            if not land[r0:r1, c0:c0 + 10].any():
                continue
            cols = np.arange(c0 - 70, c0 + 80, 2) % 3600
            rows = np.arange(w0, w1, 2)
            m = inland[np.ix_(rows, cols)]
            if m.sum() < 100:
                m = land[np.ix_(rows, cols)]
            win = D[:, rows][:, :, cols]
            ref[:, r0:r1, c0:c0 + 10] = np.median(win[:, m], axis=1)[:, None, None]
    return ref


if __name__ == "__main__":
    t0 = time.time()
    res = os.path.join(HERE, "results")
    tm = np.load(f"{OUT}/annual_tm_1979_2025.npz")["tm"]
    land = np.isfinite(tm).all(axis=0)
    dist = ndimage.distance_transform_edt(np.pad(land, ((0, 0), (50, 50)), mode="wrap"))[:, 50:-50]
    D = np.stack([tm[(YEARS > k) & (YEARS <= k + 5)].mean(axis=0) - tm[(YEARS < k) & (YEARS >= k - 5)].mean(axis=0) for k in KS]).astype("f4")
    D[:, ~land] = np.nan
    ref = regional(D, land & (dist >= 5), land)
    E = D - ref
    print(f"E computed {time.time() - t0:.0f} s", flush=True)
    i07 = int(np.where(KS == 2007)[0][0])
    pl = np.isin(KS, PLACEBO)
    noise = np.nanstd(E[pl], axis=0)
    E07 = E[i07]
    flag = land & (np.abs(E07) >= 0.5) & (np.abs(E07) >= 3 * noise)
    np.savez_compressed(f"{OUT}/coastal_2007_v0.npz", E2007=E07, noise=noise, flag=flag, dist=dist.astype("f4"))

    lat = 90 - 0.1 * np.arange(1801)
    lon = -180 + 0.1 * np.arange(3600)
    north = land & (lat[:, None] > -60)
    W = np.repeat(np.cos(np.deg2rad(lat))[:, None], 3600, axis=1)
    out = ["Coastal step in 2007. Produced by validation/step_screen/03_coastal_2007.py",
           "E(k): change across year k (5 years after minus 5 years before) at the cell, minus the same for the region's interior. Land north of 60 S.", ""]
    coast = north & (dist <= 3)
    out.append(f"== Q1  Is 2007 special? Cells within 3 cells of water: {int(coast.sum())}")
    sh = {int(k): float((np.abs(E[i][coast]) >= 0.5).mean()) for i, k in enumerate(KS)}
    out.append("  share with |E(k)| >= 0.5 K, by year k: " + " ".join(f"{k}:{v:.3f}" for k, v in sh.items()))
    plv = np.array([sh[int(k)] for k in PLACEBO])
    out.append(f"  2007: {sh[2007]:.3f}; placebo years: median {np.median(plv):.3f}, max {plv.max():.3f} ({int(PLACEBO[plv.argmax()])})")
    out.append(f"  positive share of those in 2007: {(E07[coast & (np.abs(E07) >= 0.5)] > 0).mean():.2f}; median E(2007) over coastal cells {np.nanmedian(E07[coast]):+.3f} K")
    q1 = sh[2007] > plv.max()
    out.append(f"  -> {'SPECIAL' if q1 else 'NOT SPECIAL'} by the rule written first")
    out.append("\n== Q2  Is it coastal? By distance to water (cells)")
    out.append("  band      cells    median|E2007|  share |E|>=0.5   flagged share   median E2007")
    fs = []
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 30), (30, 1e9)):
        m = north & (dist > a) & (dist <= b)
        fs.append(flag[m].mean())
        out.append(f"  {a:>3.0f}-{'inf' if b > 1e6 else int(b):<4} {int(m.sum()):8d}      {np.nanmedian(np.abs(E07[m])):.3f}          {(np.abs(E07[m]) >= 0.5).mean():.3f}          {flag[m].mean():.4f}        {np.nanmedian(E07[m]):+.3f}")
    q2 = all(fs[i] >= fs[i + 1] for i in range(len(fs) - 1))
    out.append(f"  -> {'COASTAL' if q2 else 'NOT STEADILY COASTAL'} by the rule written first")
    out.append("\n== Q3  Northern Japan station cells")
    def at(d):
        r = {}
        for n, (la, lo) in d.items():
            i, j = int(round((90 - la) / 0.1)), int(round((lo + 180) / 0.1))
            r[n] = (float(E07[i, j]), float(noise[i, j]), bool(flag[i, j]), float(dist[i, j]))
        return r
    cs, ins = at(COAST_ST), at(INLAND_ST)
    out.append("  coastal (stepped against stations): " + "; ".join(f"{n} {v[0]:+.2f} (noise {v[1]:.2f}, dist {v[3]:.0f}{', flagged' if v[2] else ''})" for n, v in cs.items()))
    out.append("  inland (no step against stations):  " + "; ".join(f"{n} {v[0]:+.2f} (dist {v[3]:.0f}{', flagged' if v[2] else ''})" for n, v in ins.items()))
    n_ok = sum(v[0] >= 0.4 for v in cs.values())
    med_in = float(np.median([v[0] for v in ins.values()]))
    q3 = n_ok >= 7 and med_in < 0.2
    out.append(f"  coastal cells with E >= 0.4 K: {n_ok} of {len(cs)}; inland median {med_in:+.2f} K -> {'RECOVERED' if q3 else 'NOT RECOVERED'} by the rule written first")

    f = flag & north
    out.append(f"\n== Flagged (|E2007| >= 0.5 K and >= 3 x noise), north of 60 S: {int(f.sum())} cells, {W[f].sum() / W[north].sum():.4f} of land area; "
               f"warm {int((E07[f] > 0).sum())}, cold {int((E07[f] < 0).sum())}; within 3 cells of water {f[coast].sum() / max(f.sum(), 1):.2f}; "
               f"share of coastal cells flagged {f[coast].mean():.4f}")
    lab, nl = ndimage.label(f, structure=np.ones((3, 3)))
    sz = ndimage.sum(f, lab, range(1, nl + 1))
    out.append(f"== Largest of {nl} flagged groups")
    for k in np.argsort(sz)[::-1][:30]:
        q = lab == k + 1
        ii, jj = np.nonzero(q)
        out.append(f"  {int(sz[k]):5d} cells  lat {lat[ii].min():6.1f}..{lat[ii].max():6.1f}  lon {lon[jj].min():7.1f}..{lon[jj].max():7.1f}  "
                   f"median E {np.median(E07[q]):+.2f} K  median dist {np.median(dist[q]):.0f}")
    out.append(f"\ntotal {time.time() - t0:.0f} s")
    txt = "\n".join(out)
    with open(f"{res}/coastal_2007.txt", "w") as fh:
        fh.write(txt + "\n")
    print(txt)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ext = [-180.05, 179.95, -90.05, 90.05]
    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=130)
    ax.imshow(np.where(land, 0.0, np.nan), extent=ext, cmap="Greys", vmin=-1, vmax=4, interpolation="nearest")
    big = ndimage.maximum_filter(np.where(f, np.abs(E07), 0), size=5)        # widen flagged cells so they are visible
    sgn = np.where(ndimage.maximum_filter(np.where(f, E07, -9), size=5) > 0, 1, -1)
    im = ax.imshow(np.where(big > 0, big * sgn, np.nan), extent=ext, cmap="RdBu_r", vmin=-2, vmax=2, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7, label="change across 2007 beyond the regional interior, K")
    ax.set_ylim(-60, 85)
    ax.set_title("Cells whose temperature changed across 2007 by 0.5 K or more beyond their region's interior (drawn 5 cells wide)")
    fig.tight_layout()
    fig.savefig(f"{res}/coastal_2007.png")
