import h5py, numpy as np, os
SITES = {"Singapore":(1.35,103.8),"Jakarta":(-6.2,106.8),"Lagos":(6.6,3.4),"Manaus":(-3.1,-60.0),"Delhi":(28.6,77.2),"Jacobabad":(28.3,68.4),"Hyderabad_IN":(17.4,78.5),"Dhahran":(26.3,50.1),"Phoenix":(33.4,-112.1),"Paris":(48.9,2.3),"Moscow":(55.8,37.6),"Portland_OR":(45.5,-122.6),"Sydney_W":(-33.8,150.9),"Nairobi":(-1.3,36.8),"LaPaz":(-16.5,-68.2),"Verkhoyansk":(67.5,133.4),"DomeC":(-75.1,123.3)}
fn = r"E:\temp\agera5\t2mmax\agera5_t2mmax_2003.nc"
f = h5py.File(fn, "r"); d = f["Temperature_Air_2m_Max_24h"]
need = set()
for s,(la,lo) in SITES.items():
    i = int(round((90-la)/0.1)); j = int(round((lo+180)/0.1))
    for a in {(i-5)//200, (i+5)//200}:
        for b in {(j-5)//400, (j+5)//400}:
            need.add((a,b))
tot = 0; n = 0
for (a,b) in need:
    for t in range(0, 365, 31):
        tot += d.id.get_chunk_info_by_coord((t, a*200, b*400)).size; n += 1
print("spatial chunks", len(need), "chunk reads", n, "bytes GB", tot/1e9, "file GB", os.path.getsize(fn)/1e9)
