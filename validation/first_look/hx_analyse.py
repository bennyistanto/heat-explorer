# Cell experiments for the heat-explorer design critique. Reads hx_cells.npz made by hx_extract.py.
import numpy as np, datetime as dt, warnings
from scipy.stats import kendalltau
from scipy.ndimage import uniform_filter1d
warnings.filterwarnings("ignore")
Z = np.load("hx_cells.npz")
time = Z["time"].astype(int)
dates = np.array([dt.date(1900,1,1)+dt.timedelta(days=int(t)) for t in time])
yr = np.array([d.year for d in dates]); mo = np.array([d.month for d in dates])
doy = np.array([min((d - dt.date(d.year,1,1)).days - (1 if (d.month>2 and d.year%4==0 and (d.year%100!=0 or d.year%400==0)) else 0), 364) for d in dates])
isleapday = np.array([d.month==2 and d.day==29 for d in dates])
base = (yr>=1991)&(yr<=2020)
SITES = {"Singapore":(1.35,103.8,15),"Jakarta":(-6.2,106.8,10),"Lagos":(6.6,3.4,20),"Manaus":(-3.1,-60.0,60),
 "Delhi":(28.6,77.2,215),"Jacobabad":(28.3,68.4,55),"Hyderabad_IN":(17.4,78.5,540),"Dhahran":(26.3,50.1,20),
 "Phoenix":(33.4,-112.1,340),"Paris":(48.9,2.3,60),"Moscow":(55.8,37.6,150),"Portland_OR":(45.5,-122.6,30),
 "Sydney_W":(-33.8,150.9,40),"Nairobi":(-1.3,36.8,1700),"LaPaz":(-16.5,-68.2,3800),
 "Verkhoyansk":(67.5,133.4,140),"DomeC":(-75.1,123.3,3230)}
def es(T):  # hPa, T in C (Magnus over water)
    return 6.112*np.exp(17.62*T/(243.12+T))
def stull(T, RH):
    return (T*np.arctan(0.151977*np.sqrt(RH+8.313659)) + np.arctan(T+RH) - np.arctan(RH-1.676331)
            + 0.00391838*RH**1.5*np.arctan(0.023101*RH) - 4.686035)
def tw_thermo(T, RH, p):  # isobaric (thermodynamic) wet-bulb by bisection, p in hPa
    e = RH/100*es(T); w = 0.622*e/(p-e)
    lo = T-60.0; hi = T.copy()
    for _ in range(40):
        m = (lo+hi)/2
        ws = 0.622*es(m)/(p-es(m)); Lv = 2.501e6-2361*m
        f = (1005+1850*w)*(T-m) - Lv*(ws-w)
        lo = np.where(f>0, m, lo); hi = np.where(f>0, hi, m)
    return (lo+hi)/2
def pstd(h): return 1013.25*(1-2.25577e-5*h)**5.25588
def ehf_calc(T):
    n = len(T); T3 = np.full(n, np.nan); T3[:n-2] = (T[:-2]+T[1:-1]+T[2:])/3
    c = np.concatenate([[0], np.cumsum(T)]); acc = np.full(n, np.nan); acc[30:] = (c[30:n]-c[0:n-30])/30
    T95 = np.percentile(T[base], 95)
    sig = T3 - T95; accl = T3 - acc
    ehf = sig*np.maximum(1, accl)
    pos = np.nan_to_num(ehf, nan=-1) > 0
    hw = pos.copy(); hw[1:] |= pos[:-1]; hw[2:] |= pos[:-2]
    e85 = np.percentile(ehf[base & pos], 85) if (base&pos).sum()>5 else np.nan
    return dict(T95=T95, ehf=ehf, pos=pos, hw=hw, accl=accl, sig=sig, e85=e85)
FULL = np.arange(1979, 2026)
def cc(a, b):
    a = a - a.mean(); b = b - b.mean(); return (a*b).sum()/np.sqrt((a*a).sum()*(b*b).sum())
def annual(flag): return np.array([flag[yr==y].sum() for y in FULL])
def lag1(x):
    t = np.arange(len(x)) - (len(x)-1)/2; x = x - x.mean() - t*(t*(x-x.mean())).sum()/(t*t).sum()
    return cc(x[:-1], x[1:])
