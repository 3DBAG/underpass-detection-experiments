# edge-extension

Minimal Python library skeleton for reading polygon data from GeoJSON files and modifying selected
polygon edges.

## Scope

The current implementation keeps the project intentionally small:

- read and write GeoJSON feature collections
- read `MultiLineString` edge sets from GeoJSON
- rebuild a polygon-with-holes from separate movable and fixed edge collections
- classify reconstructed polygon boundary segments as movable or fixed
- operate on `shapely` polygons
- offset selected exterior edges by moving each edge along its outward perpendicular
- offset selected linework segments directly from split movable/fixed GeoJSON inputs
- rebuild the polygon by intersecting adjacent supporting lines

## Install

```bash
uv sync
```

## Example

```python
from pathlib import Path

from edge_extension.linework import load_polygon_from_edge_geojson
from edge_extension.offset_linework import offset_polygon_from_edge_geojson

polygon = load_polygon_from_edge_geojson(
    movable_edges_path=Path("tests/data/exterior_one.geojson"),
    fixed_edges_path=Path("tests/data/interior_one.geojson"),
)

expanded = offset_polygon_from_edge_geojson(
    movable_edges_path=Path("tests/data/exterior_one.geojson"),
    fixed_edges_path=Path("tests/data/interior_one.geojson"),
    distance=0.25,
    output_path=Path("tests/output/offset_polygon_from_edges.geojson"),
)
```

## Algorithm Note

The implemented approach is simple and works well for straightforward polygons and split edge
fixtures:

1. Treat every polygon edge as an infinite supporting line.
2. Reconstruct and classify boundary segments from the supplied movable/fixed linework.
3. Move only the movable supporting lines along their outward normals.
4. Keep fixed edges in place.
5. Recompute each vertex as the intersection of two adjacent lines.

That directly handles the "extend open edges until they intersect again" part of the problem.

For more difficult cases, a more robust next step would be a constrained half-plane intersection
approach or a straight-skeleton-style reconstruction for concave polygons, very large offsets, and
polygons with holes that may collapse or self-intersect.
