"""Write the explicit list of "data suspect" cells, version 1.

Only regions where stations show the AgERA5 change to be wrong are listed.
The general step screen is not accepted, so nothing is listed automatically.

Region rules (project choices, 2026-11-21)
  JP-N-COAST-2007  northern Japan coast, step up in mid 2007.
      Cells: flagged in coastal_2007_v0 (change across 2007 of 0.5 K or more
      beyond the regional interior, and 3 times the cell's placebo noise),
      with a positive change, inside 36.5-45.6 N, 138-146 E.
      Evidence: 9 coastal ISD-Lite stations, 02_tsugaru_check.py.
  TP-E-2020        eastern Tibetan Plateau, step up in 2020.
  HM-BT-SK-2020    Bhutan-Sikkim Himalaya, step up in 2020.
      Cells for both: inside the box, EITHER flagged by step_screen_v0 with a
      break in 2019 to 2021, OR normal-confidence cells with a third or more of
      2021-2025 days above the approximate 90th percentile (the patch as first
      found). Evidence: 4 and 2 ISD-Lite stations, confidence_map/02_patch_check.py.

Not listed, on purpose: Arctic coasts flagged for 2007 (no station evidence;
real sea ice loss cannot be ruled out), polar cells flagged by the step
screen, the 30 smaller unchecked patches, and inland patches of unknown cause.

Run:  bash tools/py.sh validation/step_screen/04_suspect_list.py
Output: config/data_suspect/cells_v1.csv, regions_v1.csv
"""
import os

import numpy as np
import pandas as pd

SS = "E:/temp/agera5/derived-products/heat-explorer/step-screen"
CONF = "E:/temp/agera5/derived-products/heat-explorer/confidence/confidence_v0.npz"
HERE = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(HERE, "..", "..", "config", "data_suspect")

REGIONS = [
    ("JP-N-COAST-2007", "Northern Japan coast", (36.5, 45.6, 138.0, 146.0), 2007, "up",
     "9 coastal stations step 0.65 to 1.70 K against AgERA5 in Jun-Oct 2007; inland stations do not",
     "validation/step_screen/02_tsugaru_check.py; 03_coastal_2007.py"),
    ("TP-E-2020", "Eastern Tibetan Plateau", (31.0, 37.0, 94.0, 102.0), 2020, "up",
     "4 stations near the patch show +0.7 to +1.0 K for 2021-2025 where AgERA5 shows +1.9 to +2.3 K; gap opens in 2020",
     "validation/confidence_map/02_patch_check.py; validation/step_screen/01_step_screen.py"),
    ("HM-BT-SK-2020", "Bhutan-Sikkim Himalaya", (26.0, 30.0, 86.5, 91.5), 2020, "up",
     "2 stations show +0.8 and +0.9 K where AgERA5 shows +1.7 and +2.2 K; gap opens in 2020. Thin evidence",
     "validation/confidence_map/02_patch_check.py; validation/step_screen/01_step_screen.py"),
]

if __name__ == "__main__":
    os.makedirs(DST, exist_ok=True)
    c7 = np.load(f"{SS}/coastal_2007_v0.npz")
    s0 = np.load(f"{SS}/step_screen_v0.npz")
    cf = np.load(CONF)
    lat = 90 - 0.1 * np.arange(1801)
    lon = -180 + 0.1 * np.arange(3600)
    cells, regs = [], []
    for rid, name, (a0, a1, o0, o1), year, sign, evidence, scripts in REGIONS:
        box = (lat[:, None] >= a0) & (lat[:, None] <= a1) & (lon[None, :] >= o0) & (lon[None, :] <= o1)
        if year == 2007:
            m = box & c7["flag"] & (c7["E2007"] > 0)
            size = c7["E2007"]
        else:
            m = box & ((s0["suspect"] & (s0["break_year"] >= 2019) & (s0["break_year"] <= 2021))
                       | ((cf["sd"] >= 1.5) & (cf["exc_recent"] >= 0.33)))
            size = s0["step"]
        ii, jj = np.nonzero(m)
        for i, j in zip(ii, jj):
            cells.append({"row": int(i), "col": int(j), "lat": round(float(lat[i]), 1), "lon": round(float(lon[j]), 1),
                          "region_id": rid, "change_K": round(float(size[i, j]), 2)})
        regs.append({"region_id": rid, "name": name, "lat_min": a0, "lat_max": a1, "lon_min": o0, "lon_max": o1,
                     "break_year": year, "direction": sign, "cells": int(m.sum()),
                     "median_change_K": round(float(np.nanmedian(size[m])), 2),
                     "affects": "all data from the break year onward, relative to earlier years",
                     "evidence": evidence, "scripts": scripts, "listed": "2026-11-21"})
    pd.DataFrame(cells).to_csv(f"{DST}/cells_v1.csv", index=False, lineterminator="\n")
    r = pd.DataFrame(regs)
    r.to_csv(f"{DST}/regions_v1.csv", index=False, lineterminator="\n")
    print(r[["region_id", "name", "break_year", "cells", "median_change_K"]].to_string(index=False))
    print("total cells", len(cells), "; row and col index the AgERA5 grid (row 0 = 90 N, col 0 = 180 W)")