def topmonths(flag):
    c = np.array([flag[mo==m].sum() for m in range(1,13)]); o = np.argsort(c)[::-1][:3]
    return " ".join(f"{m+1}:{100*c[m]/max(c.sum(),1):.0f}%" for m in o)
def doy_thr(x, q=90, half=7, years=None):
    sel = base & ~isleapday if years is None else years & ~isleapday
    thr = np.empty(365)
    d = doy[sel]; v = x[sel]
    for k in range(365):
        dist = np.abs(d-k); dist = np.minimum(dist, 365-dist)
        thr[k] = np.percentile(v[dist<=half], q)
    return thr
R = {}
print("=== centre-cell validity ===")
for s,(la,lo,h) in SITES.items():
    w = Z[f"t2mmax__{s}"]; ci, cj = 5, 5
    if w[0,5,5] < -9000:
        ok = np.argwhere(w[0] > -9000)
        if len(ok)==0: print(s, "NO VALID CELL"); continue
        k = np.argmin(((ok-5)**2).sum(1)); ci, cj = ok[k]
        print(s, "centre is fill; using offset", ci-5, cj-5)
    g = lambda v: Z[f"{v}__{s}"][:,ci,cj].astype(float)
    tx, tn, tm, td = g("t2mmax")-273.15, g("t2mmin")-273.15, g("t2mmean")-273.15, g("t2mdp")-273.15
    rhn, rhx = g("rh2mmin"), g("rh2mmax")
    R[s] = dict(tx=tx, tn=tn, tm=tm, td=td, rhn=rhn, rhx=rhx, ci=ci, cj=cj, h=h)
    bad = sum(((a<-200)|~np.isfinite(a)).sum() for a in (tx,tn,tm,td)) + ((rhn<0)|(rhx<0)).sum()
    if bad: print(s, "bad values:", bad)
print("\n=== A. RH fields vs dewpoint ===")
print(f"{"site":13s} {"MAD rhmin":>9s} {"MAD rhmax":>9s} {"rhmax>=99.5 %d":>15s} {"RH<5 %days":>10s} {"outside Stull %":>15s}")
for s,r in R.items():
    a = 100*es(r["td"])/es(r["tx"]); b = np.minimum(100*es(r["td"])/es(r["tn"]), 100)
    viol = ((r["rhn"]<5)|(r["tx"]<-20)|(r["tx"]>50)).mean()*100
    print(f"{s:13s} {np.abs(a-r["rhn"]).mean():9.2f} {np.abs(b-r["rhx"]).mean():9.2f} {100*(r["rhx"]>=99.5).mean():15.1f} {100*(r["rhn"]<5).mean():10.1f} {viol:15.1f}")
print("\n=== B. EHF on (Tmax+Tmin)/2, all-year T95, base 1991-2020. Heatwave days per year ===")
print(f"{"site":13s} {"T95":>6s} {"sdT":>5s} {"79-90":>6s} {"91-20":>6s} {"21-25":>6s} {"min":>4s} {"max":>4s} {"zeroYrs":>7s} {"accl>1%":>7s} {"EHF85":>6s} {"sev%":>5s} {"ext%":>5s} {"tau":>5s} {"p":>7s} {"r1":>5s}  top months")
for s,r in R.items():
    T = (r["tx"]+r["tn"])/2; E = ehf_calc(T); r["E"] = E; a = annual(E["hw"]); r["aE"] = a
    pos = E["pos"]; k = kendalltau(FULL, a)
    print(f"{s:13s} {E["T95"]:6.1f} {T[base].std():5.2f} {a[FULL<=1990].mean():6.1f} {a[(FULL>=1991)&(FULL<=2020)].mean():6.1f} {a[FULL>=2021].mean():6.1f} {a.min():4d} {a.max():4d} {(a==0).sum():7d} {100*(E["accl"][pos]>1).mean():7.0f} {E["e85"]:6.2f} {100*(E["ehf"][pos]>=E["e85"]).mean():5.1f} {100*(E["ehf"][pos]>=3*E["e85"]).mean():5.1f} {k[0]:5.2f} {k[1]:7.1e} {lag1(a):5.2f}  {topmonths(E["hw"])}")
