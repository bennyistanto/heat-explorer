"""Rank each documented event among all admin-level events at its unit.

Replaces criterion P2 of 01_adm_events.py, which asked whether the 5-day peak
was in the top 3 of all years. That tested "largest in the record", and it used
a 5-day peak for events lasting up to 72 days. This script reuses the daily
admin series written by 01 (no raw data is read).

Definitions, written on 2026-11-21 BEFORE this script was first run. All are
project choices, none comes from a published source.

  Admin event day : share_any >= 0.25 (a quarter of the unit's area in a heat
                    spell of any class).
  Admin event     : a run of admin event days, runs separated by 2 days or
                    fewer merged into one, at least 3 event days in total.
  Magnitude       : sum over the event's days (gap days included) of M, the
                    area-mean excess in units of local spread.
  Documented event: the admin event with the largest magnitude among those
                    that overlap the documented window.

Pass criteria:
  P1  (unchanged) share_sev reaches 0.50 on at least one window day.
  P2b the documented event's magnitude is at or above the 95th percentile of
      the magnitudes of all admin events starting in 1991-2020 at that unit.
      This is the same level the design uses for the class "extreme".
  Pass = P1 and P2b, judged on the moving thresholds; fixed shown beside it.

Reported but not part of the pass: rank among all events 1979-2025, the event
count, and the event's start and end dates.

Known when this was written (so not a blind test): the 5-day-peak ranks from
01, and which years held the highest 5-day peaks at the six failing units.

Run:  bash tools/py.sh -W ignore validation/event_suite/02_event_rank.py
Output: validation/event_suite/results/rank_summary.txt, rank_events.csv
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("adm01", os.path.join(HERE, "01_adm_events.py"))
a1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a1)

SHARE_DAY, GAP, MIN_DAYS, PCT = 0.25, 2, 3, 95


def admin_events(share, m):
    """Table of admin events: start, end, event days, magnitude."""
    on = (share.values >= SHARE_DAY)
    idx = np.flatnonzero(on)
    if idx.size == 0:
        return pd.DataFrame(columns=["start", "end", "days", "mag"])
    brk = np.flatnonzero(np.diff(idx) > GAP + 1)
    lo = np.r_[idx[0], idx[brk + 1]]
    hi = np.r_[idx[brk], idx[-1]]
    mv = np.nan_to_num(m.values)
    rows = []
    for s, e in zip(lo, hi):
        nd = int(on[s:e + 1].sum())
        if nd >= MIN_DAYS:
            rows.append((share.index[s], share.index[e], nd, float(mv[s:e + 1].sum())))
    return pd.DataFrame(rows, columns=["start", "end", "days", "mag"])


if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    ser = {k: pd.read_csv(f"{a1.OUT}/{k}_series.csv.gz", index_col=0, parse_dates=True) for k in a1.UNITS}
    rows = []
    for name, key, d0, d1 in a1.EVENTS:
        s = ser[key]
        r = {"event": name, "unit": a1.UNITS[key][2]}
        for v in ("moving", "fixed"):
            ev = admin_events(s[f"share_any_{v}"], s[f"M_{v}"])
            base = ev[(ev.start.dt.year >= 1991) & (ev.start.dt.year <= 2020)]
            thr = float(np.percentile(base.mag, PCT)) if len(base) else np.nan
            hit = ev[(ev.end >= pd.Timestamp(d0)) & (ev.start <= pd.Timestamp(d1))]
            p1 = bool(s.loc[d0:d1, f"share_sev_{v}"].max() >= 0.50)
            if len(hit):
                h = hit.loc[hit.mag.idxmax()]
                rank = int((ev.mag > h.mag).sum()) + 1
                r.update({f"start_{v}": str(h.start.date()), f"end_{v}": str(h.end.date()),
                          f"days_{v}": int(h.days), f"mag_{v}": round(h.mag, 1),
                          f"p95_{v}": round(thr, 1), f"rank_{v}": rank, f"n_events_{v}": len(ev),
                          f"P1_{v}": p1, f"P2b_{v}": bool(h.mag >= thr),
                          f"pass_{v}": bool(p1 and h.mag >= thr)})
            else:
                r.update({f"n_events_{v}": len(ev), f"p95_{v}": round(thr, 1), f"P1_{v}": p1,
                          f"P2b_{v}": False, f"pass_{v}": False})
        rows.append(r)
    t = pd.DataFrame(rows)
    t.to_csv(f"{res}/rank_events.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 40)
    out = ["Event rank among admin events. Produced by validation/event_suite/02_event_rank.py",
           f"Admin event day: share_any >= {SHARE_DAY}; gaps of {GAP} days or fewer merged; at least {MIN_DAYS} event days.",
           f"P2b: magnitude at or above the {PCT}th percentile of admin events starting 1991-2020."]
    for v in ("moving", "fixed"):
        out.append(f"\n== {v} thresholds")
        out.append(t[["event", "unit"] + [c for c in t.columns if c.endswith("_" + v)]].to_string(index=False))
    out.append(f"\nPassed: moving {int(t.pass_moving.sum())} of {len(t)}; fixed {int(t.pass_fixed.sum())} of {len(t)}")
    txt = "\n".join(out)
    with open(f"{res}/rank_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
