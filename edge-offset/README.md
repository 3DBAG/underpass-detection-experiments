# edge-offset

`edge-offset` is a small Python library for rebuilding polygons from split edge linework and
offsetting only the boundary segments marked as movable. It supports both local GeoJSON inputs and
batch export from a PostGIS edge table.

## Current Capabilities

- read and write GeoJSON `FeatureCollection` files
- rebuild a single polygon-with-holes from movable and fixed edge linework
- classify reconstructed boundary segments into ordered rings
- offset selected boundary chains with `strategy="boolean_patch"` by default
- keep the older support-line reconstruction path available as `strategy="linework"`
- read grouped edge rows from PostGIS through an injected `psycopg` connection
- export all offset results into one GeoJSON `FeatureCollection`

## Install

```bash
uv sync
```

## Module Overview

- `edge_offset.geojson`: GeoJSON feature collection I/O
- `edge_offset.linework`: polygon reconstruction from movable/fixed edge sets
- `edge_offset.rings`: boundary-ring and segment classification
- `edge_offset.offset_linework`: partial polygon offsets from classified linework
- `edge_offset.postgis`: batch loading and export from a PostGIS edge table
- `edge_offset.polygon_ops`: lower-level edge-index offsets for already reconstructed polygons

## Rebuild From Edge GeoJSON

```python
from pathlib import Path

from edge_offset.linework import load_polygon_from_edge_geojson

polygon = load_polygon_from_edge_geojson(
    movable_edges_path=Path("tests/data/exterior_one.geojson"),
    fixed_edges_path=Path("tests/data/interior_one.geojson"),
)
```

## Offset From Edge GeoJSON

```python
from pathlib import Path

from edge_offset.offset_linework import GeometryOffsetError
from edge_offset.offset_linework import InvalidInputPolygonError
from edge_offset.offset_linework import offset_polygon_from_edge_geojson

try:
    expanded = offset_polygon_from_edge_geojson(
        movable_edges_path=Path("tests/data/exterior_one.geojson"),
        fixed_edges_path=Path("tests/data/interior_one.geojson"),
        distance=0.25,
        output_path=Path("tests/output/offset_polygon_from_edges.geojson"),
    )
except InvalidInputPolygonError:
    # The assembled source linework is not a valid polygon.
    raise
except GeometryOffsetError:
    # Retry with distance=0.0 for the validated unmodified polygon, or choose a new distance.
    raise
```

To classify first and offset later, use `classify_polygon_from_edge_geojson()` or
`classify_polygon_from_edge_sets()` from `edge_offset.rings`, then pass the result to
`offset_polygon_from_classified_polygon()`.

## Batch Export From PostGIS

```python
from pathlib import Path

from psycopg import connect
from psycopg.sql import Identifier

from edge_offset.offset_linework import GeometryOffsetError
from edge_offset.offset_linework import InvalidInputPolygonError
from edge_offset.postgis import write_offset_polygons_from_db

with connect(host="localhost", port=5557, dbname="baseregisters", user="bdukai") as connection:
    try:
        write_offset_polygons_from_db(
            connection,
            edges_table=Identifier("underpasses", "edges"),
            distance=0.25,
            output_path=Path("tests/output/offset_polygons_from_db.geojson"),
        )
    except (InvalidInputPolygonError, GeometryOffsetError):
        # Handle or skip the failed batch according to your integration policy.
        raise
```

`edge_offset.postgis` expects:

- Individual edge rows with `edge_type` of 'exterior' (movable linework - edges that can be offset)
- Individual edge rows with `edge_type` of 'shared' (fixed linework - edges shared with adjacent buildings)
- Individual edge rows with `edge_type` of 'interior' (fixed linework - edges inside the underpass area)
- Edge table structure: `edge_id`, `underpass_id`, `identificatie`, `edge_type`, `geom`
- LineString geometries (created by ST_Dump of merged linework from edges.sql)
- One output feature per unique `identificatie` / `underpass_id` combination

## Local Export Script

Run the helper script with:

```bash
uv run python scripts/export_offset_polygons.py
```

The script reads `.env` if present and requires these variables:

- `EDGE_OFFSET_DB_HOST`
- `EDGE_OFFSET_DB_PORT`
- `EDGE_OFFSET_DB_NAME`
- `EDGE_OFFSET_DB_USER`
- `EDGE_OFFSET_OUTPUT_PATH`
- `EDGE_OFFSET_OFFSET_DISTANCE`

Optional:

- `EDGE_OFFSET_DB_PASSWORD`

The script currently exports from `underpasses.edges`.

## Caller Contract

Offset calls first assemble the movable and fixed edge linework into the unmodified polygon, then
validate that polygon with Shapely/GEOS. If the assembled geometry is empty, not a polygon, invalid,
or collapsed below the tolerance area, the public API raises `InvalidInputPolygonError`.

For nonzero offset requests, `offset_polygon_from_edge_geojson()`,
`offset_polygon_from_classified_polygon()`, and the PostGIS helpers either return a valid offset
`Polygon` or raise `GeometryOffsetError`. The original polygon is returned only when the requested
distance is effectively zero for the supplied tolerance. Callers that need a validated unmodified
polygon after an offset failure can retry with `distance=0.0`, or retry with a different nonzero
distance.

## Offset Strategy

`strategy="boolean_patch"` is the default path:

1. Reconstruct and classify the polygon boundary from movable and fixed linework.
2. Group consecutive movable segments into chains.
3. Shift each chain outward by the requested distance.
4. Build a patch polygon between the original and shifted chain.
5. Apply the patch with `union()` or `difference()` depending on whether it adds or removes area.

If offset construction produces an empty, invalid, collapsed, or non-polygon result, the public API
raises `GeometryOffsetError`.

Use `strategy="linework"` to force the older support-line reconstruction path. Fully movable rings
currently route through that path even when `boolean_patch` is requested.

## Development

```bash
uv run pytest
uv run ruff check .
```