print("\n=== B2. Sensitivity to T definition: heatwave days/yr 1991-2020, Jaccard overlap with default ===")
for s,r in R.items():
    d = r["E"]["hw"]
    E2 = ehf_calc(r["tm"]); Tn = (r["tx"]+np.append(r["tn"][1:], r["tn"][-1]))/2; E3 = ehf_calc(Tn)
    j = lambda x: (x&d).sum()/max((x|d).sum(),1)
    print(f"{s:13s} default {annual(d)[12:42].mean():5.1f} | t2mmean {annual(E2["hw"])[12:42].mean():5.1f} J={j(E2["hw"]):.2f} mean(tm-(tx+tn)/2)={np.mean(r["tm"]-(r["tx"]+r["tn"])/2):+.2f}K | Tmax+next Tmin {annual(E3["hw"])[12:42].mean():5.1f} J={j(E3["hw"]):.2f}")
print("\n=== C. EHHF on mean Stull wet-bulb ===")
print(f"{"site":13s} {"Tw95":>6s} {"sdTw":>5s} {"79-90":>6s} {"91-20":>6s} {"21-25":>6s} {"min":>4s} {"max":>4s} {"accl>1%":>7s} {"EHHF85":>6s} {"ext%":>5s} {"tau":>5s} {"P(EHF|EHHF)":>11s} {"P(EHHF|EHF)":>11s}  top months")
for s,r in R.items():
    twd = stull(r["tx"], r["rhn"]); twn = stull(r["tn"], r["rhx"]); r["twd"] = twd; r["twn"] = twn
    Tw = (twd+twn)/2; H = ehf_calc(Tw); r["H"] = H; a = annual(H["hw"]); r["aH"] = a; pos = H["pos"]
    e, hh = r["E"]["hw"], H["hw"]; k = kendalltau(FULL, a)
    print(f"{s:13s} {H["T95"]:6.1f} {Tw[base].std():5.2f} {a[FULL<=1990].mean():6.1f} {a[(FULL>=1991)&(FULL<=2020)].mean():6.1f} {a[FULL>=2021].mean():6.1f} {a.min():4d} {a.max():4d} {100*(H["accl"][pos]>1).mean():7.0f} {H["e85"]:6.2f} {100*(H["ehf"][pos]>=3*H["e85"]).mean():5.1f} {k[0]:5.2f} {100*(e&hh).sum()/max(hh.sum(),1):11.0f} {100*(e&hh).sum()/max(e.sum(),1):11.0f}  {topmonths(hh)}")
print("\n=== D. Tw_day = Stull(Tmax, rh2mmin): distribution, days/yr above cuts (1991-2020), error vs thermodynamic Tw ===")
print(f"{"site":13s} {"p50":>5s} {"p95":>5s} {"p99":>5s} {"max":>5s} {">=24":>6s} {">=26":>6s} {">=28":>6s} {">=30":>5s} {">=31":>5s} {"n>=35":>5s} | {"p_hPa":>6s} {"St-true@p mean":>14s} {"top1%":>6s} {"min":>6s} {"max":>6s} | {"St-true@1013 top1%":>18s} {">=26 true@p":>11s} {">=28 true@p":>11s}")
for s,r in R.items():
    tw = r["twd"]; p = pstd(r["h"]); nb = base.sum()/365.25
    rh = np.clip(r["rhn"],0.5,100)
    tt = tw_thermo(r["tx"], rh, p); t0 = tw_thermo(r["tx"], rh, 1013.25)
    d = tw-tt; top = tw >= np.percentile(tw, 99)
    f = lambda c: (tw[base]>=c).sum()/nb
    print(f"{s:13s} {np.percentile(tw,50):5.1f} {np.percentile(tw,95):5.1f} {np.percentile(tw,99):5.1f} {tw.max():5.1f} {f(24):6.1f} {f(26):6.1f} {f(28):6.1f} {f(30):5.1f} {f(31):5.2f} {(tw>=35).sum():5d} | {p:6.0f} {d.mean():14.2f} {d[top].mean():6.2f} {d.min():6.2f} {d.max():6.2f} | {(tw-t0)[top].mean():18.2f} {(tt[base]>=26).sum()/nb:11.1f} {(tt[base]>=28).sum()/nb:11.1f}")
