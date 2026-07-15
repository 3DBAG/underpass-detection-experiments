## Rough val3dity error comparison

baseline:
```
> ./summarize_val3dity_reports.py /data2/rypeters/ams-3dbag-ref-20250903/
reports: 247
objects: 288617
objects with errors: 6225 (2.16%)
error occurrences: 20870

  code  occurrences    objects  objects_% of_error_objects_%  description
------ ------------ ---------- ---------- ------------------  -----------
   102        12989       4261      1.48%             68.45%  CONSECUTIVE_POINTS_SAME
   104         1031        658      0.23%             10.57%  RING_SELF_INTERSECTION
   201            5          4      0.00%              0.06%  INTERSECTION_RINGS
   203          414        297      0.10%              4.77%  NON_PLANAR_POLYGON_DISTANCE_PLANE
   204          153        143      0.05%              2.30%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
   205            9          3      0.00%              0.05%  POLYGON_INTERIOR_DISCONNECTED
   302         1010        529      0.18%              8.50%  SHELL_NOT_CLOSED
   303         4265        898      0.31%             14.43%  NON_MANIFOLD_CASE
   305            1          1      0.00%              0.02%  MULTIPLE_CONNECTED_COMPONENTS
   306          864         76      0.03%              1.22%  SHELL_SELF_INTERSECTION
   307          125        115      0.04%              1.85%  POLYGON_WRONG_ORIENTATION
   405            4          2      0.00%              0.03%  WRONG_ORIENTATION_SHELL
```

Current results:
```
> ./summarize_val3dity_reports.py /data2/rypeters/ams-run-06-30-rf/seq
reports: 210
objects: 163538
objects with errors: 334 (0.20%)
error occurrences: 639

  code  occurrences    objects  objects_% of_error_objects_%  description
------ ------------ ---------- ---------- ------------------  -----------
   102          232        109      0.07%             32.63%  CONSECUTIVE_POINTS_SAME
   104           28         19      0.01%              5.69%  RING_SELF_INTERSECTION
   201            1          1      0.00%              0.30%  INTERSECTION_RINGS
   203            4          1      0.00%              0.30%  NON_PLANAR_POLYGON_DISTANCE_PLANE
   204          168        156      0.10%             46.71%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
   301            3          3      0.00%              0.90%  TOO_FEW_POLYGONS
   302           30         14      0.01%              4.19%  SHELL_NOT_CLOSED
   303           90         26      0.02%              7.78%  NON_MANIFOLD_CASE
   305            1          1      0.00%              0.30%  MULTIPLE_CONNECTED_COMPONENTS
   306           78          9      0.01%              2.69%  SHELL_SELF_INTERSECTION
   307            2          2      0.00%              0.60%  POLYGON_WRONG_ORIENTATION
   405            2          1      0.00%              0.30%  WRONG_ORIENTATION_SHELL
```

```
> ./summarize_val3dity_reports.py /data2/rypeters/ams-run-06-30-rf/seq_underpasses
reports: 210
objects: 163538
objects with errors: 13508 (8.26%)
error occurrences: 178060

  code  occurrences    objects  objects_% of_error_objects_%  description
------ ------------ ---------- ---------- ------------------  -----------
   102        35864       7460      4.56%             55.23%  CONSECUTIVE_POINTS_SAME
   104         4617       2072      1.27%             15.34%  RING_SELF_INTERSECTION
   201            7          7      0.00%              0.05%  INTERSECTION_RINGS
   203         2129       1599      0.98%             11.84%  NON_PLANAR_POLYGON_DISTANCE_PLANE
   204          148        137      0.08%              1.01%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
   206            3          3      0.00%              0.02%  INNER_RING_OUTSIDE
   301            3          3      0.00%              0.02%  TOO_FEW_POLYGONS
   302           30         14      0.01%              0.10%  SHELL_NOT_CLOSED
   303        52816       4892      2.99%             36.22%  NON_MANIFOLD_CASE
   305            1          1      0.00%              0.01%  MULTIPLE_CONNECTED_COMPONENTS
   306           67          7      0.00%              0.05%  SHELL_SELF_INTERSECTION
   307        82373       4912      3.00%             36.36%  POLYGON_WRONG_ORIENTATION
   405            2          1      0.00%              0.01%  WRONG_ORIENTATION_SHELL
   ```

   ```
   > ./val3dity_tools.py summarize /data2/rypeters/ams-run-06-30-rf/seq_underpasses_pmp/
   reports: 210
   objects: 163538
   objects with errors: 13413 (8.20%)
   error occurrences: 205612
   
     code  occurrences    objects  objects_% of_error_objects_%  description
   ------ ------------ ---------- ---------- ------------------  -----------
      102       155910      11553      7.06%             86.13%  CONSECUTIVE_POINTS_SAME
      104         1540       1277      0.78%              9.52%  RING_SELF_INTERSECTION
      201            5          5      0.00%              0.04%  INTERSECTION_RINGS
      203          248        201      0.12%              1.50%  NON_PLANAR_POLYGON_DISTANCE_PLANE
      204          358        318      0.19%              2.37%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
      208            1          1      0.00%              0.01%  ORIENTATION_RINGS_SAME
      301            3          3      0.00%              0.02%  TOO_FEW_POLYGONS
      302           30         14      0.01%              0.10%  SHELL_NOT_CLOSED
      303        18286       1419      0.87%             10.58%  NON_MANIFOLD_CASE
      305            1          1      0.00%              0.01%  MULTIPLE_CONNECTED_COMPONENTS
      306           67          7      0.00%              0.05%  SHELL_SELF_INTERSECTION
      307        29161       1402      0.86%             10.45%  POLYGON_WRONG_ORIENTATION
      405            2          1      0.00%              0.01%  WRONG_ORIENTATION_SHELL
```

