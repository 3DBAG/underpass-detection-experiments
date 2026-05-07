## Streetlidar run results
took around 59 min with 
```
RAYON_NUM_THREADS=3 python run_streetlidar_heights.py --within-index-extent     --grid-cell-size 500     --batch-workers 16     --pip-workers 5     --height-workers 1     --laz-backend lazrs-parallel     --decompression xyz
```


## add_underpasses run results

```
ADD_UNDERPASS=/home/rypeters/git/underpass-detection-experiments/modelling_3d/result/bin/add_underpass ./run_add_underpass.sh
input:       /fastssd/data/3DBAG_old/bouwlagen_features_seq (8962 files)
output:      /fastssd/data/3DBAG_old/bouwlagen_features_seq_underpass
logs:        /fastssd/data/3DBAG_old/logs_add_underpass
executable:  /home/rypeters/git/underpass-detection-experiments/modelling_3d/result/bin/add_underpass
jobs:        32
clean first: 1
100% 8962:0=0s /fastssd/data/3DBAG_old/bouwlagen_features_seq/9-132-260.city.jsonl
wrote 8962 rows to /fastssd/data/3DBAG_old/logs_add_underpass/results.csv

runtime: 1h3m13
```

## tyler run
```
> RAYON_NUM_THREADS=64 RUST_LOG=info /home/rypeters/git/tyler/target/release/tyler     --3dtiles-implicit  --grid-minz=-15   --output /data2/rypeters/3dt-nlup     --include-parent-attributes     --lod-building-part "2.2"     --object-type BuildingPart  /fastssd/data/3DBAG_old/bouwlagen_features_seq_underpass
[2026-05-07T14:33:10Z INFO  tyler] tyler version: 0.4.1
[2026-05-07T14:33:10Z INFO  tyler] Created output directory "/data2/rypeters/3dt-nlup"
[2026-05-07T14:34:02Z INFO  tyler] Rebuilding cjindex sidecar at /fastssd/data/3DBAG_old/bouwlagen_features_seq_underpass/.cityjson-index.sqlite
[2026-05-07T14:45:55Z INFO  tyler::parser] Computing extent from features with CityObject types Some([BuildingPart]) and LoD filter FeatureFilter { cityobject_types: Some({"BuildingPart"}), default_lod: Highest, lods_by_type: {"BuildingPart": Exact("2.2")} }
[2026-05-07T14:48:04Z INFO  tyler::parser] Found 21555522 features of type Some([BuildingPart])
[2026-05-07T14:48:04Z INFO  tyler::parser] Ignored 0 features of type []
[2026-05-07T14:48:04Z INFO  tyler::parser] Available CityObject types after scan: {"Building", "BuildingPart"}
[2026-05-07T14:48:04Z INFO  tyler::parser] Retained CityObject types after filtering: {"BuildingPart"}
[2026-05-07T14:48:04Z INFO  tyler::parser] Available LoDs by CityObject type after filtering: {"BuildingPart": {"1.2", "1.3", "2.2"}}
[2026-05-07T14:48:04Z INFO  tyler::parser] Retained LoDs by CityObject type after filtering: {"BuildingPart": {"2.2"}}
[2026-05-07T14:48:04Z INFO  tyler::parser] Computed extent from features: POLYGON((13603.331000000006 306900.397, 277924.306 306900.397, 277924.306 612658.035, 13603.331000000006 612658.035, 13603.331000000006 306900.397))
[2026-05-07T14:48:04Z INFO  tyler::spatial_structs] Allocating dense square grid: 1024x1024 cells (~32.0 MiB base cell storage)
[2026-05-07T14:48:04Z INFO  tyler::parser] Counting vertices in grid cells
[2026-05-07T14:49:22Z INFO  tyler::parser] Indexed 21555522 of 21555522 scanned features into grid cells across 329 pages in 77.985838208s
[2026-05-07T14:49:22Z INFO  tyler] Computed grid statistics: Nr. cells with vertices: 208434; Nr. vertices: 589697159, min.: 8, max.: 102004, median: 564, mean: 2829.179303760423
[2026-05-07T14:49:22Z INFO  tyler] Building quadtree
[2026-05-07T14:49:23Z INFO  tyler] Generating 3D Tiles tileset
[2026-05-07T14:49:27Z INFO  tyler::formats::cesium3dtiles] Root ENU frame - input CRS origin: [145763.82, 459779.22, 165.31], geodetic: [5.25232626, 52.12614730, 208.61], ECEF: [3907542.21, 359212.68, 5011597.40]
[2026-05-07T14:51:01Z INFO  tyler] Geographic implicit tiling assigned 21555522 source features to 61213 content tiles (21555522 feature-tile assignments, 21555522 before ancestor deduplication)
[2026-05-07T14:51:01Z INFO  tyler] Converting to geographic implicit tiling
[2026-05-07T14:51:01Z INFO  tyler] Created output directory "/data2/rypeters/3dt-nlup/t"
[2026-05-07T14:51:01Z INFO  tyler] Converting and optimizing 61213 tiles
[2026-05-07T14:53:43Z INFO  tyler] Done
[2026-05-07T14:53:43Z INFO  tyler] Pruning tileset of 0 failed tiles
[2026-05-07T14:53:43Z INFO  tyler] Writing subtrees for implicit tiling
[2026-05-07T14:53:43Z INFO  tyler] Writing 3D Tiles tileset

runtime: 20m42s
```
