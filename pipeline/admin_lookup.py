"""Which admin unit does each AgERA5 cell belong to?

Frozen rule (docs/detector-v1-frozen.md, section 7): a cell belongs to the
unit that contains its centre. Each adm1 and adm2 polygon is rasterised on the
0.1 degree grid with that rule. Where two polygons both contain a centre, the
one that comes first in the boundary file keeps the cell; the number of such
cells is reported. Countries (adm0) are not rasterised: a cell's country is
the country of its adm1 unit.

Cells of the heat-state store that fall in no polygon get -1. They stay in the
map and are in no admin number.

Output, outside the repository, in E:/temp/agera5/derived-products/heat-explorer/v1/admin/:
    lookup.npz      adm1, adm2 (1801, 3600) int32 row index into the unit tables, -1 none;
                    adm0 (1801, 3600) int16 row index into units_adm0.csv
    units_adm1.csv, units_adm2.csv, units_adm0.csv   one row per unit: ids, names,
                    licence, land cells, area in km2 (sum of cell areas)

Run:  bash tools/py.sh -W ignore pipeline/admin_lookup.py
"""
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
import zarr
from rasterio import features
from rasterio.transform import from_origin

B = "E:/temp/boundaries"
V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"
NLAT, NLON = 1801, 3600
KEEP = {1: ["adm1_id", "adm1_name", "adm0_id", "adm0_name", "iso_3", "src_lic", "status_nm"],
        2: ["adm2_id", "adm2_name", "adm1_id", "adm1_name", "adm0_id", "adm0_name", "iso_3", "src_lic", "status_nm"]}


def job(a):
    lvl, g0, g1 = a
    f = pq.ParquetFile(f"{B}/adm{lvl}/adm{lvl}_polygons.parquet")   # folder layout since 2026-11-22
    out = []
    for g in range(g0, g1):
        t = f.read_row_group(g, columns=["geometry"])
        for k, wkb in enumerate(t.column("geometry").to_pylist()):
            if wkb is None:
                out.append(None)
                continue
            gm = shapely.from_wkb(wkb)
            if gm.is_empty:
                out.append(None)
                continue
            x0, y0, x1, y1 = gm.bounds
            i0, i1 = max(int(np.floor((90 - y1) / 0.1)), 0), min(int(np.ceil((90 - y0) / 0.1)), NLAT - 1)
            j0, j1 = max(int(np.floor((x0 + 180) / 0.1)), 0), min(int(np.ceil((x1 + 180) / 0.1)), NLON - 1)
            m = features.rasterize([(gm, 1)], out_shape=(i1 - i0 + 1, j1 - j0 + 1),
                                   transform=from_origin(-180 + 0.1 * j0 - 0.05, 90 - 0.1 * i0 + 0.05, 0.1, 0.1), dtype="uint8").astype(bool)
            out.append((i0, j0, m.shape, np.packbits(m)))
    return lvl, g0, out


if __name__ == "__main__":
    os.makedirs(f"{V1}/admin", exist_ok=True)
    land = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")["cls_day"][0] != 255
    lat = 90 - 0.1 * np.arange(NLAT)
    area = np.repeat((np.cos(np.deg2rad(lat)) * 11.1195 ** 2)[:, None], NLON, axis=1)
    res, tabs, rep = {}, {}, []
    for lvl in (1, 2):
        f = pq.ParquetFile(f"{B}/adm{lvl}/adm{lvl}_polygons.parquet")
        cols = [c for c in KEEP[lvl] if c in f.schema_arrow.names]
        tab = pq.read_table(f"{B}/adm{lvl}/adm{lvl}_polygons.parquet", columns=cols).to_pandas()
        ng = f.metadata.num_row_groups
        rows_before = np.concatenate([[0], np.cumsum([f.metadata.row_group(g).num_rows for g in range(ng)])])
        step = max(1, ng // 400)
        jobs = [(lvl, g, min(g + step, ng)) for g in range(0, ng, step)]
        grid = np.full((NLAT, NLON), -1, "i4")
        overlap = 0
        with Pool(32) as p:
            got = sorted(p.imap_unordered(job, jobs), key=lambda r: r[1])
        for _, g0, out in got:
            for k, item in enumerate(out):
                if item is None:
                    continue
                i0, j0, shp, bits = item
                m = np.unpackbits(bits, count=shp[0] * shp[1]).reshape(shp).astype(bool)
                sub = grid[i0:i0 + shp[0], j0:j0 + shp[1]]
                overlap += int((m & (sub >= 0)).sum())
                sub[m & (sub < 0)] = rows_before[g0] + k
        grid[~land] = -1
        ok = grid >= 0
        tab["land_cells"] = np.bincount(grid[ok], minlength=len(tab))
        tab["area_km2"] = np.round(np.bincount(grid[ok], weights=area[ok], minlength=len(tab))).astype("i8")
        res[lvl], tabs[lvl] = grid, tab
        rep.append(f"adm{lvl}: {len(tab):,} units; with at least one land cell: {int((tab.land_cells > 0).sum()):,}; with none: {int((tab.land_cells == 0).sum()):,}; "
                   f"land cells assigned: {int(ok.sum()):,} of {int(land.sum()):,} ({ok.sum() / land.sum():.1%}); cell centres inside two polygons: {overlap:,}")
    t1 = tabs[1]
    a0 = t1.groupby("adm0_id", sort=True).agg(adm0_name=("adm0_name", "first"), iso_3=("iso_3", "first"), n_adm1=("adm1_id", "size"),
                                                land_cells=("land_cells", "sum"), area_km2=("area_km2", "sum")).reset_index()
    code = pd.Series(np.arange(len(a0)), index=a0.adm0_id).reindex(t1.adm0_id).values
    g0 = np.where(res[1] >= 0, code[np.clip(res[1], 0, None)], -1).astype("i2")
    both = (res[1] >= 0) & (res[2] >= 0)
    mism = int((tabs[2].adm1_id.values[res[2][both]] != t1.adm1_id.values[res[1][both]]).sum()) if "adm1_id" in tabs[2] else -1
    rep.append(f"adm0: {len(a0)} countries and territories, taken from the adm1 table")
    rep.append(f"cells in an adm1 unit but in no adm2 unit: {int(((res[1] >= 0) & (res[2] < 0)).sum()):,}; the reverse: {int(((res[1] < 0) & (res[2] >= 0)).sum()):,}; "
               f"cells whose adm2 unit names a different adm1 than the adm1 raster: {mism:,}")
    north = np.repeat((lat > -60)[:, None], NLON, axis=1)
    rep.append(f"land cells north of 60 S in no adm1 unit: {int((land & north & (res[1] < 0)).sum()):,} of {int((land & north).sum()):,} ({(land & north & (res[1] < 0)).sum() / (land & north).sum():.1%})")
    np.savez_compressed(f"{V1}/admin/lookup.npz", adm1=res[1], adm2=res[2], adm0=g0)
    tabs[1].to_csv(f"{V1}/admin/units_adm1.csv", index=False, encoding="utf-8")
    tabs[2].to_csv(f"{V1}/admin/units_adm2.csv", index=False, encoding="utf-8")
    a0.to_csv(f"{V1}/admin/units_adm0.csv", index=False, encoding="utf-8")
    txt = "Admin lookup. Produced by pipeline/admin_lookup.py\n" + "\n".join(rep)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"), exist_ok=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "admin_lookup.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)