print("\n=== E. TX90/TN90 calendar-day (15-day window, base 1991-2020): exceedance rates % ===")
print(f"{"site":13s} {"TXin":>5s} {"TXcv":>5s} {"TX79-90":>7s} {"TX21-26":>7s} {"TNin":>5s} {"TNcv":>5s} {"TN79-90":>7s} {"TN21-26":>7s} {"comp%":>6s} {"P(N|D)":>6s}")
for s,r in R.items():
    out = []
    for key in ("tx","tn"):
        x = r[key]; thr = doy_thr(x); fl = x > thr[doy]; r["f"+key] = fl
        cv = []
        for y in range(1991, 2021):
            t2 = doy_thr(x, years=base&(yr!=y)); cv.append((x[yr==y] > t2[doy[yr==y]]).mean())
        out += [100*fl[base].mean(), 100*np.mean(cv), 100*fl[yr<=1990].mean(), 100*fl[yr>=2021].mean()]
    c = r["ftx"]&r["ftn"]; r["comp"] = c
    cold = np.isin(mo,[12,1,2]) if SITES[s][0]>0 else np.isin(mo,[6,7,8])
    print(f"{s:13s} {out[0]:5.1f} {out[1]:5.1f} {out[2]:7.1f} {out[3]:7.1f} {out[4]:5.1f} {out[5]:5.1f} {out[6]:7.1f} {out[7]:7.1f} {100*c.mean():6.1f} {100*c.sum()/r["ftx"].sum():6.0f}  winter-quarter share of compound days: {100*(c&cold).sum()/max(c.sum(),1):.0f}%")
print("\n=== F. Documented events ===")
def event(s, d0, d1, label):
    r = R[s]; sel = (dates>=dt.date(*d0))&(dates<=dt.date(*d1)); E, H = r["E"], r["H"]
    pk = np.nanmax(E["ehf"][sel]); ymax = np.array([np.nanmax(E["ehf"][yr==y]) for y in range(1979,2027)])
    rank = 1+(ymax > pk).sum(); cls = "extreme" if pk>=3*E["e85"] else "severe" if pk>=E["e85"] else "low" if pk>0 else "NONE"
    hpk = np.nanmax(H["ehf"][sel]); hcls = "extreme" if hpk>=3*H["e85"] else "severe" if hpk>=H["e85"] else "low" if hpk>0 else "NONE"
    print(f"{label:24s} {s:12s} EHF peak {pk:7.1f} K2 = {pk/E["e85"]:5.1f} x EHF85 [{cls:7s}] rank {rank:2d}/48 | hw days {E["hw"][sel].sum():2d}/{sel.sum()} | TX90 {r["ftx"][sel].sum():2d} TN90 {r["ftn"][sel].sum():2d} comp {r["comp"][sel].sum():2d} | Tx max {r["tx"][sel].max():.1f} | Tw_day max {r["twd"][sel].max():.1f} | EHHF peak {hpk:6.1f} [{hcls}] days {H["hw"][sel].sum()}")
event("Paris",(2003,8,1),(2003,8,15),"Europe Aug 2003")
event("Moscow",(2010,7,10),(2010,8,20),"Russia Jul-Aug 2010")
event("Hyderabad_IN",(2015,5,18),(2015,6,3),"India May 2015")
event("Delhi",(2015,5,18),(2015,6,3),"India May 2015")
event("Jacobabad",(2015,6,15),(2015,6,28),"Pakistan Jun 2015")
event("Delhi",(2022,3,10),(2022,5,20),"India-Pak Mar-May 2022")
event("Jacobabad",(2022,3,10),(2022,5,20),"India-Pak Mar-May 2022")
event("Portland_OR",(2021,6,25),(2021,6,30),"Pacific NW Jun 2021")
event("Sydney_W",(2019,12,15),(2020,2,5),"SE Australia 2019-20")
event("Verkhoyansk",(2020,6,15),(2020,6,30),"Siberia Jun 2020")
print("\nTop 5 yearly EHF peaks per site; top Tw_day dates for humid sites:")
for s in ("Paris","Moscow","Portland_OR","Delhi","Jacobabad","Hyderabad_IN"):
    E = R[s]["E"]["ehf"]; o = []
    for y in range(1979,2027):
        i = np.where(yr==y)[0]; k = i[np.nanargmax(E[i])]; o.append((E[k], dates[k]))
    o.sort(reverse=True); print(f"  {s:12s}", ", ".join(f"{d} {v:.0f}" for v,d in o[:5]))
