"""Does the fast detector equal the frozen reference, day for day?

The frozen definition (docs/detector-v1-frozen.md) says a faster
implementation must reproduce the reference code's flag, spell and cls_day
exactly. This script checks pipeline/detector.py against
validation/detector_v3/detector.py on every land cell of the 17 test windows
(17 climates from the equator to Antarctica, 11 x 11 cells each, 1979 to
2026): up to 2,057 cells and about 36 million cell-days.

Pass, written before the first run: flag, spell and cls_day identical on every
day at every cell. One differing cell-day is a failure. `excess` is not frozen;
it is compared too and reported, with a tolerance of 1e-5.

Run:  bash tools/py.sh -W ignore validation/detector_v3/03_fast_equals_reference.py
Output: validation/detector_v3/results/fast_equals_reference.txt
"""
import importlib.util
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
CELLS = "E:/temp/agera5/derived-products/heat-explorer/critique-2026-11-20/hx_cells.npz"
_D = {}


def init(days):
    spec = importlib.util.spec_from_file_location("det3", os.path.join(HERE, "detector.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _D["det"] = m
    _D["idx"] = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))


def ref_job(a):
    k, tm = a
    r = _D["det"].detect(tm.astype("f8"), _D["idx"])
    return k, r["flag"], r["spell"], r["cls_day"].astype("u1"), (r["excess"] * r["spell"]).astype("f4")


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    from pipeline import detector as fast
    z = np.load(CELLS)
    days = z["time"]
    sites = sorted(k.split("__")[1] for k in z.files if k.startswith("t2mmax__"))
    cols, names = [], []
    for s in sites:
        tx, tn = z[f"t2mmax__{s}"].astype("f4"), z[f"t2mmin__{s}"].astype("f4")
        land = (tx[0] != -9999.0).ravel()
        tx, tn = tx.reshape(len(days), -1)[:, land] - 273.15, tn.reshape(len(days), -1)[:, land] - 273.15
        tm = np.full_like(tx, np.nan)
        tm[:-1] = (tx[:-1] + tn[1:]) / 2
        cols.append(tm)
        names += [s] * tm.shape[1]
    tm = np.concatenate(cols, axis=1)
    names = np.array(names)
    n = tm.shape[1]
    t0 = time.time()
    f = fast.detect_block(tm, days)
    t_fast = time.time() - t0
    t0 = time.time()
    ref = {k: np.zeros((len(days), n), dt) for k, dt in (("flag", bool), ("spell", bool), ("cls_day", "u1"), ("excess", "f4"))}
    with Pool(48, initializer=init, initargs=(days,)) as p:
        for k, a, b, c, d in p.imap_unordered(ref_job, ((k, tm[:, k]) for k in range(n)), chunksize=4):
            ref["flag"][:, k], ref["spell"][:, k], ref["cls_day"][:, k], ref["excess"][:, k] = a, b, c, d
    t_ref = time.time() - t0
    okc = f["ok"]
    out = ["Fast detector against the frozen reference. Produced by validation/detector_v3/03_fast_equals_reference.py",
           f"pipeline/detector.py version {fast.VERSION}; {len(sites)} windows, {n} land cells, {len(days)} days, {n * len(days):,} cell-days.",
           f"Cells the fast code declined (missing values inside the baseline): {int((~okc).sum())}"]
    allok = True
    for k in ("flag", "spell", "cls_day"):
        diff = (f[k][:, okc] != ref[k][:, okc])
        nd = int(diff.sum())
        allok &= nd == 0
        bad = sorted(set(names[okc][diff.any(axis=0)])) if nd else []
        out.append(f"  {k:8s} differing cell-days: {nd:,}" + (f"  in cells of: {bad}" if bad else ""))
    de = np.abs(f["excess"][:, okc] - ref["excess"][:, okc])
    out.append(f"  excess   (not frozen) largest absolute difference: {float(de.max()):.2e}; cell-days over 1e-5: {int((de > 1e-5).sum()):,}")
    live = ref["flag"].copy()
    live[2:] &= ref["flag"][1:-1] & ref["flag"][:-2]
    live[:2] = False
    out.append(f"  live     differing cell-days against the rule applied to the reference flag: {int((f['live'][:, okc] != live[:, okc]).sum()):,}")
    out.append(f"Totals in the reference: flagged {int(ref['flag'].sum()):,}, spell {int(ref['spell'].sum()):,}, severe or extreme {int((ref['cls_day'] >= 2).sum()):,}, extreme {int((ref['cls_day'] == 3).sum()):,} cell-days.")
    out.append(f"Time: fast {t_fast:.1f} s in one process ({t_fast / n * 1000:.1f} ms per cell); reference {t_ref:.0f} s on 48 processes ({t_ref * 48 / n:.1f} core-seconds per cell).")
    out.append(f"RESULT: {'IDENTICAL on flag, spell and cls_day' if allok else 'NOT IDENTICAL: the fast code may not be used'}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "fast_equals_reference.txt"), "w") as fh:
        fh.write(txt + "\n")
    print(txt)
