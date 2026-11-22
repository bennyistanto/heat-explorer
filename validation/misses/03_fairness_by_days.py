"""Season fairness measured the right way: severe days as a share of ALL days in each month.

02_calendar_classes.py compared classes by "share of a month's spell days that
are severe". That measure is confounded: in the hottest months the all-year
test admits many ordinary summer days as spell days, which lowers the share
without saying anything about how often a severe day occurs. This script
counts severe days against all baseline days of the month, on the 17 single
cells. POST HOC, diagnosis only.

Run:  bash tools/py.sh -W ignore validation/misses/03_fairness_by_days.py
Output: validation/misses/results/fairness_by_days.txt
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("c02", os.path.join(HERE, "02_calendar_classes.py"))
c2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2)

if __name__ == "__main__":
    det = c2.load("det3", os.path.join(HERE, "..", "detector_v3", "detector.py"))
    z = np.load(det.p1.CELLS)
    c2.init(z["time"])
    idx = c2._D["idx"]
    base = np.asarray((idx.year >= 1991) & (idx.year <= 2020))
    mo = idx.month.values
    rows = []
    for s in det.p1.ELEV:
        g = lambda v: np.where(z[f"{v}__{s}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{s}"][:, 5, 5].astype("f8") - 273.15)
        tm = (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
        _, a, b, _ = c2.cell_job((s, tm))
        # the six warmest calendar months by baseline mean Tm
        mm = pd.Series(tm[base]).groupby(mo[base]).mean().sort_values(ascending=False).index[:6]
        f = lambda c, k: [100 * (c[base & (mo == m)] >= k).mean() for m in mm]
        s0, s2, sp = f(a, 2), f(b, 2), f(a, 1)
        rows.append({"site": s, "spell_min": min(sp), "spell_max": max(sp), "V0_sev_min": min(s0), "V0_sev_max": max(s0), "V2_sev_min": min(s2), "V2_sev_max": max(s2),
                     "V0_ratio": max(s0) / max(min(s0), 0.01), "V2_ratio": max(s2) / max(min(s2), 0.01),
                     "V0_sev_all": 100 * (a[base] >= 2).mean(), "V2_sev_all": 100 * (b[base] >= 2).mean(), "V2_ext_all": 100 * (b[base] >= 3).mean()})
    S = pd.DataFrame(rows).set_index("site")
    pd.set_option("display.width", 250)
    out = ["Severe days as a percentage of all baseline days, in each of the six warmest months of the cell: lowest and highest month.",
           "Produced by validation/misses/03_fairness_by_days.py. POST HOC. ratio = highest month over lowest month; 1 would be perfectly even.",
           S.round(2).to_string(),
           f"\nMedian ratio across the 17 cells: V0 {S.V0_ratio.median():.1f}, V2 {S.V2_ratio.median():.1f}. Cells with ratio above 3: V0 {int((S.V0_ratio > 3).sum())}, V2 {int((S.V2_ratio > 3).sum())}.",
           f"Severe or extreme days, percent of all baseline days, median across cells: V0 {S.V0_sev_all.median():.2f}, V2 {S.V2_sev_all.median():.2f} (extreme under V2: {S.V2_ext_all.median():.2f})"]
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "fairness_by_days.txt"), "w") as fh:
        fh.write(txt + "\n")
    print(txt)
