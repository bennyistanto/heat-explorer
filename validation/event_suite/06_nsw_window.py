"""New South Wales 2019-20 season total with a window the sources support.

The window used in 01 and 03 (15 Dec 2019 to 5 Feb 2020) has no support after
early January: the Bureau of Meteorology's summer review (3 Mar 2020) calls
December the hottest on record and puts "a noticeable change to the weather"
in early January. This script repeats the season-total test of 03 on shorter
windows. 01_adm_events.py is left as it was run.

Written on 2026-11-21 BEFORE the first run. Project choices.

  Windows : 15 Dec to 5 Jan (main; "early January" read as the first five
            days, chosen without reference to the detector's event dates);
            15 Dec to 31 Dec (December only); 15 Dec to 5 Feb (the original,
            for comparison).
  Pass S  : the main window ranks in the top 3 of 46 summers by window total
            of M, judged on moving thresholds; fixed shown beside it.

Known when this was written: the original window ranked 2 behind 2018-19, and
the detector's own admin event runs 16 Dec to 10 Jan.

Run:  bash tools/py.sh -W ignore validation/event_suite/06_nsw_window.py
Output: validation/event_suite/results/nsw_window.txt
"""
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SER = "E:/temp/agera5/derived-products/heat-explorer/event-suite/NSW_series.csv.gz"
WINDOWS = [("15 Dec to 5 Jan (main)", "2019-12-15", "2020-01-05"),
           ("15 Dec to 31 Dec", "2019-12-15", "2019-12-31"),
           ("15 Dec to 5 Feb (original)", "2019-12-15", "2020-02-05")]

if __name__ == "__main__":
    s = pd.read_csv(SER, index_col=0, parse_dates=True)
    out = ["New South Wales 2019-20, season total on shorter windows. Produced by validation/event_suite/06_nsw_window.py",
           "Years are labelled by the December in which the window starts."]
    for v in ("moving", "fixed"):
        out.append(f"\n== {v} thresholds")
        m = s[f"M_{v}"].fillna(0)
        for lab, d0, d1 in WINDOWS:
            t0, t1 = pd.Timestamp(d0), pd.Timestamp(d1)
            tot, days = {}, {}
            for k in range(1979 - t0.year, 2025 - t0.year):
                a, b = t0 + pd.DateOffset(years=k), t1 + pd.DateOffset(years=k)
                tot[a.year] = float(m.loc[a:b].sum())
                days[a.year] = int((s.loc[a:b, f"share_any_{v}"] >= 0.25).sum())
            tot = pd.Series(tot)
            rank = int((tot > tot[2019]).sum()) + 1
            top = " ".join(f"{y}:{x:.1f}" for y, x in tot.sort_values(ascending=False).head(4).items())
            out.append(f"{lab}: 2019 total {tot[2019]:.1f}, rank {rank} of {len(tot)}, spell days {days[2019]} of {(t1 - t0).days + 1}; top4 {top}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "nsw_window.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)
