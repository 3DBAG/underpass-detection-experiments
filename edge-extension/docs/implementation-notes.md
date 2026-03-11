# Implementation Notes

## 2026-03-11

### Scope

- Implement the plan from `docs/implementation-plan.md`.
- Keep the existing reconstruction path intact.
- Add a linework-aware offset path that starts from split movable/fixed edge GeoJSON inputs.

### Design Direction

- Add `src/edge_extension/rings.py` to classify reconstructed polygon boundary segments as
  movable or fixed.
- Add `src/edge_extension/offset_linework.py` to offset only movable segments and rebuild valid
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
