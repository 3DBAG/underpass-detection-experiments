## Streetlidar run results
took around 52 min with 
```
RAYON_NUM_THREADS=3 python run_streetlidar_heights.py --within-index-extent     --grid-cell-size 500     --batch-workers 16     --pip-workers 5     --height-workers 1     --laz-backend lazrs-parallel     --decompression xyz
```
### Run Coverage

| Metric | Count |
|---|---:|
| Total rows | 365,723 |
| Processed rows | 66,752 |
| Streetlidar success | 17,784 |
| Fallback rows | 48,968 |
| Still placeholder/null | 298,971 |

The 298,971 unprocessed/placeholder rows all have h_underpass = 2.5 with h_underpass_source/status still null.

### Status Counts

| source | status | rows | h median | point median |
|---|---|---:|---:|---:|
| null | null | 298,971 | 3.5 | null |
| fallback | no_laz_tiles | 45,885 | 2.5 | 0 |
| streetlidar | success | 17,784 | 2.930 | 32,368 |
| fallback | no_points | 1,637 | 2.5 | 0 |
| fallback | too_few_points | 1,338 | 2.5 | 19 |
| fallback | too_many_points | 104 | 2.5 | 5,099,548 |
| fallback | failed | 2 | 2.5 | 105,071 |
| fallback | invalid_geometry | 2 | 2.5 | 0 |

### Common Errors

| status | error group | rows |
|---|---|---:|
| no_laz_tiles | No street-lidar tiles intersect polygon | 45,885 |
| no_points | No points inside polygon | 1,637 |
| too_few_points | Too few points inside polygon <100 | 1,338 |
| too_many_points | Selected more than 5,000,000 points | 104 |
| failed | Fewer than two usable Z peaks found | 2 |
| invalid_geometry | failed to create prepared polygon | 2 |

### Point Count Histogram

| point count | rows | success | other |
|---|---:|---:|---:|
| null | 298,971 | 0 | 298,971 |
| 0 | 47,524 | 0 | 47,524 |
| 1-99 | 1,338 | 0 | 1,338 |
| 100-999 | 1,335 | 1,335 | 0 |
| 1k-10k | 2,884 | 2,884 | 0 |
| 10k-100k | 9,339 | 9,338 | 1 |
| 100k-1M | 3,770 | 3,769 | 1 |
| 1M-5M | 458 | 458 | 0 |
| >=5M | 104 | 0 | 104 |

### Success-only point count quantiles

| Quantile | Value |
|---|---:|
| min | 100 |
| p01 | 151 |
| p05 | 527 |
| p10 | 1,768 |
| p25 | 11,038 |
| median | 32,368 |
| p75 | 93,079 |
| p90 | 294,275 |
| p95 | 581,148 |
| p99 | 1,912,377 |
| max | 4,980,052 |
| avg | 135,158 |

### Height Histogram

This includes fallback 2.5 and placeholder 3.5.

| h_underpass | rows | success | other |
|---|---:|---:|---:|
| 0-1 | 1,120 | 1,120 | 0 |
| 1-1.5 | 943 | 943 | 0 |
| 1.5-2 | 1,001 | 1,001 | 0 |
| 2-2.5 | 2,234 | 2,234 | 0 |
| =2.5 | 48,968 | 0 | 48,968 |
| 2.5-3 | 4,026 | 4,026 | 0 |
| 3-3.5 | 2,127 | 2,127 | 0 |
| =3.5 | 298,971 | 0 | 298,971 |
| 3.5-4 | 1,391 | 1,391 | 0 |
| 4-5 | 1,815 | 1,815 | 0 |
| 5-10 | 2,809 | 2,809 | 0 |
| >=10 | 318 | 318 | 0 |

### Success-only h_underpass quantiles

| Quantile | Value |
|---|---:|
| min | 0.003 |
| p01 | 0.339 |
| p05 | 0.873 |
| p10 | 1.355 |
| p25 | 2.394 |
| median | 2.930 |
| p75 | 4.235 |
| p90 | 5.993 |
| p95 | 7.632 |
| p99 | 11.290 |
| max | 24.186 |
| avg | 3.485 |


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
