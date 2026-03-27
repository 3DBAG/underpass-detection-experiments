# Implementation Plan

## Goal

Implement robust partial polygon offsetting from split edge GeoJSON inputs:

- `tests/data/exterior_one.geojson`: edges that may move
- `tests/data/interior_one.geojson`: edges that must remain fixed

The combined linework forms one valid polygon with holes. The library should offset only selected
boundary segments and rebuild a valid polygon after extending neighboring edges to new
intersections.

`tests/data/polygon.geojson` is the reference geometry for reconstruction and should be treated as
the ground truth output for the current fixture set.

## Current State

- GeoJSON feature collection I/O exists.
- Polygon reconstruction from combined `MultiLineString` fixtures exists.
- A simple edge-index-based polygon offset exists for already reconstructed polygon shells.

## Phase 1: Reconstruct and Classify Boundary Segments

1. Load both edge datasets and normalize them into individual `LineString` segments.
2. Rebuild the polygon-with-holes from the combined linework.
3. Extract oriented boundary rings from the reconstructed polygon.
4. Snap input segments to the polygon boundary within a small tolerance.
5. Classify each boundary segment as `movable` or `fixed`.

Deliverable: a ring model that preserves segment order, ring membership, and move/fix labels.

## Phase 2: Offset Movable Segments

1. Represent each ring edge as an infinite supporting line.
2. Move only `movable` lines along the outward normal of the ring.
3. Leave `fixed` lines unchanged.
4. Recompute vertices from adjacent line intersections.
5. Rebuild each ring from the updated vertices.

Deliverable: updated exterior and interior rings with preserved orientation.

## Phase 3: Validity and Failure Handling

1. Validate ring closure, minimum edge length, and non-parallel neighbor constraints.
2. Detect self-intersections, ring inversions, and collapsed holes.
3. Require the final output polygon to pass `.is_valid`.
4. If the extended polygon is invalid, return the original input polygon instead of the offset result.
5. Return structured errors when offsets are geometrically impossible.
6. Add optional tolerance-based snapping for nearly intersecting lines.

Deliverable: predictable behavior for invalid or unstable offset requests, with a safe fallback to
the original polygon.

## Recommended Algorithm Direction

Start with line-based reconstruction because it matches the problem directly and is easy to reason
about. If concave cases or large offsets become unstable, upgrade to a half-plane intersection or
boolean patching approach per ring.

## Phase 4: Database Batch Input

1. Read grouped edge rows from PostGIS with an injected `psycopg` connection.
2. Accept the source table as a schema-qualified `psycopg.sql.Identifier`.
3. Treat `exterior_edges` as movable linework.
4. Merge `shared_edges` and `interior_edges` into the fixed linework input.
5. Reuse the existing reconstruction, classification, and offset pipeline for each
   `identificatie`/`underpass_id` group.
6. Write all output polygons into one GeoJSON `FeatureCollection`.

## Testing Plan

- Unit tests on rectangles and L-shaped polygons
- Fixture tests using `tests/data/*`
- Exact reconstruction checks against `tests/data/polygon.geojson`
- Cases with holes, concave corners, and parallel adjacent edges
- Regression tests that confirm invalid offset results fall back to the original input polygon
- Mocked database adapter tests that verify row mapping and GeoJSON batch output

## Suggested File Additions

- `src/edge_offset/rings.py`: ring extraction and segment classification
- `src/edge_offset/offset_linework.py`: partial-offset implementation
- `tests/test_linework_classification.py`
- `tests/test_offset_linework.py`
