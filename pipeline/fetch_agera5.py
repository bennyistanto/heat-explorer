"""Fetch new AgERA5 days from the Copernicus Climate Data Store and write them
beside the yearly files, without touching the yearly files.

The yearly files in E:/temp/agera5/<var>/agera5_<var>_<year>.nc are raw input
and are never changed. Days after the last day they hold are downloaded and
merged into one supplement file per variable:

    E:/temp/agera5/derived-products/heat-explorer/raw_update/<var>/agera5_<var>_<first>_<last>.nc

with the same variable name, grid, time units and fill value as the yearly
files. pipeline/rawfiles.py lists the yearly files followed by the
supplements, and every pass reads through it.

Needs the cdsapi package and a CDS key in ~/.cdsapirc, with the dataset licence
accepted on the CDS website.

Run:  bash tools/py.sh pipeline/fetch_agera5.py 2026-10-31
"""
import glob
import os
import sys
import zipfile

import netCDF4 as nc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pipeline import rawfiles  # noqa: E402

REQ = {"t2mmax": ("2m_temperature", "24_hour_maximum"), "t2mmin": ("2m_temperature", "24_hour_minimum"), "t2mdp": ("2m_dewpoint_temperature", "24_hour_mean")}
EPOCH = pd.Timestamp("1900-01-01")


def main(until):
    import cdsapi
    until = pd.Timestamp(until)
    client = cdsapi.Client()
    for v, (variable, stat) in REQ.items():
        last = EPOCH + pd.Timedelta(days=int(rawfiles.time_axis(v)[-1]))
        want = pd.date_range(last + pd.Timedelta(days=1), until)
        if not len(want):
            print(v, "already holds", until.date())
            continue
        work = f"{rawfiles.UPD}/_download/{v}"
        os.makedirs(work, exist_ok=True)
        for (y, m), days in want.to_series().groupby([want.year, want.month]):
            z = f"{work}/{v}_{y}{m:02d}_{days.iloc[0].day:02d}_{days.iloc[-1].day:02d}.zip"
            if not os.path.exists(z):
                print("requesting", v, y, m, f"{len(days)} days", flush=True)
                client.retrieve("sis-agrometeorological-indicators", {"variable": variable, "statistic": [stat], "year": [str(y)], "month": [f"{m:02d}"],
                                                                      "day": [f"{d.day:02d}" for d in days], "version": "2_0"}, z + ".part")
                os.replace(z + ".part", z)
            with zipfile.ZipFile(z) as f:
                f.extractall(work)
        merge(v, work, want)


def merge(v, work, want):
    name = rawfiles.VARS[v]
    got = {}
    for p in glob.glob(f"{work}/*.nc"):
        d = nc.Dataset(p)
        t = nc.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False, only_use_python_datetimes=True)
        if len(t) == 1 and name in d.variables:
            got[pd.Timestamp(t[0]).normalize()] = p
        d.close()
    have = [q for q in want if q in got]
    if not have:
        raise SystemExit(f"{v}: no daily file was delivered")
    if have != list(want[:len(have)]):
        raise SystemExit(f"{v}: days are missing inside the run: {sorted(set(want[:len(have)]) - set(have))[:5]}")
    if len(have) < len(want):
        print(f"{v}: the store has days only to {have[-1].date()}; asked to {want[-1].date()}")
    out_dir = f"{rawfiles.UPD}/{v}"
    os.makedirs(out_dir, exist_ok=True)
    out = f"{out_dir}/agera5_{v}_{have[0]:%Y%m%d}_{have[-1]:%Y%m%d}.nc"
    ref = nc.Dataset(rawfiles.yearly(v)[-1])
    o = nc.Dataset(out + ".part", "w", format="NETCDF4")
    o.createDimension("time", None)
    o.createDimension("lat", ref.dimensions["lat"].size)
    o.createDimension("lon", ref.dimensions["lon"].size)
    for k in ("lat", "lon"):
        x = o.createVariable(k, ref[k].dtype, (k,))
        x.setncatts({a: ref[k].getncattr(a) for a in ref[k].ncattrs() if a != "_FillValue"})
        x[:] = ref[k][:]
    tv = o.createVariable("time", "i8", ("time",))
    tv.units, tv.calendar = ref["time"].units, "proleptic_gregorian"
    x = o.createVariable(name, "f4", ("time", "lat", "lon"), zlib=True, complevel=4, shuffle=True, chunksizes=(min(31, len(have)), 200, 400), fill_value=-9999.0)
    x.setncatts({a: ref[name].getncattr(a) for a in ref[name].ncattrs() if a not in ("_FillValue", "grid_mapping")})
    lat0 = np.asarray(ref["lat"][:])
    for i, day in enumerate(have):
        d = nc.Dataset(got[day])
        d.set_auto_mask(False)
        a = np.asarray(d[name][0], "f4")
        la = np.asarray(d["lat"][:])
        if not np.allclose(la, lat0):
            if np.allclose(la[::-1], lat0):
                a = a[::-1]
            else:
                raise SystemExit(f"{v} {day.date()}: grid differs from the yearly files")
        fv = getattr(d[name], "_FillValue", None)
        if fv is not None and fv != -9999.0:
            a = np.where(a == fv, np.float32(-9999.0), a)
        a = np.where(np.isfinite(a), a, np.float32(-9999.0))
        x[i] = a
        tv[i] = (day - EPOCH).days
        d.close()
    o.source_note = f"{len(have)} daily AgERA5 files from the Climate Data Store, merged by pipeline/fetch_agera5.py. The yearly files were not changed."
    o.close()
    ref.close()
    os.replace(out + ".part", out)
    print("wrote", out, f"{os.path.getsize(out) / 1e6:.0f} MB", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
