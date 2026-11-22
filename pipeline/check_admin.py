"""Checks on the admin series written by pipeline/admin_series.py.

1. Values: every share is 0 to 10000 or 65535; extreme <= severe <= spell.
2. Reproduction of a registered result: the third held-out suite's largest
   severe share and largest spell share in each unit's window
   (validation/heldout_suite_3/results/units.csv), and the unit's cell count.
   That suite rasterised each unit alone; this lookup rasterises all at once,
   so a cell on a shared edge can differ. Same = within 0.011.
3. Levels agree: a country's share equals the area-weighted mean of its adm1
   units' shares (largest difference over all days, all countries).
4. How often is a unit "severe over most of the area" (share 0.50 or more),
   and how often would lower limits be met? Days per year, 1991-2020 and
   2021-2025. The lower limits are printed to inform the middle status tier,
   which is not frozen; nothing is chosen here.
5. Size on disk.

Run:  bash tools/py.sh -W ignore pipeline/check_admin.py
Output: pipeline/results/check_admin.txt
"""
import os

import numpy as np
import pandas as pd
import zarr

HERE = os.path.dirname(os.path.abspath(__file__))
A = "E:/temp/agera5/derived-products/heat-explorer/v1/admin"
LEVELS = ("adm0", "adm1", "adm2")

