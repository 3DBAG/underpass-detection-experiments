# edge-offset

Minimal Python library skeleton for reading polygon data from GeoJSON files and modifying selected
polygon edges, including batch processing from a PostGIS edge table.

## Scope

The current implementation keeps the project intentionally small:

- read and write GeoJSON feature collections
- read `MultiLineString` edge sets from GeoJSON
- read grouped edge sets from a PostGIS table through an injected `psycopg` connection
- rebuild a polygon-with-holes from separate movable and fixed edge collections
- classify reconstructed polygon boundary segments as movable or fixed
- operate on `shapely` polygons
- offset selected exterior edges by moving each edge along its outward perpendicular
- offset selected linework segments directly from split movable/fixed GeoJSON inputs
- rebuild the polygon with boolean patching by default
- fall back to the original polygon if an offset result is invalid
- write all offset polygons into one GeoJSON feature collection

## Install

```bash
uv sync
```

## Example

```python
from pathlib import Path

from edge_offset.linework import load_polygon_from_edge_geojson
from edge_offset.offset_linework import offset_polygon_from_edge_geojson

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

## Database Batch Export

```python
from pathlib import Path

from psycopg import connect
from psycopg.sql import Identifier

from edge_offset.postgis import write_offset_polygons_from_db

with connect(host="localhost", port=5557, dbname="baseregisters", user="bdukai") as connection:
    write_offset_polygons_from_db(
        connection,
        edges_table=Identifier("underpasses_edge_extension", "edges"),
        distance=0.25,
        output_path=Path("tests/output/offset_polygons_from_db.geojson"),
    )
```

For local runs, copy `.env.example` to `.env` and run
`uv run python scripts/export_offset_polygons.py`.

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