after normal orientation fix:

```
> ./val3dity_tools.py summarise /data2/rypeters/ams-run-07-07-rf/seq_underpasses_manifold/
reports: 210
objects: 163538
objects with errors: 8785 (5.37%)
error occurrences: 46023

  code  occurrences    objects  objects_% of_error_objects_%  description
------ ------------ ---------- ---------- ------------------  -----------
   102        36672       7497      4.58%             85.34%  CONSECUTIVE_POINTS_SAME
   104         5051       2154      1.32%             24.52%  RING_SELF_INTERSECTION
   201            6          6      0.00%              0.07%  INTERSECTION_RINGS
   203         2150       1607      0.98%             18.29%  NON_PLANAR_POLYGON_DISTANCE_PLANE
   204          147        136      0.08%              1.55%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
   206            2          2      0.00%              0.02%  INNER_RING_OUTSIDE
   301            3          3      0.00%              0.03%  TOO_FEW_POLYGONS
   302           30         14      0.01%              0.16%  SHELL_NOT_CLOSED
   303          244         63      0.04%              0.72%  NON_MANIFOLD_CASE
   305           14         14      0.01%              0.16%  MULTIPLE_CONNECTED_COMPONENTS
   306         1633        126      0.08%              1.43%  SHELL_SELF_INTERSECTION
   307           69         20      0.01%              0.23%  POLYGON_WRONG_ORIENTATION
   405            2          1      0.00%              0.01%  WRONG_ORIENTATION_SHELL
```

```
> ./val3dity_tools.py summarise /data2/rypeters/ams-run-07-07-rf/seq_underpasses_pmp/
reports: 210
objects: 163538
objects with errors: 12075 (7.38%)
error occurrences: 166895

  code  occurrences    objects  objects_% of_error_objects_%  description
------ ------------ ---------- ---------- ------------------  -----------
   102       164312      11624      7.11%             96.27%  CONSECUTIVE_POINTS_SAME
   104         1779       1410      0.86%             11.68%  RING_SELF_INTERSECTION
   201            4          4      0.00%              0.03%  INTERSECTION_RINGS
   203          254        202      0.12%              1.67%  NON_PLANAR_POLYGON_DISTANCE_PLANE
   204          345        307      0.19%              2.54%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
   208            1          1      0.00%              0.01%  ORIENTATION_RINGS_SAME
   301            3          3      0.00%              0.02%  TOO_FEW_POLYGONS
   302           30         14      0.01%              0.12%  SHELL_NOT_CLOSED
   303           90         26      0.02%              0.22%  NON_MANIFOLD_CASE
   305            5          5      0.00%              0.04%  MULTIPLE_CONNECTED_COMPONENTS
   306           67          7      0.00%              0.06%  SHELL_SELF_INTERSECTION
   307            3          3      0.00%              0.02%  POLYGON_WRONG_ORIENTATION
   405            2          1      0.00%              0.01%  WRONG_ORIENTATION_SHELL
```

After add mesh simplification and fixes to face merging (https://github.com/3DBAG/underpass-detection-experiments/issues/11#issuecomment-4939222880):

```
./val3dity_tools.py summarise /data2/rypeters/ams-run-07-14-rf/seq_underpasses_manifold/
reports: 210
objects: 163538
objects with errors: 2943 (1.80%)
error occurrences: 7395

  code  occurrences    objects  objects_% of_error_objects_%  description
------ ------------ ---------- ---------- ------------------  -----------
   102         6169       2379      1.45%             80.84%  CONSECUTIVE_POINTS_SAME
   104          126        116      0.07%              3.94%  RING_SELF_INTERSECTION
   201            2          2      0.00%              0.07%  INTERSECTION_RINGS
   203          172        163      0.10%              5.54%  NON_PLANAR_POLYGON_DISTANCE_PLANE
   204          252        228      0.14%              7.75%  NON_PLANAR_POLYGON_NORMALS_DEVIATION
   301            3          3      0.00%              0.10%  TOO_FEW_POLYGONS
   302           31         15      0.01%              0.51%  SHELL_NOT_CLOSED
   303          214         58      0.04%              1.97%  NON_MANIFOLD_CASE
   305           39         39      0.02%              1.33%  MULTIPLE_CONNECTED_COMPONENTS
   306          285         43      0.03%              1.46%  SHELL_SELF_INTERSECTION
   307          100         29      0.02%              0.99%  POLYGON_WRONG_ORIENTATION
   405            2          1      0.00%              0.03%  WRONG_ORIENTATION_SHELL
```