if __name__ == "__main__":
    g = zarr.open_group(f"{A}/series.zarr", mode="r")
    days = g["time"][:]
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    U = {k: pd.read_csv(f"{A}/units_{k}.csv") for k in LEVELS}
    out, fails = [f"Checks on {A}/series.zarr. Produced by pipeline/check_admin.py", f"{len(days)} days, {idx[0].date()} to {idx[-1].date()}"], []
    D = {k: {m: g[f"{k}_{m}"][:] for m in ("spell", "severe", "extreme")} for k in LEVELS}

    out.append("\n1. Values")
    for k in LEVELS:
        s, v, e = D[k]["spell"], D[k]["severe"], D[k]["extreme"]
        none = s[0] == 65535
        tail = int(dict(g.attrs).get("unclassed_tail_days", 0)); nd = s.shape[0] - tail      # the last days hold 65535: not yet classed
        bad = int(((s[:nd, ~none] > 10000) | (v[:nd, ~none] > s[:nd, ~none]) | (e[:nd, ~none] > v[:nd, ~none])).sum()) + int((s[nd:] != 65535).sum())
        out.append(f"   {k}: {s.shape[1]:,} units, {int((~none).sum()):,} with land cells; unit-days out of range or out of order: {bad}")
        if bad:
            fails.append(f"values {k}")

    out.append("\n2. Third held-out suite from the admin series")
    ev = pd.read_csv(os.path.join(HERE, "..", "validation", "heldout_suite_3", "events.csv"))
    reg = pd.read_csv(os.path.join(HERE, "..", "validation", "heldout_suite_3", "results", "units.csv"))
    for u, rr in zip(ev.itertuples(), reg.itertuples()):
        hit = np.where(U["adm1"].adm1_id.values == u.unit_id)[0]
        if len(hit) != 1:
            out.append(f"   {u.unit_name:22s} unit id {u.unit_id} found {len(hit)} times")
            fails.append(f"heldout3 id {u.unit_name}")
            continue
        j = int(hit[0])
        k0, k1 = int(np.where(idx == pd.Timestamp(u.window_start))[0][0]), int(np.where(idx == pd.Timestamp(u.window_end))[0][0])
        sev, sp = D["adm1"]["severe"][k0:k1 + 1, j].max() / 1e4, D["adm1"]["spell"][k0:k1 + 1, j].max() / 1e4
        ok = abs(sev - rr.max_share_sev) < 0.011 and abs(sp - rr.max_share_spell) < 0.011
        out.append(f"   {u.unit_name:22s} cells {int(U['adm1'].land_cells[j]):5d} (registered {rr.cells:5d})  severe {sev:.2f} ({rr.max_share_sev:.2f})  spell {sp:.2f} ({rr.max_share_spell:.2f})  {'same' if ok else 'DIFFERENT'}")
        if not ok:
            fails.append(f"heldout3 {u.unit_name}")

    out.append("\n3. Country share against the area-weighted mean of its adm1 units")
    lk = np.load(f"{A}/lookup.npz")
    lat = 90 - 0.1 * np.arange(1801)
    w = np.repeat(np.cos(np.deg2rad(lat))[:, None], 3600, axis=1)
    ok1 = lk["adm1"] >= 0
    w1 = np.bincount(lk["adm1"][ok1], weights=w[ok1], minlength=len(U["adm1"]))
    code = pd.Series(np.arange(len(U["adm0"])), index=U["adm0"].adm0_id).reindex(U["adm1"].adm0_id).values
    worst = 0.0
    for c in range(len(U["adm0"])):
        m = (code == c) & (w1 > 0)
        if not m.any():
            continue
        est = (D["adm1"]["severe"][:, m].astype("f8") * w1[m]).sum(axis=1) / w1[m].sum()
        worst = max(worst, float(np.abs(est - D["adm0"]["severe"][:, c]).max()) / 1e4)
    out.append(f"   largest difference in severe share, any country, any day: {worst:.4f} (rounding of the stored shares allows about 0.0001)")
    if worst > 0.0005:
        fails.append("levels disagree")

    out.append("\n4. Days per year a unit's severe share reaches a limit; median (5th to 95th percentile) over units with at least 9 land cells")
    yr = idx.year.values
    per = {"1991-2020": ((yr >= 1991) & (yr <= 2020), 30), "2021-2025": ((yr >= 2021) & (yr <= 2025), 5)}
    for k in LEVELS:
        big = (U[k].land_cells.values >= 9)
        out.append(f"   {k} ({int(big.sum()):,} units)")
        for lim in (0.50, 0.25, 0.10):
            parts = []
            for nm, (m, ny) in per.items():
                d = (D[k]["severe"][m][:, big] >= lim * 1e4).sum(axis=0) / ny
                parts.append(f"{nm}: {np.median(d):5.1f} ({np.percentile(d, 5):4.1f} to {np.percentile(d, 95):5.1f})")
            out.append(f"      share >= {lim:.2f}   " + "   ".join(parts))

    out.append("\n6. Degree-days (event size ingredient)")
    for k in LEVELS:
        dd = g[f"{k}_degdays"][:]
        none = dd[0] == 65535
        stray = int(((dd[:, ~none] > 0) & (D[k]["spell"][:, ~none] == 0)).sum())
        out.append(f"   {k}: unit-days with degree-days above zero but no area in a heat spell: {stray}; largest daily value {dd[:, ~none].max() / 1000:.1f} K")
        if stray:
            fails.append(f"degdays stray {k}")
    rb = os.path.join(HERE, "..", "validation", "event_size", "results", "revisit_B.csv")
    if os.path.exists(rb):
        import importlib.util
        spec = importlib.util.spec_from_file_location("adm01", os.path.join(HERE, "..", "validation", "event_suite", "01_adm_events.py"))
        a1 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(a1)
        ids = {lab: (lv, uid) for lv, uid, lab in a1.UNITS.values()}
        dd1 = g["adm1_degdays"]
        for r in pd.read_csv(rb).itertuples():
            lv, uid = ids[r.unit]
            if lv != 1 or ".." not in str(r.event_dates):
                continue
            j = int(np.where(U["adm1"].adm1_id.values == uid)[0][0])
            a, b = (pd.Timestamp(v) for v in r.event_dates.split(".."))
            k0, k1 = int(np.where(idx == a)[0][0]), int(np.where(idx == b)[0][0])
            v = dd1[k0:k1 + 1, j].sum() / 1000
            ok = abs(v - r.S7_size) < 0.1
            out.append(f"   {r.unit:18s} {r.event_dates}  series {v:6.1f}  computed from the cells in 02_revisit.py {r.S7_size:6.1f}  {'same' if ok else 'DIFFERENT'}")
            if not ok:
                fails.append(f"degdays {r.unit}")

    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(f"{A}/series.zarr") for f in fs)
    out.append(f"\n5. Size on disk: {size / 1e9:.2f} GB")
    out.append(f"\nRESULT: {'ALL CHECKS PASS' if not fails else 'FAILED: ' + '; '.join(fails)}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "check_admin.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
