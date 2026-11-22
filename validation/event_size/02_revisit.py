"""Event size revisited: should intensity count, and how?

After severe area-days (S2) was adopted, the mock showed two things: a day
with the whole unit extreme scores the same as a day with it merely severe,
and an October warm spell can outrank a midsummer heat dome. Two candidates
that reward intensity are added here to the two that tied in 01_compare.py:

  S2  severe area-days       sum over days of the severe-or-extreme share
  S4  class-weighted         sum of spell + severe + extreme shares (1, 2, 3)
  S5  severe plus extreme    sum of severe-or-extreme share + extreme share
                             (an extreme cell-day counts twice, no other weight)
  S7  degree-days            sum over days of the area-mean number of degrees
                             (K) by which cells in a heat spell exceed their
                             heat threshold. Read from the store: excess (in
                             units of local spread) times that spread. Not
                             capped, in a physical unit, and it needs a field
                             that is not in the admin series.

Part A: the 29 registered unit-windows, rank of the event year's window total
among 47 years (as in 01_compare.py).
Part B: the 13 landmark unit-events of the first event suite
(validation/event_suite/01_adm_events.py). The admin event with the most days
inside the documented window is ranked among all admin events at that unit,
1979 to 2026, by its whole size. These are the events the project was tuned
on; all are widely documented as exceptional.
Part C, described only: of each unit's 10 largest events, the share that began
in the three summer months (June to August north of 23 N, December to February
south of 23 S; units between are left out). An even spread would be 25 percent.

Choice rule, written on 2026-11-22 before the run:
  S2 stays unless a candidate has at least as many top-3 windows in Part A as
  S2 AND at least 2 more landmark events in the top 3 in Part B. Among
  candidates that meet both, prefer S5, then S7, then S4 (S5 is the smallest
  change; S7 needs a new product; S4 has weights with no reason behind them).
This is the second post hoc look at event size on events already seen. It
chooses between measures; it does not show any of them is right.

Run:  bash tools/py.sh -W ignore validation/event_size/02_revisit.py
Output: validation/event_size/results/revisit.txt, revisit_A.csv, revisit_B.csv
"""
import importlib.util
import os

import numpy as np
import pandas as pd
import zarr

HERE = os.path.dirname(os.path.abspath(__file__))
VAL = os.path.join(HERE, "..")
V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
SHARE_DAY, GAP, MIN_DAYS = 0.25, 2, 3
KS = ("S2", "S4", "S5", "S7")


def events(on):
    idx = np.flatnonzero(on)
    if idx.size == 0:
        return []
    brk = np.flatnonzero(np.diff(idx) > GAP + 1)
    lo, hi = np.r_[idx[0], idx[brk + 1]], np.r_[idx[brk], idx[-1]]
    return [(s, e) for s, e in zip(lo, hi) if on[s:e + 1].sum() >= MIN_DAYS]


