# Implementation Notes

## 2026-03-11

### Scope

- Implement the plan from `docs/implementation-plan.md`.
- Keep the existing reconstruction path intact.
- Add a linework-aware offset path that starts from split movable/fixed edge GeoJSON inputs.

### Design Direction

- Add `src/edge_offset/rings.py` to classify reconstructed polygon boundary segments as
  movable or fixed.
- Add `src/edge_offset/offset_linework.py` to offset only movable segments and rebuild valid
  rings from supporting-line intersections.
- Keep file output in the library API so tests can materialize GeoJSON into `tests/output`.

### Geometry Assumptions

- The split GeoJSON inputs describe one valid polygon with holes when combined.
- Input `MultiLineString` geometries may contain multi-vertex paths, so they need to be exploded
  into individual boundary segments before classification.
- A tolerance-based normalized segment key should be sufficient for the current fixtures because
  the reconstructed polygon vertices come directly from the supplied linework.

### Implemented Matching Strategy

- Reconstruct the polygon first from the combined movable and fixed linework, then orient it with a
  standard exterior CCW / interior CW convention.
- Explode each input `MultiLineString` into individual two-point `LineString` segments.
- Match polygon boundary segments to input segments with an order-independent quantized segment key.
- Consume matched segment keys from counters so every supplied segment must map to the boundary
  exactly once.

### Implemented Reconnection Strategy

- Build one supporting line per classified boundary segment.
- Offset only the segments marked movable; fixed segments stay on their original supporting lines.
- Recompute each vertex from the previous/current supporting-line pair.
- If adjacent lines are parallel but still coincident, project the original vertex back onto the
  shared line instead of failing. This keeps collinear runs stable.
- If adjacent lines are parallel and separated, raise an error because the requested offset cannot
  reconnect that corner with the current line-based model.

### Validation

- `uv run pytest` passes with the new classifier and linework-offset tests.
- `uv run ruff check` passes after the implementation landed.
- The fixture-driven offset path writes GeoJSON output into `tests/output`.

## 2026-03-12

### Boolean Patching Upgrade Direction

- Prefer a per-chain patch model over a full-ring rebuild.
- Group consecutive movable boundary segments into one `movable chain` and compute one patch
  polygon per chain.
- Apply each patch to the original polygon material with boolean operations instead of manually
  stitching the entire output boundary.

### Proposed Geometry Pipeline

- Reconstruct and classify the input polygon as the current implementation already does.
- For each ring, collapse consecutive movable segments into chain objects that also record the
  previous and next fixed segments.
- Shift each movable segment along its polygon-outward normal by the requested distance.
- Build a replacement chain from support-line intersections:
  - start vertex = previous fixed line with first shifted line
  - interior vertices = adjacent shifted-line intersections
  - end vertex = last shifted line with next fixed line
- Form a patch polygon from the original chain path, the replacement chain path, and the two end
  connectors.

### Boolean Application Rule

- Determine whether the patch adds or removes polygon material with a midpoint containment test on
  the shifted chain.
- If the shifted chain lies outside the original polygon material, apply `polygon.union(patch)`.
- If the shifted chain lies inside the original polygon material, apply
  `polygon.difference(patch)`.
- After each patch, require a single valid polygon result; if invalid, fall back to the original
  input polygon.

### Suggested Module Shape

- Add a chain model in `src/edge_offset/rings.py` so classification can expose grouped movable
  runs directly.
- Add patch builders in `src/edge_offset/offset_linework.py` instead of replacing the current
  API surface.
- Keep public entry points explicit and keyword-driven, for example
  `offset_polygon_from_edge_geojson(..., strategy="linework" | "boolean_patch")`.

### Expected Failure Modes

- Nearly parallel start or end junctions may create numerically unstable patch vertices.
- A patch may overlap unrelated polygon regions in highly concave cases.
- Boolean operations may yield a `MultiPolygon` when a single polygon is required.
- Any of the above should trigger the documented fallback to the original input polygon.

### Implemented Boolean Patch Path

- `src/edge_offset/offset_linework.py` now uses `strategy="boolean_patch"` by default.
- Consecutive movable segments are grouped into per-ring chains before any geometry update is
  attempted.
- Each chain builds one patch polygon from the original chain, the shifted replacement chain, and
  the implicit end connectors formed by the closed patch boundary.
- The patch is applied with `union` or `difference` based on whether a midpoint sample along the
  shifted chain falls outside or inside the original polygon material.
- Any empty, invalid, or multi-part boolean result raises an internal geometry error and causes the
  public API to return the original input polygon.

### Compatibility Notes

- The previous support-line reconstruction path remains available as `strategy="linework"`.
- Fully movable rings currently fall back to the linework path because the boolean patch model
  needs fixed anchor edges at both ends of a movable chain.

### Database Input Integration

- Add a dedicated PostGIS adapter instead of teaching the geometry modules about SQL or connection
  lifecycle.
- Keep the main batch API connection-injected: the caller supplies a configured `psycopg`
  connection and a schema-qualified `psycopg.sql.Identifier` for the edge table.
- Read `exterior_edges` as movable linework and merge `shared_edges` with `interior_edges` into
  the fixed linework input expected by the existing classifier.
- Continue to keep local `.env` handling outside the core library path; a thin export script can
  load `.env` and create the connection for local development without changing the library API.

### Validation

- `uv sync` installs `psycopg` into the project environment.
- `uv run pytest` passes with the new PostGIS adapter tests.
- `uv run ruff check .` passes after the database-backed export path landed.

### Near-Parallel Spike Fix

- Two live database rows produced incorrect offset spikes:
  `identificatie='NL.IMBAG.Pand.0363100012165490', poly_id=118` and
  `identificatie='NL.IMBAG.Pand.0363100012165490', poly_id=119`.
- Both failures came from a near-parallel join between a movable chain edge and its neighboring
  fixed edge.
- The previous implementation accepted the infinite-line intersection at that join, which created a
  very long miter vertex far away from the original building footprint even for a `0.25` meter
  offset request.

### Implemented Join Limit

- Add a miter limit to line-based corner resolution in `src/edge_offset/offset_linework.py`.
- If the resolved join vertex lands more than `10x` the requested offset distance away from the
  original polygon vertex, do not use that infinite-line intersection.
- Instead, fall back to a bevel-style join formed from the projected endpoints of the shifted
  segments.
- Apply the same safeguard in both the default `strategy="boolean_patch"` path and the legacy
  `strategy="linework"` path so both public APIs remain consistent.

### Regression Coverage

- Export the failing live database rows into:
  - `tests/data/pand_0363100012165490_poly_118_movable.geojson`
  - `tests/data/pand_0363100012165490_poly_118_fixed.geojson`
  - `tests/data/pand_0363100012165490_poly_119_movable.geojson`
  - `tests/data/pand_0363100012165490_poly_119_fixed.geojson`
- Add regression tests in `tests/test_offset_linework.py` that confirm both strategies keep the
  offset geometry local to the source polygon instead of producing a long spike.
