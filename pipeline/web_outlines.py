"""Country lines and name points for the map, for orientation only.

Source: E:/temp/boundaries/adm0/adm0_polygons.parquet (OpenStreetMap-based
country polygons of the FieldMaps release of 2025-07-29, view "all", ODbL).
The polygons are simplified as one coverage, so neighbours keep a shared
edge, then reduced to the land borders between them, each kept once. Coasts
are left out: the edge of the land cells already shows them.

These lines are a drawing aid. They are not used for any number: admin
shares use the adm1 and adm2 polygons through pipeline/admin_lookup.py, whose
view of disputed areas ("intl") can differ from this file's ("all"). Lines and
names are shown as the source gives them.

Output, outside the repository (pipeline/web_products.py copies it into the site):
    E:/temp/agera5/derived-products/heat-explorer/v1/web/countries.json
        {"lines": GeoJSON MultiLineString, coordinates to 0.01 degree,
         "labels": [{"name", "lon", "lat", "rank"}], rank 1 = largest area}

Run:  bash tools/py.sh -W ignore pipeline/web_outlines.py
"""
import json
import os
import time

import numpy as np
import pyarrow.parquet as pq
import shapely

SRC = "E:/temp/boundaries/adm0/adm0_polygons.parquet"
OUT = "E:/temp/agera5/derived-products/heat-explorer/v1/web"
TOL = 0.05          # degrees, about half a grid cell

if __name__ == "__main__":
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    t = pq.read_table(SRC, columns=["adm0_name", "geometry"])
    names = [str(n) for n in t.column("adm0_name").to_pylist()]
    geoms = shapely.from_wkb(np.array(t.column("geometry").to_pylist(), dtype=object))
    print(f"read {len(geoms)} polygons, {time.time() - t0:.0f} s", flush=True)
    how = "coverage"
    cache = f"{OUT}/adm0_simplified_{TOL}.npy"                # the coverage step takes about 11 minutes
    if os.path.exists(cache):
        simp = shapely.from_wkb(np.load(cache, allow_pickle=True))
        how = "coverage (from cache)"
    else:
        try:
            simp = shapely.coverage_simplify(geoms, TOL)
        except Exception as e:                              # not a valid coverage, or an older GEOS
            how = f"each polygon alone ({type(e).__name__})"
            simp = shapely.simplify(geoms, TOL, preserve_topology=True)
        np.save(cache, np.array(shapely.to_wkb(simp), dtype=object), allow_pickle=True)
    print(f"simplified by {how}, {time.time() - t0:.0f} s", flush=True)
    # land borders only: for each pair of neighbouring countries, the part of their outlines they share.
    # Coasts are left out (the edge of the land cells already shows them, and they are most of the points).
    # Polygon parts under 0.002 square degrees (about 20 km2) are dropped first: tiny islands have no land border.
    def big_parts(g):
        ps = shapely.get_parts(g)
        return shapely.multipolygons(ps[shapely.area(ps) >= 0.002]) if len(ps) else g
    simp = np.array([big_parts(g) for g in simp], dtype=object)
    bnd = shapely.boundary(simp)
    tree = shapely.STRtree(simp)
    a_i, b_i = tree.query(simp, predicate="intersects")
    shared = [shapely.intersection(bnd[i], bnd[j]) for i, j in zip(a_i, b_i) if i < j]
    shared = [g for g in shared if not g.is_empty]
    lines = shapely.line_merge(shapely.union_all([p for g in shared for p in shapely.get_parts(g) if p.geom_type in ("LineString", "LinearRing") and p.length > 0]))
    print(f"neighbour pairs {int((a_i < b_i).sum())}, {time.time() - t0:.0f} s", flush=True)
    lines = shapely.set_precision(lines, 0.01)
    parts = [p for p in shapely.get_parts(lines) if not p.is_empty and p.length > 0.03]
    coords = [[[round(float(x), 2), round(float(y), 2)] for x, y in p.coords] for p in parts]
    area = shapely.area(geoms)
    order = np.argsort(-area)
    rank = np.empty(len(geoms), int)
    rank[order] = np.arange(1, len(geoms) + 1)
    labels = []
    for n, g, r in zip(names, geoms, rank):
        if n in ("None", "nan", ""):                          # the source gives no name for some areas (disputed and small ones): no label
            continue
        ps = shapely.get_parts(g)
        big = ps[int(np.argmax(shapely.area(ps)))]
        big = shapely.simplify(big, 0.02)
        c = big.centroid
        pt = c if big.contains(c) else big.representative_point()
        labels.append({"name": n, "lon": round(float(pt.x), 2), "lat": round(float(pt.y), 2), "rank": int(r)})
    labels.sort(key=lambda d: d["rank"])
    with open(f"{OUT}/countries.json", "w", encoding="utf-8") as f:
        json.dump({"source": "FieldMaps adm0 (OpenStreetMap), release 2025-07-29, ODbL 1.0; simplified to 0.05 degree; for drawing only",
                   "lines": {"type": "MultiLineString", "coordinates": coords}, "labels": labels, "what": "land borders between countries, no coasts"}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"DONE {time.time() - t0:.0f} s: {len(parts):,} lines, {sum(len(c) for c in coords):,} points, {len(labels)} names, "
          f"{os.path.getsize(f'{OUT}/countries.json') / 1e6:.2f} MB; simplified by {how}")