if __name__ == "__main__":
    g = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(g["time"][:], unit="D"))
    LK = np.load(f"{V1}/admin/lookup.npz")
    U = {lv: pd.read_csv(f"{V1}/admin/units_adm{lv}.csv") for lv in (1, 2)}
    lat_all = 90 - 0.1 * np.arange(1801)
    cache = {}

    def series(lv, uid):
        if (lv, uid) in cache:
            return cache[(lv, uid)]
        hit = np.where(U[lv][f"adm{lv}_id"].values == uid)[0]
        assert len(hit) == 1, (lv, uid, len(hit))
        m = LK[f"adm{lv}"] == int(hit[0])
        ii, jj = np.where(m)
        i0, i1, j0, j1 = ii.min(), ii.max() + 1, jj.min(), jj.max() + 1
        ms = m[i0:i1, j0:j1]
        c = g["cls_day"][:, i0:i1, j0:j1][:, ms]
        x = g["excess"][:, i0:i1, j0:j1][:, ms].astype("f4")
        iqr = g["allyear"][2, i0:i1, j0:j1][ms]
        w = np.cos(np.deg2rad(np.repeat(lat_all[i0:i1][:, None], j1 - j0, axis=1)[ms]))
        w /= w.sum()
        sp = (c >= 1) & (c <= 3)
        lv_ = sp.copy()
        lv_[2:] &= sp[1:-1] & sp[:-2]
        lv_[:2] = False
        s = pd.DataFrame({"spell": lv_ @ w, "severe": (lv_ & (c >= 2)) @ w, "extreme": (lv_ & (c == 3)) @ w,
                          "S7": (np.nan_to_num(x) * lv_ * iqr[None, :]) @ w}, index=idx)
        s["S2"], s["S4"], s["S5"] = s.severe, s.spell + s.severe + s.extreme, s.severe + s.extreme
        cache[(lv, uid)] = (s, float((lat_all[ii] * 1.0).mean()))
        return cache[(lv, uid)]

    out = ["Event size revisited. Produced by validation/event_size/02_revisit.py", ""]
    pd.set_option("display.width", 300, "display.max_columns", 30)

    rows = []
    for suite in ("heldout_suite", "heldout_suite_2", "heldout_suite_3"):
        ev = pd.read_csv(os.path.join(VAL, suite, "events.csv"))
        for u in ev.itertuples():
            if getattr(u, "primary", 1) != 1:
                continue
            s, _ = series(int(getattr(u, "level", 1)), u.unit_id)
            a, b = pd.Timestamp(u.window_start), pd.Timestamp(u.window_end)
            row = {"event": u.event, "unit": u.unit_name, "days": (b - a).days + 1}
            for k in KS:
                tot = pd.Series({y: float(s[k].loc[a.replace(year=y):a.replace(year=y) + (b - a)].sum()) for y in range(1979, 2026)})
                row[k] = int((tot > tot[a.year]).sum()) + 1
            rows.append(row)
    RA = pd.DataFrame(rows)
    RA.to_csv(os.path.join(HERE, "results", "revisit_A.csv"), index=False)
    out.append(f"== Part A. Window rank among 47 years, {len(RA)} registered unit-windows")
    out.append(RA.to_string(index=False))
    for k in KS:
        out.append(f"   {k}: first {int((RA[k] == 1).sum())}, top 3 {int((RA[k] <= 3).sum())} of {len(RA)}, sum of ranks {int(RA[k].sum())}, worst {int(RA[k].max())}")

    spec = importlib.util.spec_from_file_location("adm01", os.path.join(VAL, "event_suite", "01_adm_events.py"))
    a1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a1)
    rows, summer = [], {k: [] for k in KS}
    seen = set()
    for name, key, d0, d1 in a1.EVENTS:
        lv, uid, label = a1.UNITS[key]
        s, ulat = series(lv, uid)
        evs = events(s.spell.values >= SHARE_DAY)
        k0, k1 = int(np.where(idx == pd.Timestamp(d0))[0][0]), int(np.where(idx == pd.Timestamp(d1))[0][0])
        ov = [max(0, min(e, k1) - max(st, k0) + 1) for st, e in evs]
        row = {"event": name, "unit": label, "window_days": k1 - k0 + 1, "n_events": len(evs)}
        if not evs or max(ov) == 0:
            row.update({k: 9999 for k in KS})
            row["event_dates"] = "no admin event in the window"
        else:
            q = int(np.argmax(ov))
            row["event_dates"] = f"{idx[evs[q][0]].date()}..{idx[evs[q][1]].date()}"
            for k in KS:
                sz = np.array([s[k].values[st:e + 1].sum() for st, e in evs])
                row[k] = int((sz > sz[q]).sum()) + 1
                row[k + "_size"] = round(float(sz[q]), 1)
        rows.append(row)
        if key not in seen and abs(ulat) > 23 and evs:
            seen.add(key)
            mon = np.array([idx[st].month for st, _ in evs])
            hot = np.isin(mon, (6, 7, 8) if ulat > 0 else (12, 1, 2))
            for k in KS:
                sz = np.array([s[k].values[st:e + 1].sum() for st, e in evs])
                summer[k].append(float(hot[np.argsort(sz)[-10:]].mean()))
    RB = pd.DataFrame(rows)
    RB.to_csv(os.path.join(HERE, "results", "revisit_B.csv"), index=False)
    out.append(f"\n== Part B. Rank of the landmark event among all admin events at its unit, {len(RB)} unit-events")
    out.append(RB[["event", "unit", "event_dates", "n_events", "S2", "S4", "S5", "S7", "S2_size", "S5_size", "S7_size"]].to_string(index=False))
    for k in KS:
        out.append(f"   {k}: first {int((RB[k] == 1).sum())}, top 3 {int((RB[k] <= 3).sum())} of {len(RB)}, top 10 {int((RB[k] <= 10).sum())}, median rank {np.median(RB[k]):.0f}, worst {int(RB[k].max())}")
    out.append(f"\n== Part C. Of a unit's 10 largest events, share that began in the three summer months ({len(seen)} units outside the tropics; even spread 25%)")
    for k in KS:
        out.append(f"   {k}: mean {np.mean(summer[k]):.0%}, range {min(summer[k]):.0%} to {max(summer[k]):.0%}")

    a2, b2 = int((RA.S2 <= 3).sum()), int((RB.S2 <= 3).sum())
    okc = [k for k in ("S5", "S7", "S4") if (RA[k] <= 3).sum() >= a2 and (RB[k] <= 3).sum() >= b2 + 2]
    out.append(f"\nBy the rule written first: candidates that match S2 in Part A and beat it by 2 or more in Part B: {okc or 'none'}. Choice: {okc[0] if okc else 'S2 stays'}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "revisit.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
