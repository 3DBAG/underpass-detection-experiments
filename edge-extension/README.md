# edge-extension

Minimal Python library skeleton for reading polygon data from GeoJSON files and modifying selected
polygon edges.

## Scope

The current implementation keeps the project intentionally small:

- read and write GeoJSON feature collections
- read `MultiLineString` edge sets from GeoJSON
- rebuild a polygon-with-holes from separate movable and fixed edge collections
- operate on `shapely` polygons
- offset selected exterior edges by moving each edge along its outward perpendicular
- rebuild the polygon by intersecting adjacent supporting lines

## Install

```bash
uv sync
```

## Example

```python
from pathlib import Path

from edge_extension.geojson import read_feature_collection
from edge_extension.linework import load_polygon_from_edge_geojson
from edge_extension.polygon_ops import EdgeOffset
from edge_extension.polygon_ops import offset_polygon_edges

polygon = load_polygon_from_edge_geojson(
    movable_edges_path=Path("tests/data/exterior_one.geojson"),
    fixed_edges_path=Path("tests/data/interior_one.geojson"),
)

features = read_feature_collection(Path("input.geojson"))
polygon = features[0].geometry
expanded = offset_polygon_edges(
    polygon,
    [
        EdgeOffset(edge_index=1, distance=2.0),
        EdgeOffset(edge_index=2, distance=1.0),
    ],
)
```

## Algorithm Note

The implemented approach is simple and works well for straightforward polygons:

1. Treat every polygon edge as an infinite supporting line.
2. Move only the selected lines along their outward normals.
3. Keep unselected edges in place.
4. Recompute each vertex as the intersection of two adjacent lines.

That directly handles the "extend open edges until they intersect again" part of the problem.

For more difficult cases, a more robust next step would be a constrained half-plane intersection
approach or a straight-skeleton-style reconstruction for concave polygons, very large offsets, and
polygons with holes that may collapse or self-intersect.
