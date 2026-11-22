"""Mark the days at the end of the record that cannot be classed yet.

The centred 3-day mean of day d needs the minimum of day d+2, so the detector
has no value for the last two days of the record. pipeline/run_global.py used
to leave them as 0 ("not in a heat spell"), which reads as a statement about
the weather. This script changes them in place:

    heat_state.zarr   cls_day on the last two days: 0 to 3 become 253 ("not yet classed")
    admin/series.zarr every share and degree-day value on the last two days becomes 65535

Safe to run again: it only touches those two days. run_global.py and
admin_series.py now write these codes themselves, so this is needed only for a
store made before 2026-11-22.

Run:  bash tools/py.sh -W ignore pipeline/mark_unclassed.py
"""
import os

import numpy as np
import zarr

V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
TAIL = 2

if __name__ == "__main__":
    g = zarr.open_group(f"{V1}/heat_state.zarr", mode="r+")
    c = g["cls_day"]
    x = c[-TAIL:]
    before = {int(v): int((x == v).sum()) for v in np.unique(x)}
    x[x <= 3] = 253
    c[-TAIL:] = x
    g.attrs.update({"unclassed_tail_days": TAIL, "cls_day_codes": "0 none, 1 heat spell, 2 severe, 3 extreme, 253 not yet classed (the last days of the record), 254 declined, 255 no data"})
    after = {int(v): int(n) for v, n in zip(*np.unique(c[-TAIL:], return_counts=True))}
    print("heat_state.zarr last", TAIL, "days: before", before, "after", after)
    p = f"{V1}/admin/series.zarr"
    if os.path.exists(p):
        a = zarr.open_group(p, mode="r+")
        names = [k for k in a.array_keys() if k != "time"]
        for k in names:
            a[k][-TAIL:] = 65535
        a.attrs.update({"unclassed_tail_days": TAIL})
        print("series.zarr: last", TAIL, "days set to 65535 in", len(names), "arrays")
