"""Siberia 2020 re-tested as a season, on the saved Sakha series.

The published event (Ciavarella et al. 2021) is the January to June 2020 mean
temperature over a large Siberian region, not a June spell. 01 to 03 tested a
16-day June window. This script ranks 2020 over longer windows.

Written on 2026-11-21 BEFORE the first run. Project choices.

  Window total : sum of M (area-mean excess) over the window, as in 03.
  Windows      : 1 Jan to 30 Jun (the published period); 1 May to 30 Jun and
                 1 Jun to 30 Jun for context.
  Pass S       : 2020 ranks in the top 3 of all years for 1 Jan to 30 Jun,
                 judged on moving thresholds; fixed shown beside it.

Expected limit, stated in advance: the detector has a warm-season floor (the
3-day mean must exceed the all-year median, or the all-year 95th percentile),
so winter and early spring warmth in Sakha cannot register however large the
anomaly. The January to June total is therefore mostly a May to June total.
Also, Sakha is one unit; the published region is wider.

Run:  bash tools/py.sh -W ignore validation/event_suite/04_siberia_season.py
Output: validation/event_suite/results/siberia_season.txt
"""
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SER = "E:/temp/agera5/derived-products/heat-explorer/event-suite/SAK_series.csv.gz"
WINDOWS = [("1 Jan to 30 Jun", (1, 1), (6, 30)), ("1 May to 30 Jun", (5, 1), (6, 30)), ("1 Jun to 30 Jun", (6, 1), (6, 30))]

if __name__ == "__main__":
    s = pd.read_csv(SER, index_col=0, parse_dates=True)
    out = ["Siberia 2020 as a season, Sakha. Produced by validation/event_suite/04_siberia_season.py"]
    for v in ("moving", "fixed"):
        out.append(f"\n== {v} thresholds")
        for lab, (m0, d0), (m1, d1) in WINDOWS:
            tot, days, first = {}, {}, {}
            for y in range(1979, 2026):
                w = s.loc[pd.Timestamp(y, m0, d0):pd.Timestamp(y, m1, d1)]
                tot[y] = float(w[f"M_{v}"].fillna(0).sum())
                on = w[f"share_any_{v}"] >= 0.25
                days[y] = int(on.sum())
                first[y] = str(on.idxmax().date())[5:] if on.any() else "none"
            tot = pd.Series(tot)
            rank = int((tot > tot[2020]).sum()) + 1
            top = " ".join(f"{y}:{x:.1f}" for y, x in tot.sort_values(ascending=False).head(5).items())
            out.append(f"{lab}: 2020 total {tot[2020]:.1f}, rank {rank} of {len(tot)}, spell days {days[2020]}, "
                       f"first spell day {first[2020]}; top5 {top}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "siberia_season.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)
