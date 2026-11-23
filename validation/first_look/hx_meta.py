import netCDF4 as nc, numpy as np
for v in ["t2mmax","t2mmin","t2mmean","t2mdp","rh2mmax","rh2mmin"]:
    d = nc.Dataset(rf"E:\temp\agera5\{v}\agera5_{v}_2003.nc")
    for k,x in d.variables.items():
        if x.ndim==3:
            print(v,k,x.shape,x.chunking(),getattr(x,'units',''),getattr(x,'long_name',''))
    if v=="t2mmax":
        print(d.variables['lat'][:3], d.variables['lon'][:3], d.variables['time'][:2], d.variables['time'].units)
    d.close()
