"""Season-total test: does a long season of repeated spells stand out by its total?

02_event_rank.py failed the 2022 South Asia cases because the 72-day window
breaks into separate admin events. This script measures the window as a whole.
It reuses the daily admin series written by 01 (no raw data is read).

Definitions, written on 2026-11-21 BEFORE this script was first run. Project
choices, not from a published source.

  Window total : sum of M (area-mean excess in units of local spread) over the
                 documented window.
  Comparison A : the same calendar window in every other year with complete
                 data (the window shifted by whole years).
  Comparison B : the highest total over any window of the same length that
                 starts in each other year (season not matched).
  Spell days   : days in the window with share_any >= 0.25.

Pass criterion S: the documented window ranks in the top 3 under comparison A,
judged on moving thresholds; fixed shown beside it. B is reported only.

The question was raised by the 2022 cases, so those three are the test. The
other ten are run for context: a short window is mostly one event, so S adds
little there.

Known when this was written (not a blind test): results of 01 and 02,
including that the highest 5-day peaks at Rajasthan and Sindh fall in 2024,
2016, 2010 and 1991, in May and June, outside the March to May window.

Run:  bash tools/py.sh -W ignore validation/event_suite/03_season_total.py
Output: validation/event_suite/results/season_summary.txt, season_events.csv
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("adm01", os.path.join(HERE, "01_adm_events.py"))
a1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a1)

if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    ser = {k: pd.read_csv(f"{a1.OUT}/{k}_series.csv.gz", index_col=0, parse_dates=True) for k in a1.UNITS}
    rows = []
    for name, key, d0, d1 in a1.EVENTS:
        s = ser[key]
        t0, t1 = pd.Timestamp(d0), pd.Timestamp(d1)
        n = (t1 - t0).days + 1
        r = {"event": name, "unit": a1.UNITS[key][2], "window_days": n}
        for v in ("moving", "fixed"):
            m = s[f"M_{v}"].fillna(0.0)
            tot, days = {}, {}
            for k in range(1979 - t0.year, 2026 - t0.year):
                a, b = t0 + pd.DateOffset(years=k), t1 + pd.DateOffset(years=k)
                if a < s.index[0] or b > s.index[-1]:
                    continue
                tot[a.year] = float(m.loc[a:b].sum())
                days[a.year] = int((s.loc[a:b, f"share_any_{v}"] >= 0.25).sum())
            tot = pd.Series(tot)
            mine = tot[t0.year]
            roll = m.rolling(n).sum().shift(-(n - 1))            # total of the window starting each day
            best = roll.groupby(roll.index.year).max()
            top = tot.sort_values(ascending=False).head(4)
            r.update({f"total_{v}": round(mine, 1), f"spell_days_{v}": days[t0.year],
                      f"rankA_{v}": int((tot > mine).sum()) + 1, f"years_{v}": len(tot),
                      f"rankB_{v}": int((best.drop(t0.year) > mine).sum()) + 1,
                      f"top4_{v}": " ".join(f"{y}:{x:.1f}" for y, x in top.items()),
                      f"S_{v}": bool((tot > mine).sum() + 1 <= 3)})
        rows.append(r)
    t = pd.DataFrame(rows)
    t.to_csv(f"{res}/season_events.csv", index=False)
    pd.set_option("display.width", 320, "display.max_columns", 40, "display.max_colwidth", 60)
    out = ["Season-total test. Produced by validation/event_suite/03_season_total.py",
           "Window total of M; rank A = same calendar window in other years; rank B = best same-length window in each other year.",
           "S: rank A in the top 3."]
    for v in ("moving", "fixed"):
        out.append(f"\n== {v} thresholds")
        out.append(t[["event", "unit", "window_days"] + [c for c in t.columns if c.endswith("_" + v)]].to_string(index=False))
    q = t[t.event.str.startswith("India-Pakistan 2022")]
    out.append(f"\n2022 South Asia cases passing S: moving {int(q.S_moving.sum())} of {len(q)}; fixed {int(q.S_fixed.sum())} of {len(q)}")
    out.append(f"All cases passing S: moving {int(t.S_moving.sum())} of {len(t)}; fixed {int(t.S_fixed.sum())} of {len(t)}")
    txt = "\n".join(out)
    with open(f"{res}/season_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
