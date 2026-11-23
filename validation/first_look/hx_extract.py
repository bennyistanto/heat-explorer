# Extract 11x11 cell windows around sites from AgERA5 yearly files (read-only).
import numpy as np, netCDF4 as nc, sys, time
from multiprocessing import Pool
SITES = {  # name: (lat, lon, approx elevation m - assumed, not from the DEM)
 "Singapore":(1.35,103.8,15),"Jakarta":(-6.2,106.8,10),"Lagos":(6.6,3.4,20),"Manaus":(-3.1,-60.0,60),
 "Delhi":(28.6,77.2,215),"Jacobabad":(28.3,68.4,55),"Hyderabad_IN":(17.4,78.5,540),"Dhahran":(26.3,50.1,20),
 "Phoenix":(33.4,-112.1,340),"Paris":(48.9,2.3,60),"Moscow":(55.8,37.6,150),"Portland_OR":(45.5,-122.6,30),
 "Sydney_W":(-33.8,150.9,40),"Nairobi":(-1.3,36.8,1700),"LaPaz":(-16.5,-68.2,3800),
 "Verkhoyansk":(67.5,133.4,140),"DomeC":(-75.1,123.3,3230)}
VARS = {"t2mmax":"Temperature_Air_2m_Max_24h","t2mmin":"Temperature_Air_2m_Min_24h","t2mmean":"Temperature_Air_2m_Mean_24h",
        "t2mdp":"Dew_Point_Temperature_2m_Mean_24h","rh2mmax":"Derived_Relative_Humidity_2m_Max_24h","rh2mmin":"Derived_Relative_Humidity_2m_Min_24h"}
H = 5
def job(a):
    v, y = a
    d = nc.Dataset(rf"E:\temp\agera5\{v}\agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[VARS[v]]
    t = d.variables["time"][:]
    out = {}
    for s,(la,lo,_) in SITES.items():
        i = int(round((90-la)/0.1)); j = int(round((lo+180)/0.1))
        out[s] = np.asarray(x[:, i-H:i+H+1, j-H:j+H+1], dtype=np.float32)
    d.close()
    return v, y, np.asarray(t), out
if __name__ == "__main__":
    t0 = time.time()
    jobs = [(v,y) for v in VARS for y in range(1979,2027)]
    with Pool(40) as p:
        res = p.map(job, jobs, chunksize=1)
    times = None; data = {}
    for v in VARS:
        rs = sorted([r for r in res if r[0]==v], key=lambda r:r[1])
        tt = np.concatenate([r[2] for r in rs])
        if times is None: times = tt
        assert np.array_equal(tt, times), v
        for s in SITES:
            data[f"{v}__{s}"] = np.concatenate([r[3][s] for r in rs], axis=0)
    np.savez_compressed("hx_cells.npz", time=times, **data)
    print("done", time.time()-t0, "s", len(times), "days")
