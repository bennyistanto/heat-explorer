import netCDF4 as nc, numpy as np
ref = {}
for v in ["t2mmax","t2mmin","t2mmean","t2mdp","rh2mmax","rh2mmin"]:
    for y in range(1979, 2027):
        d = nc.Dataset(rf"E:\temp\agera5\{v}\agera5_{v}_{y}.nc"); t = np.asarray(d.variables["time"][:]); u = d.variables["time"].units; d.close()
        if v == "t2mmax": ref[y] = t
        elif not np.array_equal(t, ref[y]):
            df = np.setdiff1d(ref[y], t); ex = np.setdiff1d(t, ref[y])
            print(v, y, "n", len(t), "vs", len(ref[y]), "units", u, "missing", df[:10], "extra", ex[:10], "sorted", bool(np.all(np.diff(t)>0)), "first", t[:3], ref[y][:3])
print("checked")
