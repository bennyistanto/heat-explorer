# Lower bound on admin units that cannot own a 0.1 degree cell centre, from bounding boxes only (no geometry read).
import pyarrow.parquet as pq, numpy as np
for lvl in ("adm1","adm2"):
    f = pq.ParquetFile(rf"E:\temp\boundaries\{lvl}_polygons.parquet")
    t = f.read(columns=["geometry_bbox", "iso_3"]).to_pandas()
    b = t["geometry_bbox"].apply(lambda d: (d["xmin"], d["ymin"], d["xmax"], d["ymax"]))
    b = np.array(b.tolist(), dtype=float)
    nx = np.floor(b[:,2]/0.1+1e-9) - np.ceil(b[:,0]/0.1-1e-9) + 1
    ny = np.floor(b[:,3]/0.1+1e-9) - np.ceil(b[:,1]/0.1-1e-9) + 1
    ncent = np.clip(nx,0,None)*np.clip(ny,0,None)   # cell centres inside the bbox: upper bound on cells owned
    lat = (b[:,1]+b[:,3])/2
    area = (b[:,2]-b[:,0])*(b[:,3]-b[:,1])*111.32**2*np.cos(np.deg2rad(lat))  # bbox area km2, upper bound on unit area
    n = len(b)
    print(lvl, "units", n)
    print("  bbox holds 0 cell centres (certainly owns no cell): %d (%.1f%%)" % ((ncent==0).sum(), 100*(ncent==0).mean()))
    for k in (1, 4, 10, 30):
        print("  bbox holds <= %d centres (upper bound on cells): %d (%.1f%%)" % (k, (ncent<=k).sum(), 100*(ncent<=k).mean()))
    print("  bbox area km2 percentiles 5/25/50/75/95/max:", np.round(np.percentile(area,[5,25,50,75,95,100]),0))
    print("  bbox holds > 10000 centres:", (ncent>10000).sum(), "| > 100000:", (ncent>100000).sum())
    z = t["iso_3"][ncent==0].value_counts().head(8)
    print("  top countries with zero-centre units:", dict(z))
