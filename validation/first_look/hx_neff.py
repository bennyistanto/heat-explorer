# Effective number of independent cells in an 11x11 (about 1.1 degree) window, for annual EHF heatwave-day counts.
import numpy as np, datetime as dt
Z = np.load("hx_cells.npz"); time = Z["time"].astype(int)
yr = np.array([(dt.date(1900,1,1)+dt.timedelta(days=int(t))).year for t in time]); base = (yr>=1991)&(yr<=2020)
FULL = np.arange(1979, 2026)
def hwdays(T):
    n = len(T); T3 = np.full(n, -99.0); T3[:n-2] = (T[:-2]+T[1:-1]+T[2:])/3
    pos = T3 > np.percentile(T[base], 95); hw = pos.copy(); hw[1:] |= pos[:-1]; hw[2:] |= pos[:-2]
    return np.array([hw[yr==y].sum() for y in FULL])
print(f"{"site":13s} {"cells":>5s} {"sd single":>9s} {"sd window mean":>14s} {"n_eff":>6s} {"sd if independent":>17s} {"z inflation":>11s}")
for k in [f for f in Z.files if f.startswith("t2mmax__")]:
    s = k.split("__")[1]; wx = Z[k].astype(float); wn = Z["t2mmin__"+s].astype(float); ok = wx[0] > -9000
    A = np.array([hwdays((wx[:,i,j]+wn[:,i,j])/2) for i in range(11) for j in range(11) if ok[i,j]]).astype(float)
    t = FULL - FULL.mean()
    A = A - A.mean(1, keepdims=True); A = A - np.outer((A*t).sum(1)/(t*t).sum(), t)   # remove each cell's linear trend
    vs = A.var(1).mean(); vm = A.mean(0).var(); n = len(A)
    print(f"{s:13s} {n:5d} {np.sqrt(vs):9.2f} {np.sqrt(vm):14.2f} {vs/vm:6.2f} {np.sqrt(vs/n):17.2f} {np.sqrt(vm/(vs/n)):11.1f}")
