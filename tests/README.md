## Streetlidar run results
took around 59 min with 
```
RAYON_NUM_THREADS=3 python run_streetlidar_heights.py --within-index-extent     --grid-cell-size 500     --batch-workers 16     --pip-workers 5     --height-workers 1     --laz-backend lazrs-parallel     --decompression xyz
```


## add_underpasses run results

```
> ADD_UNDERPASS=/home/rypeters/git/underpass-detection-experiments/modelling_3d/result/bin/add_underpass ./run_add_underpass.sh
input:       /fastssd/data/3DBAG/bouwlagen_features_seq (8962 files)
output:      /fastssd/data/3DBAG/bouwlagen_features_seq_underpass
logs:        /fastssd/data/3DBAG/logs_add_underpass
executable:  /home/rypeters/git/underpass-detection-experiments/modelling_3d/result/bin/add_underpass
jobs:        32
clean first: 1
0% 25:8937=1h29m50s /fastssd/data/3DBAG/bouwlagen_features_seq/10-912-712.city.jsonl     Installed 1 package in 44ms
100% 8962:0=0s /fastssd/data/3DBAG/bouwlagen_features_seq/9-132-260.city.jsonl
wrote 8962 rows to /fastssd/data/3DBAG/logs_add_underpass/results.csv

runtime: 57m12s
```

## tyler run

```
 RAYON_NUM_THREADS=40 RUST_LOG=info /home/rypeters/git/tyler/target/release/tyler --3dtiles-implicit --grid-minz=-15 --output /data2/rypeters/3dt-nlup --include-parent-attributes --lod-building-part "2.2" --object-type BuildingPart /fastssd/data/3DBAG_old/bouwlagen_features_seq_underpass
```
