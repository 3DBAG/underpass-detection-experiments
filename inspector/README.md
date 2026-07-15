# Alignment Inspector

Browser-based comparison of one FlatCityBuf building model with the nearby points from a city-wide COPC file. Building lookup and point decoding happen client-side. The Vite development server exposes the local data with HTTP byte-range support and provides a small persistent review-tag API.

## Data prerequisite

The FlatCityBuf source must contain an attribute index for `identificatie`. The build also creates a small `*.underpasses.json` navigation manifest from features whose `BuildingPart` has `add_underpass_success` set.

The `wasmwork` serializer currently fetches every extension schema URL while finalizing the FCB header. The 3DBAG sequences declare the val3dity extension, which can make an otherwise local conversion fail with an HTTP JSON decode error. Use the helper script to remove that unused declaration from the merged header and build the indexed file:

```bash
./scripts/build-viewer-fcb.sh \
  /data2/rypeters/ams-run-07-15-rf/seq_underpasses_manifold \
  /data2/rypeters/ams-run-07-15-rf/seq_underpasses_manifold/city.viewer.fcb
```

Messages such as `Attribute identificatie not found in schema` are currently printed once for CityObjects such as `BuildingPart` that do not carry that attribute. The corresponding parent `Building` does carry it, so these messages do not prevent creation of the `identificatie` index.

The manifest is ordered by building ID. It lets the browser resolve previous/next positions—including for a building entered directly—while individual buildings are still fetched through the FCB `identificatie` index.

The app vendors the generated WASM bindings from `Ylannl/flatcitybuf` branch `wasmwork`. It uses `HttpFcbReader.select_attr_query_paged` and requests one matching feature.

## Run

```bash
npm install
FCB_PATH=/data2/rypeters/ams-run-07-15-rf/seq_underpasses_manifold/city.viewer.fcb npm run dev
```

Open:

```text
http://localhost:5173/?building=NL.IMBAG.Pand.0363100012061167
```

A numeric BAG ID entered in the search field is normalized to the `NL.IMBAG.Pand.` form. Browser back/forward navigation restores the selected building.

Local paths and browser-facing URLs can be overridden:

```bash
FCB_PATH=/path/to/city.fcb
COPC_PATH=/path/to/merged.copc
TAG_DB_PATH=/path/to/viewer-tags.json
VITE_FCB_URL=https://data.example/city.fcb
VITE_COPC_URL=https://data.example/merged.copc
VITE_UNDERPASS_URL=https://data.example/city.viewer.underpasses.json
VITE_TAG_API_URL=https://viewer.example/api/tags
```

Remote files must support `Range` requests and expose `Content-Range`, `Content-Length`, and `Accept-Ranges` through CORS. Hosting must also serve `laz-perf.wasm` as `application/wasm`.

## Review tags

Each underpass can have one review status (`Approved`, `Wrong elevation`, `PointCloud insufficient`, or `Faulty underpass geometry`). `Highlight` remains building-level and can be combined with any underpass status. The Vite server stores reviews atomically in `.viewer-tags.json` by default; use `TAG_DB_PATH` to keep the database elsewhere.

Buildings with one underpass retain the compact review UI. Buildings with several get a local underpass selector; clicking an `OuterCeilingSurface` also selects it. The selected `underpass_id` is stored in the URL so filtered review links open the exact surface.

The API supports both individual records and tag-based lookup:

```text
GET /api/tags/NL.IMBAG.Pand.0363100012061167?underpass=138690
PUT /api/tags/NL.IMBAG.Pand.0363100012061167
PUT /api/tags/NL.IMBAG.Pand.0363100012061167/138690
GET /api/tags?tag=Approved
```

The building-level `PUT` accepts only `Highlight`; the underpass-level `PUT` accepts one review status. Collection responses contain review targets with both `buildingId` and, for status tags, `underpassId`. A static production deployment needs to provide the same API and configure `VITE_TAG_API_URL` accordingly.

Version 1 tag databases are migrated losslessly when first written. Highlight moves directly to the building. A status is automatically attached when the loaded building has exactly one underpass; for multi-underpass buildings it remains an unassigned legacy status until the reviewer explicitly assigns it in the UI.

Review statuses can be clicked directly or toggled with `1`, `2`, `3`, and `4`. Use the left and right arrow keys to move to the previous or next underpass object. Press `T` to cycle the building display through the complete model, outer ceiling surfaces only, and no model. The `?` button in the header lists these shortcuts and explains the review tags. Keyboard shortcuts are suspended while typing in a field or adjusting a slider.

When an underpass has no `underpass_candidate_peaks` semantic-surface attribute, it receives `PointCloud insufficient` automatically. This is a default rather than a lock: reviewers can replace or clear it, and that explicit override is retained on later loads. Existing explicit statuses are never overwritten. `Highlight` remains available independently.

Picking is always active: click the model or point cloud to inspect world coordinates and matching semantic-surface attributes. Dragging still rotates the view without producing a pick.

## Loading behavior

- FCB WASM reads the header, attribute index, and matching feature byte range.
- The COPC worker reads the header and only hierarchy pages whose bounds intersect the building footprint plus a 3 m horizontal margin. The query spans the COPC dataset's full vertical extent.
- Matching LAZ nodes are decoded off the UI thread, filtered to that horizontal extent, and streamed to Three.js.
- The point budget changes maximum octree depth and sampling. Changing it restarts only the point-cloud worker.

For the included 7.6 GB COPC and the example building, the default view displays about 76K points using roughly 2.2 MB across 18 COPC range responses. Exact values depend on the selected building and point budget.

## Checks

```bash
npm run lint
npm run build
```
