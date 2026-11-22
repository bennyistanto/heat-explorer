"""Daily share of each admin unit's area in a heat spell, severe, and extreme.

Frozen rules (docs/detector-v1-frozen.md, sections 6 and 7): live labelling (a
day counts when it and the two days before it are spell days); a cell belongs
to the unit containing its centre; cells are weighted by the cosine of
latitude. The share is over the unit's land cells that are in the store.

Reads the heat-state store by tile, and the lookup from pipeline/admin_lookup.py.
Writes E:/temp/agera5/derived-products/heat-explorer/v1/admin/series.zarr:

    {adm0,adm1,adm2}_{spell,severe,extreme}   uint16 (time, unit), share x 10000;
                                              65535 where the unit has no land cell, and on the
                                              last days of the record, which cannot be classed yet
    {adm0,adm1,adm2}_degdays                  uint16 (time, unit), K x 1000; 65535 no land cell
    time   int32 days since 1900-01-01

"degdays" is the event-size ingredient (a setting, not part of frozen version
1.0): the number of degrees by which a cell in a heat spell (live labelling)
is above its heat threshold, averaged over the unit's whole area, cells not in
a spell counting as zero. Summed over the days of an event it gives the
event's size in degree-days. It is read from the store as excess (in units of
local spread, float16) times that spread, so the threshold is whichever of the
two flag thresholds the day exceeds by more.

"spell" is any class (1 to 3), "severe" is severe or extreme (2 to 3),
"extreme" is class 3, each under live labelling. Unit order is the row order
of units_adm*.csv in the same folder.

Run:  bash tools/py.sh -W ignore pipeline/admin_series.py
"""
import os
import shutil
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
import zarr
from scipy import sparse

V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
NLAT, NLON, TR, TC = 1801, 3600, 200, 400
LEVELS, MEAS = ("adm0", "adm1", "adm2"), ("spell", "severe", "extreme")
TSTEP = 2048
_G = {}


def init():
    z0 = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")
    _G["c"], _G["x"], _G["a"] = z0["cls_day"], z0["excess"], z0["allyear"]
    z = np.load(f"{V1}/admin/lookup.npz")
    _G["lk"] = {k: z[k] for k in LEVELS}


def tile_job(a):
    r0, c0 = a
    r1, c1 = min(r0 + TR, NLAT), min(c0 + TC, NLON)
    lk = {k: _G["lk"][k][r0:r1, c0:c1] for k in LEVELS}
    use = lk["adm1"] >= 0
    for k in LEVELS:
        use |= lk[k] >= 0
    if not use.any():
        return None
    x = _G["c"][:, r0:r1, c0:c1][:, use]                       # (time, n) uint8
    valid = x[0] <= 3
    x = x[:, valid]
    n = x.shape[1]
    if n == 0:
        return None
    lat = np.repeat((90 - 0.1 * np.arange(r0, r1))[:, None], c1 - c0, axis=1)[use][valid]
    w = np.cos(np.deg2rad(lat)).astype("f8")
    sp = (x >= 1) & (x <= 3)
    live = sp.copy()
    live[2:] &= sp[1:-1] & sp[:-2]
    live[:2] = False
    exc = _G["x"][:, r0:r1, c0:c1][:, use][:, valid]            # float16, units of local spread
    iqr = np.nan_to_num(_G["a"][2, r0:r1, c0:c1][use][valid]).astype("f4")
    res = {}
    for k in LEVELS:
        u = lk[k][use][valid]
        has = u >= 0
        ids, inv = np.unique(u[has], return_inverse=True)
        m = sparse.csr_matrix((w[has], (np.where(has)[0], inv)), shape=(n, len(ids)))
        num = np.zeros((4, x.shape[0], len(ids)), "f4")
        for t0 in range(0, x.shape[0], TSTEP):
            sl = slice(t0, t0 + TSTEP)
            for q, lev in enumerate((1, 2, 3)):
                num[q, sl] = (m.T @ (live[sl] & (x[sl] >= lev)).astype("f4").T).T
            num[3, sl] = (m.T @ (np.nan_to_num(exc[sl].astype("f4")) * live[sl] * iqr[None, :]).T).T
        res[k] = (ids, num, np.asarray(m.sum(axis=0)).ravel())
    return res


if __name__ == "__main__":
    t0 = time.time()
    days = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")["time"][:]
    nt = len(days)
    nu = {k: len(pd.read_csv(f"{V1}/admin/units_{k}.csv", usecols=[0])) for k in LEVELS}
    num = {k: np.zeros((4, nt, nu[k]), "f4") for k in LEVELS}
    den = {k: np.zeros(nu[k], "f8") for k in LEVELS}
    tiles = [(r, c) for r in range(0, NLAT, TR) for c in range(0, NLON, TC)]
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 10, initializer=init) as p:
        for i, res in enumerate(p.imap_unordered(tile_job, tiles)):
            if res is not None:
                for k in LEVELS:
                    ids, nm, dn = res[k]
                    num[k][:, :, ids] += nm
                    den[k][ids] += dn
            print(f"tile {i + 1}/{len(tiles)} elapsed {time.time() - t0:.0f} s", flush=True)
    out = f"{V1}/admin/series.zarr"
    if os.path.exists(out):
        shutil.rmtree(out)
    g = zarr.open_group(out, mode="w")
    comp = zarr.codecs.BloscCodec(cname="zstd", clevel=3, shuffle=zarr.codecs.BloscShuffle.shuffle)
    g.create_array("time", shape=days.shape, chunks=days.shape, dtype="i4")[:] = days.astype("i4")
    for k in LEVELS:
        ok = den[k] > 0
        for q, m in enumerate(MEAS):
            with np.errstate(invalid="ignore", divide="ignore"):
                s = np.where(ok[None, :], np.clip(np.rint(num[k][q] / den[k][None, :] * 10000), 0, 10000), 65535).astype("u2")
            a = g.create_array(f"{k}_{m}", shape=s.shape, chunks=(nt, min(256, s.shape[1])), dtype="u2", fill_value=65535, compressors=comp)
            a[:] = s
        with np.errstate(invalid="ignore", divide="ignore"):
            s = np.where(ok[None, :], np.clip(np.rint(num[k][3] / den[k][None, :] * 1000), 0, 65534), 65535).astype("u2")
        a = g.create_array(f"{k}_degdays", shape=s.shape, chunks=(nt, min(256, s.shape[1])), dtype="u2", fill_value=65535, compressors=comp)
        a[:] = s
    tail = int(dict(zarr.open_group(f"{V1}/heat_state.zarr", mode="r").attrs).get("unclassed_tail_days", 0))
    if tail:                                                   # the store has no class for its last days: no share either
        for name in [k for k in g.array_keys() if k != "time"]:
            g[name][-tail:] = 65535
    g.attrs.update({"unclassed_tail_days": tail, "degdays": "K x 1000: degrees above the heat threshold over live spell cells, mean over the unit's area; not part of frozen version 1.0","detector_version": "1.0", "scale": "share of area x 10000; 65535 no land cell", "labelling": "live: the day and the two days before it are spell days",
                    "weights": "cosine of latitude", "units": "row order of units_adm0.csv, units_adm1.csv, units_adm2.csv"})
    print(f"DONE {time.time() - t0:.0f} s -> {out}; units with land: " + ", ".join(f"{k} {int((den[k] > 0).sum())}" for k in LEVELS), flush=True)
