# Simple 3D Tiles Viewer

Cesium viewer for testing local `tileset.json` trees, with a `nix run` launcher that serves the current directory with CORS.

## Usage

From any directory containing a `tileset.json`:

```sh
nix run github:3dgi/tv
```

To force a rebuild of the viewer app:

```sh
nix run --refresh github:3dgi/tv
```
This is only necessary if this repo had an update.

By default the launcher serves and opens these two tilesets:

- `/data2/rypeters/ams-run-07-07-rf/seq_underpasses_pmp_3dt`
- `/data2/rypeters/amsterdam_data/2025/cropped-3dtiles`

Optional flags:

```sh
nix run github:3dgi/tv -- --port 8090 --tileset path/to/tileset.json
```

Pass `--tileset` more than once to load multiple tilesets.

## Local development

Run from the local repository:

```sh
git clone git@github.com:3DGI/tv.git
cd ./tv
nix run .
```

To force a rebuild of your local checkout:

```sh
nix run --refresh .
```

Run from a directory containing `tileset.json`:

```sh
cd /path/to/tileset-dir
nix run --refresh ./tv
```

Serve a tileset from a different directory:

```sh
nix run --refresh ./tv -- --tileset /path/to/tileset-dir/tileset.json
```

Optional flags:

```sh
nix run --refresh ./tv -- --port 8090 --viewer-port 8091 --tileset /path/to/tileset.json
```

The `--tileset` value can be either a `tileset.json` file or a directory containing one.

The command starts a local static server with permissive CORS headers and prints:

- the local tileset URL
- a local viewer URL

The viewer includes a `Terrain` selector with three modes:

- `None`
- `Cesium World Terrain` (requires a Cesium Ion token)
- `PDOK Quantized Mesh` via `https://api.pdok.nl/kadaster/3d-basisvoorziening/ogc/v1/collections/digitaalterreinmodel/quantized-mesh`

The selected terrain mode is persisted in the URL as the `terrain` query parameter.

Available tilesets are loaded from `data/tilesets.json` and listed in a `Tilesets` panel. Only manifest-listed tilesets can be loaded, the last manifest entry is loaded by default, only one tileset is shown at a time, and switching tilesets preserves the current camera view. Underpass colors and the legend are enabled by default.

## Deploy

To build and deploy the static viewer to `godzilla:/var/www/innovatiebudget-3dtiles`:

```sh
bun run deploy
```

To also upload a 3D Tiles directory and add it to the remote tileset selector:

```sh
bun run deploy -- /path/to/tileset-dir
```

You can override the target with `DEPLOY_HOST` and `DEPLOY_PATH`.

The deploy script syncs the static app with `--delete`, but excludes the remote `data/`
directory from deletion. When a tileset directory is provided, it is synced to
`$DEPLOY_PATH/data/<tileset-dir-name>/`, and `$DEPLOY_PATH/data/tilesets.json` is
refreshed by merging discovered remote tileset folders with any existing manifest
entries. Existing labels and names are preserved, and a newly uploaded tileset is
moved to the end of the manifest so it becomes the viewer default.
