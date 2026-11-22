"""Coastline and province borders for drawing, as smooth lines.

Companion to pipeline/web_outlines.py (country land borders and names). Both
are drawing aids only: no number on the page uses them.

    coast.json      the outer edge of all land together, from the simplified country polygons
                    (FieldMaps adm0, OpenStreetMap, ODbL). Polygon parts under COAST_MIN square
                    degrees (about 200 km2) are left out, as are coast pieces shorter than
                    0.3 degree: small islands would be most of the file.
    provinces.json  borders between provinces of the SAME country, from the adm1 polygons
                    (FieldMaps edge-matched, ODbL), simplified as one coverage so neighbours
                    share an edge. Borders between countries are not repeated here: they come
                    from the country file, whose view of some borders differs slightly.

Coordinates are rounded to 0.01 degree. Output, outside the repository, in
E:/temp/agera5/derived-products/heat-explorer/v1/web/ ; pipeline/web_products.py copies it into the site.
The coverage simplification of adm1 is slow and is cached beside the output.

Run:  bash tools/py.sh -W ignore pipeline/web_lines.py
"""
import json
import os
import time

import numpy as np
import pyarrow.parquet as pq
import shapely

B = "E:/temp/boundaries"
OUT = "E:/temp/agera5/derived-products/heat-explorer/v1/web"
TOL, COAST_MIN = 0.05, 0.02


def big_parts(g, amin):
    ps = shapely.get_parts(g)
    ps = ps[shapely.area(ps) >= amin]
    return shapely.multipolygons(ps) if len(ps) else None


def write(name, lines, what, minlen):
    lines = shapely.set_precision(shapely.line_merge(lines), 0.01)
    parts = [q for q in shapely.get_parts(lines) if not q.is_empty and q.length > minlen]
    coords = [[[round(float(x), 2), round(float(y), 2)] for x, y in q.coords] for q in parts]
    with open(f"{OUT}/{name}", "w", encoding="utf-8") as f:
        json.dump({"what": what, "lines": {"type": "MultiLineString", "coordinates": coords}}, f, separators=(",", ":"))
    print(f"{name}: {len(parts):,} lines, {sum(len(c) for c in coords):,} points, {os.path.getsize(f'{OUT}/{name}') / 1e6:.2f} MB", flush=True)


if __name__ == "__main__":
    t0 = time.time()
    simp0 = shapely.from_wkb(np.load(f"{OUT}/adm0_simplified_{TOL}.npy", allow_pickle=True))      # made by web_outlines.py
    big = [q for q in (big_parts(g, COAST_MIN) for g in simp0) if q is not None]
    allb = shapely.union_all(shapely.boundary(np.array(big, dtype=object)))                      # every outline, shared borders once
    tree = shapely.STRtree(big)
    a_i, b_i = tree.query(big, predicate="intersects")
    bnd = shapely.boundary(np.array(big, dtype=object))
    shared = [shapely.intersection(bnd[i], bnd[j]) for i, j in zip(a_i, b_i) if i < j]
    borders = shapely.union_all([q for g in shared if not g.is_empty for q in shapely.get_parts(g) if q.geom_type in ("LineString", "LinearRing")])
    coast = shapely.difference(allb, shapely.buffer(borders, 1e-6))                              # outlines that are not a border between two countries
    print(f"coast computed {time.time() - t0:.0f} s", flush=True)
    write("coast.json", coast, "coastline of land parts over about 200 km2; FieldMaps adm0 (OpenStreetMap), ODbL 1.0; simplified to 0.05 degree; for drawing only", 0.3)

    cache = f"{OUT}/adm1_simplified_{TOL}.npy"
    t = pq.read_table(f"{B}/adm1/adm1_polygons.parquet", columns=["adm0_id"] if os.path.exists(cache) else ["adm0_id", "geometry"])
    a0 = np.array(t.column("adm0_id").to_pylist(), dtype=object)
    if os.path.exists(cache):
        simp1 = shapely.from_wkb(np.load(cache, allow_pickle=True))
    else:
        g1 = shapely.from_wkb(np.array(t.column("geometry").to_pylist(), dtype=object))
        print(f"adm1 read, {len(g1)} polygons, {time.time() - t0:.0f} s", flush=True)
        simp1 = shapely.coverage_simplify(g1, TOL)
        np.save(cache, np.array(shapely.to_wkb(simp1), dtype=object), allow_pickle=True)
        del g1
    print(f"adm1 simplified {time.time() - t0:.0f} s", flush=True)
    keep = [(big_parts(g, 0.002), c) for g, c in zip(simp1, a0)]
    polys = np.array([q for q, _ in keep if q is not None], dtype=object)
    ctry = np.array([c for q, c in keep if q is not None], dtype=object)
    bnd1 = shapely.boundary(polys)
    tree = shapely.STRtree(polys)
    a_i, b_i = tree.query(polys, predicate="intersects")
    pairs = [(i, j) for i, j in zip(a_i, b_i) if i < j and ctry[i] == ctry[j]]                   # provinces of the same country only
    sh = [shapely.intersection(bnd1[i], bnd1[j]) for i, j in pairs]
    lines = shapely.union_all([q for g in sh if not g.is_empty for q in shapely.get_parts(g) if q.geom_type in ("LineString", "LinearRing") and q.length > 0])
    print(f"province pairs {len(pairs):,}, {time.time() - t0:.0f} s", flush=True)
    write("provinces.json", lines, "borders between provinces of the same country; FieldMaps edge-matched adm1, ODbL 1.0; simplified to 0.05 degree; for drawing only", 0.03)
    print(f"DONE {time.time() - t0:.0f} s")
