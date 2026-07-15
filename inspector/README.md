# Alignment Inspector

Browser-based comparison of one FlatCityBuf building model with the nearby points from a city-wide COPC file. Building lookup and point decoding both happen client-side. The Vite development middleware only exposes the local files with HTTP byte-range support; there is no application API.

## Data prerequisite

The FlatCityBuf source must contain an attribute index for `identificatie`. The build also creates a small `*.underpasses.json` navigation manifest from buildings that have an `underpass_id` attribute.

The `wasmwork` serializer currently fetches every extension schema URL while finalizing the FCB header. The 3DBAG sequences declare the val3dity extension, which can make an otherwise local conversion fail with an HTTP JSON decode error. Use the helper script to remove that unused declaration from the merged header and build the indexed file:

```bash
./scripts/build-viewer-fcb.sh \
  /data2/rypeters/ams-run-07-14-rf/seq_underpasses_manifold \
  /data2/rypeters/ams-run-07-14-rf/seq_underpasses_manifold/city.viewer.fcb
```

Messages such as `Attribute identificatie not found in schema` are currently printed once for CityObjects such as `BuildingPart` that do not carry that attribute. The corresponding parent `Building` does carry it, so these messages do not prevent creation of the `identificatie` index.

The manifest is ordered by `underpass_id`. It lets the browser resolve previous/next positions—including for a building entered directly—while individual buildings are still fetched through the FCB `identificatie` index.

The app vendors the generated WASM bindings from `Ylannl/flatcitybuf` branch `wasmwork`. It uses `HttpFcbReader.select_attr_query_paged` and requests one matching feature.

## Run

```bash
npm install
FCB_PATH=/data2/rypeters/ams-run-06-30-rf/seq/city.viewer.fcb npm run dev
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
VITE_FCB_URL=https://data.example/city.fcb
VITE_COPC_URL=https://data.example/merged.copc
VITE_UNDERPASS_URL=https://data.example/city.viewer.underpasses.json
```

Remote files must support `Range` requests and expose `Content-Range`, `Content-Length`, and `Accept-Ranges` through CORS. Hosting must also serve `laz-perf.wasm` as `application/wasm`.

## Loading behavior

- FCB WASM reads the header, attribute index, and matching feature byte range.
- The COPC worker reads the header and only hierarchy pages whose bounds intersect the building extent plus a 3 m margin.
- Matching LAZ nodes are decoded off the UI thread, filtered to the exact extent, and streamed to Three.js.
- The point budget changes maximum octree depth and sampling. Changing it restarts only the point-cloud worker.

For the included 7.6 GB COPC and the example building, the default view displays about 76K points using roughly 2.2 MB across 18 COPC range responses. Exact values depend on the selected building and point budget.

## Checks

```bash
npm run lint
npm run build
```
