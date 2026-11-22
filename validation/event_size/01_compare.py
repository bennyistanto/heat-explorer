"""Which number should say how big a heat event is?

Detector version 1.0 freezes the class of a day. It does not freeze the size
of an event. The measure used so far ("S1": daily excess over the threshold in
units of local spread, averaged over the area, summed over the event) is not
built from the frozen classes and has no plain unit. Three candidates that are
built only from the frozen admin series, all in "area-days" (1.0 = the whole
unit for one day), are compared with it here:

  S2  severe area-days      sum over days of the share of area severe or extreme
  S3  spell area-days       sum over days of the share of area in a heat spell
  S4  class-weighted        sum over days of spell + severe + extreme shares
                            (a cell-day scores 1, 2 or 3)

Part A, registered events. For each primary unit of the three held-out suites
(29 unit-windows), the window total in the event year is ranked among the same
dates in 1979 to 2025, as the suites did for S1. S1's ranks are read from the
suites' result files, not recomputed. Suites 1 and 2 classed severity
differently from version 1.0, which affects none of S2 to S4 here.

Part B, every adm1 unit with at least 9 land cells. Admin events by the rule
used so far (validation/event_suite/02_event_rank.py: a quarter of the area in
a heat spell, gaps of up to 2 days merged, at least 3 such days): how many a
year, how long, and whether S2, S3 and S4 put a unit's events in the same order.

Choice rule, written on 2026-11-22 before the run:
  Take the candidate with the most Part A windows ranked in the top 3; ties
  broken by the lower sum of ranks. If candidates are within one window of
  each other, prefer S2, then S4, then S3: S2 rests on the class that is even
  through the year, S4 adds arbitrary weights, S3 rests on the flag that is
  known to be uneven through the year.
  A candidate is NOT adopted if it has 2 or more fewer top-3 windows than S1.
This is post hoc for all four measures: these 29 windows have been looked at
before, and S1's ranks were known. It can choose between measures; it is not
evidence that the chosen one is right.

Run:  bash tools/py.sh -W ignore validation/event_size/01_compare.py
Output: validation/event_size/results/compare.txt, ranks.csv
"""
import os

import numpy as np
import pandas as pd
import zarr
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
VAL = os.path.join(HERE, "..")
A = "E:/temp/agera5/derived-products/heat-explorer/v1/admin"
CONF = "E:/temp/agera5/derived-products/heat-explorer/confidence/confidence_v0.npz"
SHARE_DAY, GAP, MIN_DAYS = 0.25, 2, 3


