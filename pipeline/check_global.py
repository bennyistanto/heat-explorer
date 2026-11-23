"""Checks on the global heat-state store written by pipeline/run_global.py.

1. Completeness: every AgERA5 land cell has a value; count against 2,395,758.
2. Codes: cls_day holds only 0, 1, 2, 3 on land, 255 on sea, 254 where declined.
3. Equality with an independent path: the 17 test windows (11 x 11 cells each)
   were extracted from the raw files on 2026-11-20 by a different script. The
   detector is run on those arrays here and compared with the same cells in
   the store, day for day.
4. Reproduction of a registered result: the admin shares of the third
   held-out suite (validation/heldout_suite_3/results/units.csv), recomputed
   from the store for the same units and windows.
5. Thresholds: the 95th is not below the 90th, the 99th not below the 95th.
6. Plausibility: days per year in a spell and severe, baseline and 2021-2025.
7. Size on disk.

Run:  bash tools/py.sh -W ignore pipeline/check_global.py
Output: pipeline/results/check_global.txt, days_per_year.png
"""
import os
import sys

import numpy as np
import pandas as pd
import zarr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from pipeline import detector  # noqa: E402

V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
CELLS = "E:/temp/agera5/derived-products/heat-explorer/critique-2026-11-20/hx_cells.npz"
SITES = {"Singapore": (1.35, 103.8), "Jakarta": (-6.2, 106.8), "Lagos": (6.6, 3.4), "Manaus": (-3.1, -60.0), "Delhi": (28.6, 77.2),
         "Jacobabad": (28.3, 68.4), "Hyderabad_IN": (17.4, 78.5), "Dhahran": (26.3, 50.1), "Phoenix": (33.4, -112.1), "Paris": (48.9, 2.3),
         "Moscow": (55.8, 37.6), "Portland_OR": (45.5, -122.6), "Sydney_W": (-33.8, 150.9), "Nairobi": (-1.3, 36.8), "LaPaz": (-16.5, -68.2),
         "Verkhoyansk": (67.5, 133.4), "DomeC": (-75.1, 123.3)}

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    g = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")
    C, days = g["cls_day"], g["time"][:]
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    out = [f"Checks on {V1}/heat_state.zarr. Produced by pipeline/check_global.py", f"detector version {dict(g.attrs).get('detector_version')}; {len(days)} days, {idx[0].date()} to {idx[-1].date()}"]
    fails = []

    first = C[0]
    land = first != 255
    n_land, n_dec = int(land.sum()), int((first == 254).sum())
    out.append(f"\n1. Land cells in the store: {n_land:,} (AgERA5 land cells measured earlier: 2,395,758). Declined by the detector: {n_dec:,}")
    if n_land != 2395758:
        fails.append("land cell count")

    S = np.load(f"{V1}/run_summary_global.npz")["days_per_year"]
    z = np.load(CELLS)
    nz = len(z["time"])                                                        # the windows were extracted when the record was shorter
    same_time = np.array_equal(z["time"], days[:nz])
    cut = 4 if nz < len(days) else 0                                           # a run at the end of the shorter record can still grow into a spell: those days are left out
    zd = days[:nz]
    out.append(f"\n3. Independent path, 17 windows, first {nz - cut:,} days (the windows' time axis is the start of the store's: {same_time})")
    vals, tot_diff, tot_days = set(), 0, 0
    for s, (la, lo) in SITES.items():
        i, j = int(round((90 - la) / 0.1)), int(round((lo + 180) / 0.1))
        st = C[:nz, i - 5:i + 6, j - 5:j + 6].reshape(nz, -1)
        vals |= set(np.unique(st).tolist())
        tx, tn = z[f"t2mmax__{s}"].astype("f4").reshape(nz, -1), z[f"t2mmin__{s}"].astype("f4").reshape(nz, -1)
        ld = tx[0] != -9999.0
        tm = np.full((nz, int(ld.sum())), np.nan, "f4")
        tm[:-1] = ((tx[:-1, ld] - np.float32(273.15)) + (tn[1:, ld] - np.float32(273.15))) / 2
        r = detector.detect_block(tm, zd)
        tail = int(dict(g.attrs).get("unclassed_tail_days", 0))               # those days hold 253 in the store
        nd = nz - cut if cut else nz - tail
        d = int((st[:nd, ld] != r["cls_day"][:nd]).sum()) + (0 if cut else int((st[nd:, ld] != 253).sum()))
        mask_ok = bool(np.array_equal(st[0] != 255, ld))
        tot_diff += d
        tot_days += r["cls_day"][:nd].size
        out.append(f"   {s:13s} land cells {int(ld.sum()):3d}  land mask equal: {mask_ok}  differing cell-days: {d}")
        if d or not mask_ok:
            fails.append(f"independent path {s}")
    out.append(f"   total differing cell-days: {tot_diff:,} of {tot_days:,}")
    out.append(f"\n2. Codes seen in those windows: {sorted(vals)} (allowed: 0, 1, 2, 3, 253, 254, 255)")
    if not vals <= {0, 1, 2, 3, 253, 254, 255}:
        fails.append("codes")

    out.append("\n4. Third held-out suite, admin shares recomputed from the store")
    import pyarrow.parquet as pq
    import shapely
    from rasterio import features
    from rasterio.transform import from_origin
    ev = pd.read_csv(os.path.join(HERE, "..", "validation", "heldout_suite_3", "events.csv"))
    reg = pd.read_csv(os.path.join(HERE, "..", "validation", "heldout_suite_3", "results", "units.csv"))
    lat_all = 90 - 0.1 * np.arange(1801)
    for u, rr in zip(ev.itertuples(), reg.itertuples()):
        t = pq.read_table("E:/temp/boundaries/adm1/adm1_polygons.parquet", columns=["adm1_id", "geometry"], filters=[("adm1_id", "in", [u.unit_id])])
        gm = shapely.from_wkb(t.column("geometry")[0].as_py())
        x0, y0, x1, y1 = gm.bounds
        i0, i1 = int(np.floor((90 - y1) / 0.1)), int(np.ceil((90 - y0) / 0.1))
        j0, j1 = int(np.floor((x0 + 180) / 0.1)), int(np.ceil((x1 + 180) / 0.1))
        m = features.rasterize([(gm, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1), transform=from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1), dtype="uint8").astype(bool)
        a, b = pd.Timestamp(u.window_start), pd.Timestamp(u.window_end)
        k0, k1 = int(np.where(idx == a)[0][0]), int(np.where(idx == b)[0][0])
        x = C[k0 - 2:k1 + 1, i0:i1 + 1, j0:j1 + 1][:, m]
        ld = x[0] != 255
        x = x[:, ld]
        w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1 + 1][:, None], m.shape[1], axis=1)[m][ld]))
        w /= w.sum()
        sp = (x >= 1) & (x <= 3)
        live = sp[2:] & sp[1:-1] & sp[:-2]
        sev = float((((x[2:] >= 2) & (x[2:] <= 3) & live) @ w).max())
        okk = abs(round(sev, 2) - rr.max_share_sev) < 0.011
        out.append(f"   {u.event:34s} {u.unit_name:22s} store {sev:.2f}  registered {rr.max_share_sev:.2f}  {'same' if okk else 'DIFFERENT'}")
        if not okk:
            fails.append(f"heldout3 {u.unit_name}")

    out.append("\n5. Thresholds")
    bad = 0
    for r0 in range(0, 1801, 200):
        t = g["thr"][:, :, r0:r0 + 200, :]
        with np.errstate(invalid="ignore"):
            bad += int(((t[:, 1] < t[:, 0]) | (t[:, 2] < t[:, 1])).sum())
    out.append(f"   cell-days where the 95th is below the 90th or the 99th below the 95th: {bad}")
    if bad:
        fails.append("threshold order")

    out.append("\n6. Days per year, median and 5th to 95th percentile across land cells north of 60 S")
    north = np.repeat((lat_all > -60)[:, None], 3600, axis=1) & np.isfinite(S[0])
    for k, nm in enumerate(("in a heat spell, 1991-2020", "severe or extreme, 1991-2020", "in a heat spell, 2021-2025", "severe or extreme, 2021-2025")):
        v = S[k][north]
        out.append(f"   {nm:30s} median {np.median(v):5.1f}   5th {np.percentile(v, 5):5.1f}   95th {np.percentile(v, 95):6.1f}")

    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(f"{V1}/heat_state.zarr") for f in fs)
    out.append(f"\n7. Size on disk: {size / 1e9:.1f} GB")
    out.append(f"\nRESULT: {'ALL CHECKS PASS' if not fails else 'FAILED: ' + '; '.join(fails)}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "check_global.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, 1, figsize=(13, 11), dpi=120)
    for ax, k, ttl, vm in ((axs[0], 1, "Severe or extreme days per year, 1991-2020 (detector 1.0)", 30), (axs[1], 3, "Severe or extreme days per year, 2021-2025", 120)):
        im = ax.imshow(S[k], extent=[-180.05, 179.95, -90.05, 90.05], cmap="magma_r", vmin=0, vmax=vm, interpolation="nearest")
        fig.colorbar(im, ax=ax, shrink=0.8, label="days per year")
        ax.set_ylim(-60, 85)
        ax.set_title(ttl)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "results", "days_per_year.png"))
