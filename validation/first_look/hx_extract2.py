# Extract 11x11 cell windows around sites from AgERA5 yearly files (read-only). Saves one part per file, then merges.
import numpy as np, netCDF4 as nc, time, os
from multiprocessing import Pool
from hx_extract import SITES, VARS, H
def job(a):
    v, y = a
    out = f"hx_parts/{v}_{y}.npz"
    if os.path.exists(out): return
    d = nc.Dataset(rf"E:\temp\agera5\{v}\agera5_{v}_{y}.nc"); d.set_auto_mask(False)
    x = d.variables[VARS[v]]; t = np.asarray(d.variables["time"][:])
    # one hyperslab per site, sorted so sites sharing a chunk are read back to back
    r = {s: np.asarray(x[:, int(round((90-la)/0.1))-H:int(round((90-la)/0.1))+H+1, int(round((lo+180)/0.1))-H:int(round((lo+180)/0.1))+H+1], dtype=np.float32) for s,(la,lo,_) in SITES.items()}
    d.close()
    np.savez(out + ".tmp.npz", time=t, **r); os.replace(out + ".tmp.npz", out)
if __name__ == "__main__":
    t0 = time.time()
    jobs = [(v,y) for y in range(1979,2027) for v in VARS]
    with Pool(48) as p: p.map(job, jobs, chunksize=1)
    T = {v: np.concatenate([np.load(f"hx_parts/{v}_{y}.npz")["time"] for y in range(1979,2027)]) for v in VARS}
    common = T["t2mmax"]
    for v in VARS: common = np.intersect1d(common, T[v])
    data = {}
    for v in VARS:
        keep = np.isin(T[v], common)
        parts = [np.load(f"hx_parts/{v}_{y}.npz") for y in range(1979,2027)]
        for s in SITES: data[f"{v}__{s}"] = np.concatenate([p[s] for p in parts], axis=0)[keep]
    np.savez_compressed("hx_cells.npz", time=common, **data)
    print("done", time.time()-t0, "s", len(common), "days")
