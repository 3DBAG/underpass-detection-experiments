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
- rebuild the polygon with boolean patching by default
- fall back to the original polygon if an offset result is invalid

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

The default implementation uses a boolean patch workflow:

1. Reconstruct and classify boundary segments from the supplied movable/fixed linework.
2. Group consecutive movable segments into chains.
3. Build a patch polygon between the original chain and its shifted replacement chain.
4. Apply each patch with `union` or `difference` against the original polygon material.
5. Return the original polygon if the boolean result is invalid.

The previous support-line reconstruction path is still available with `strategy="linework"`.

The boolean patch path is more robust for disconnected movable edge runs, holes, and cases where
local corner stitching is not enough.