def events(on):
    idx = np.flatnonzero(on)
    if idx.size == 0:
        return []
    brk = np.flatnonzero(np.diff(idx) > GAP + 1)
    lo, hi = np.r_[idx[0], idx[brk + 1]], np.r_[idx[brk], idx[-1]]
    return [(s, e) for s, e in zip(lo, hi) if on[s:e + 1].sum() >= MIN_DAYS]


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    g = zarr.open_group(f"{A}/series.zarr", mode="r")
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(g["time"][:], unit="D"))
    D = {lv: {m: g[f"adm{lv}_{m}"] for m in ("spell", "severe", "extreme")} for lv in (1, 2)}
    U = {lv: pd.read_csv(f"{A}/units_adm{lv}.csv") for lv in (1, 2)}
    out = ["Event size measures compared. Produced by validation/event_size/01_compare.py", ""]

    # ---- Part A
    rows = []
    for suite in ("heldout_suite", "heldout_suite_2", "heldout_suite_3"):
        ev = pd.read_csv(os.path.join(VAL, suite, "events.csv"))
        reg = pd.read_csv(os.path.join(VAL, suite, "results", "units.csv"))
        for u, rr in zip(ev.itertuples(), reg.itertuples()):
            assert u.unit_name == rr.unit
            if getattr(u, "primary", 1) != 1:
                continue
            lv = int(getattr(u, "level", 1))
            hit = np.where(U[lv][f"adm{lv}_id"].values == u.unit_id)[0]
            if len(hit) != 1:
                out.append(f"   unit not found once: {suite} {u.unit_name} {u.unit_id} ({len(hit)})")
                continue
            j = int(hit[0])
            s = pd.DataFrame({m: D[lv][m][:, j] / 1e4 for m in ("spell", "severe", "extreme")}, index=idx)
            meas = {"S2": s.severe, "S3": s.spell, "S4": s.spell + s.severe + s.extreme}
            a, b = pd.Timestamp(u.window_start), pd.Timestamp(u.window_end)
            row = {"suite": suite[-1] if suite[-1].isdigit() else "1", "event": u.event, "unit": u.unit_name, "confidence": u.confidence, "days": (b - a).days + 1, "S1": int(rr.rank)}
            for k, v in meas.items():
                tot = {}
                for y in range(1979, 2026):
                    a2 = a.replace(year=y)
                    tot[y] = float(v.loc[a2:a2 + (b - a)].sum())
                tot = pd.Series(tot)
                row[k] = int((tot > tot[a.year]).sum()) + 1
                row[k + "_tied_first"] = int((tot == tot[a.year]).sum()) if row[k] == 1 else 0
                row[k + "_value"] = round(tot[a.year], 2)
            rows.append(row)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(HERE, "results", "ranks.csv"), index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30)
    out.append(f"== Part A. Rank of the event year's window total among 47 years, {len(R)} primary unit-windows")
    out.append(R[["suite", "event", "unit", "confidence", "days", "S1", "S2", "S3", "S4", "S2_value", "S3_value", "S4_value"]].to_string(index=False))
    out.append("")
    summ = {}
    for k in ("S1", "S2", "S3", "S4"):
        summ[k] = (int((R[k] <= 3).sum()), int(R[k].sum()))
        tie = f"; ranked first but tied with another year: {int((R[k + '_tied_first'] > 1).sum())}" if k != "S1" else ""
        out.append(f"   {k}: first {int((R[k] == 1).sum())}, top 3 {summ[k][0]} of {len(R)}, sum of ranks {summ[k][1]}, worst {int(R[k].max())}{tie}")
    cand = sorted(("S2", "S3", "S4"), key=lambda k: (-summ[k][0], summ[k][1]))
    best = cand[0]
    close = [k for k in ("S2", "S4", "S3") if summ[best][0] - summ[k][0] <= 1]
    pick = close[0]
    ok = summ["S1"][0] - summ[pick][0] < 2
    out.append(f"   By the rule written first: most top-3 windows {best}; within one window of it {close}; preferred {pick}; "
               f"{'ADOPTABLE' if ok else 'NOT ADOPTED: 2 or more fewer top-3 windows than S1'}")

    # ---- Part B
    out.append("\n== Part B. Admin events at adm1 units with at least 9 land cells, 1979 to 2025")
    sp, sv, ex = (D[1][m][:] / 1e4 for m in ("spell", "severe", "extreme"))
    keep = np.asarray(idx.year <= 2025)
    sp, sv, ex, ix = sp[keep], sv[keep], ex[keep], idx[keep]
    yr = ix.year.values
    lk = np.load(f"{A}/lookup.npz")["adm1"]
    sd = np.load(CONF)["sd"]
    okc = (lk >= 0) & np.isfinite(sd)
    usd = np.full(len(U[1]), np.nan)
    med = pd.Series(sd[okc]).groupby(lk[okc]).median()
    usd[med.index.values] = med.values
    big = np.where(U[1].land_cells.values >= 9)[0]
    rec = []
    for j in big:
        evs = events(sp[:, j] >= SHARE_DAY)
        if not evs:
            rec.append({"j": j, "n": 0})
            continue
        ln = np.array([e - s + 1 for s, e in evs])
        m2 = np.array([sv[s:e + 1, j].sum() for s, e in evs])
        m3 = np.array([sp[s:e + 1, j].sum() for s, e in evs])
        m4 = m3 + m2 + np.array([ex[s:e + 1, j].sum() for s, e in evs])
        ys = yr[[s for s, _ in evs]]
        r = {"j": j, "n": len(evs), "per_year_base": ((ys >= 1991) & (ys <= 2020)).sum() / 30, "per_year_recent": (ys >= 2021).sum() / 5,
             "len_med": np.median(ln), "len_max": ln.max(), "zero_S2": float((m2 == 0).mean()), "sd": usd[j]}
        if len(evs) >= 20:
            r["rho_S2_S3"] = stats.spearmanr(m2, m3)[0]
            r["rho_S2_S4"] = stats.spearmanr(m2, m4)[0]
            r["rho_S3_S4"] = stats.spearmanr(m3, m4)[0]
            top = lambda m: set(np.argsort(m)[-5:])
            r["top5_S2_S4"] = len(top(m2) & top(m4))
            r["top5_S3_S4"] = len(top(m3) & top(m4))
            r["top5_recent_S2"] = float((ys[list(top(m2))] >= 2016).mean())
        rec.append(r)
    B = pd.DataFrame(rec)
    Bn = B[B.n > 0]
    q = lambda x: f"{np.nanmedian(x):.2f} ({np.nanpercentile(x, 5):.2f} to {np.nanpercentile(x, 95):.2f})"
    out.append(f"   units: {len(B):,}; with no event at all: {int((B.n == 0).sum())}")
    out.append(f"   events per year, median (5th to 95th percentile of units): 1991-2020 {q(Bn.per_year_base)}; 2021-2025 {q(Bn.per_year_recent)}")
    out.append(f"   event length in days, median over units of the unit's median {np.median(Bn.len_med):.0f}; of the unit's longest {np.median(Bn.len_max):.0f}; "
               f"units whose longest event exceeds 60 days: {(Bn.len_max > 60).mean():.1%}; exceeds 180 days: {(Bn.len_max > 180).mean():.1%}")
    for nm, m in (("low confidence (sd below 1.0 K)", Bn.sd < 1.0), ("reduced (1.0 to 1.5 K)", (Bn.sd >= 1.0) & (Bn.sd < 1.5)), ("normal", Bn.sd >= 1.5)):
        x = Bn[m]
        out.append(f"      {nm:32s} units {len(x):5d}; longest event, median {np.median(x.len_max):4.0f} days, 95th percentile {np.percentile(x.len_max, 95):4.0f}; exceeds 60 days at {(x.len_max > 60).mean():.1%}")
    out.append(f"   share of a unit's events with S2 exactly zero (no severe area at all): {q(Bn.zero_S2)}")
    out.append(f"   rank correlation of event sizes within a unit: S2 with S3 {q(Bn.rho_S2_S3)}; S2 with S4 {q(Bn.rho_S2_S4)}; S3 with S4 {q(Bn.rho_S3_S4)}")
    out.append(f"   of a unit's 5 largest events, how many are the same under S2 and S4: mean {Bn.top5_S2_S4.mean():.2f}; under S3 and S4: mean {Bn.top5_S3_S4.mean():.2f}")
    out.append(f"   of a unit's 5 largest events by S2, share that began in 2016 or later: mean {Bn.top5_recent_S2.mean():.1%} (10 of 47 years is 21%)")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "compare.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