for s in ("Dhahran","Jacobabad","Delhi","Singapore","Lagos"):
    tw = R[s]["twd"]; o = np.argsort(tw)[::-1][:5]
    print(f"  Tw_day top: {s:10s}", ", ".join(f"{dates[k]} {tw[k]:.1f} (Tx {R[s]["tx"][k]:.0f}, RH {R[s]["rhn"][k]:.0f})" for k in o))
print("\n=== G. Spatial redundancy in the 11x11 window (centre vs cells at Chebyshev distance 1, 3, 5) ===")
print(f"{"site":13s} {"land%":>5s} {"r daily anom d1":>15s} {"d3":>5s} {"d5":>5s} | {"r annual hw d1":>14s} {"d3":>5s} {"d5":>5s} | {"T95 range K":>11s}")
for s,r in R.items():
    wx = Z[f"t2mmax__{s}"].astype(float); wn = Z[f"t2mmin__{s}"].astype(float)
    valid = wx[0] > -9000; W = (wx+wn)/2 - 273.15; ci, cj = r["ci"], r["cj"]
    clim = np.array([W[doy==k].mean(0) for k in range(365)]); An = W - uniform_filter1d(clim, 31, axis=0, mode="wrap")[doy]
    t95 = []; res = {1:[[],[]],3:[[],[]],5:[[],[]]}
    a0 = An[:,ci,cj]; h0 = r["aE"]
    for i in range(11):
        for j in range(11):
            if not valid[i,j]: continue
            dd = max(abs(i-ci), abs(j-cj))
            E = ehf_calc(W[:,i,j]); t95.append(E["T95"])
            if dd in res:
                res[dd][0].append(cc(a0, An[:,i,j])); res[dd][1].append(cc(h0, annual(E["hw"])))
    m = lambda d,k: np.mean(res[d][k]) if res[d][k] else np.nan
    print(f"{s:13s} {100*valid.mean():5.0f} {m(1,0):15.3f} {m(3,0):5.3f} {m(5,0):5.3f} | {m(1,1):14.3f} {m(3,1):5.3f} {m(5,1):5.3f} | {max(t95)-min(t95):11.1f}")
print("\n=== H. What a cube-wide Gi* reference sees ===")
allA = np.array([R[s]["aE"] for s in R])
print("mean over sites, EHF heatwave days/yr: 1979-1990 %.1f | 1991-2005 %.1f | 2006-2020 %.1f | 2021-2025 %.1f" % (allA[:,FULL<=1990].mean(), allA[:,(FULL>=1991)&(FULL<=2005)].mean(), allA[:,(FULL>=2006)&(FULL<=2020)].mean(), allA[:,FULL>=2021].mean()))
print("pooled sd over sites and years %.1f; between-site sd of 2021-25 means %.1f; of 1979-90 means %.1f" % (allA.std(), allA[:,FULL>=2021].mean(1).std(), allA[:,FULL<=1990].mean(1).std()))
for s,r in R.items():
    hw = r["E"]["hw"]; n = (len(hw)//7)*7; wk = hw[len(hw)-n:].reshape(-1,7).sum(1)
    a = r["aE"]; k = kendalltau(FULL, a)
    print(f"{s:13s} weekly zero share, all record {100*(wk==0).mean():5.1f}% | last 26 weeks: zero weeks {int((wk[-26:]==0).sum()):2d}/26, hw days {int(wk[-26:].sum()):3d} | annual MK p<0.05 {"yes" if k[1]<0.05 else "no "} sign {np.sign(k[0]):+.0f} | 2021-25 / 1979-90 ratio {a[FULL>=2021].mean()/max(a[FULL<=1990].mean(),0.1):5.1f}")
