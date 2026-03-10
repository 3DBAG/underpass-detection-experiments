# Underpass Detection

⚠️ **Important:** Results are stored in the `underpasses` schema in baseregisters (Gilfoyle)

## Part 1: Detection and Simplification

Underpasses in Dutch building data can be detected by subtracting BAG (building registration) from BGT (topographic registration) geometries. However, since these two datasets are not perfectly aligned, the resulting difference geometries contain numerous sliver polygons. This necessitates implementing a multi-step simplification process to remove these artifacts while preserving genuine underpass areas.

Several methods were evaluated including erosion/dilation, geometric snapping, and grid-based snapping. The combination of steps described below proved most effective so far.

### Step 1: Preprocessing and Geometry Join

BGT data often contains multiple polygons for the same pand id. In this preprocessing step, we merge these BGT polygons per building and create a join table with BAG data:

```SQL
CREATE TABLE underpasses.bag_bgt_join AS
WITH filtered AS (
    SELECT
        bag.identificatie,
        bag.geometrie AS bag_geometrie,
        bt.geometrie AS bgt_geometrie
    FROM lvbag.pandactueelbestaand bag
    JOIN bgt.pandactueelbestaand bt
        ON bt.identificatiebagpnd = SUBSTRING(bag.identificatie FROM 15)
        AND bag.geometrie && bt.geometrie
)
SELECT
    identificatie,
    bag_geometrie,
    ST_UnaryUnion(ST_Collect(bgt_geometrie)) AS bgt_geometrie
FROM filtered
GROUP BY identificatie, bag_geometrie;
```

### Step 2: Initial BAG-BGT Difference Calculation

The initial underpass detection uses `ST_Difference` to subtract BGT geometries from BAG geometries. Only polygon geometries from the result are retained using `ST_CollectionExtract(raw_diff, 3)`, which filters out any resulting points or lines: 

```SQL
CREATE TABLE underpasses.bag_minus_bgt AS
WITH diff AS (
    SELECT
        identificatie,
        ST_Difference(bag_geometrie, bgt_geometrie) AS raw_diff
    FROM underpasses.bag_bgt_join
)
SELECT
    identificatie,
    ST_Multi(
        ST_CollectionExtract(raw_diff, 3)
    ) AS geom
FROM diff
WHERE NOT ST_IsEmpty(raw_diff);
```

This initial BAG-BGT operation yields **1,972,190** potential underpass polygons from approximately 2 million buildings. However, this result contains numerous sliver polygons caused by minor geometric differences between BGT and BAG datasets. These artifacts do not represent actual underpasses and require cleanup through the following processing steps.

<figure>
<img src="img/step1_sliver_polygons.png" width="600" alt="Alt text">
<figcaption>Example of sliver polygons resulting from the BAG-BGT difference</figcaption>
</figure>

### Step 3: Filtering through Double Buffering per Geometry

We implement an erosion/dilation operation (double buffering) with a threshold of **0.2 meters**. This step removes thin sliver polygons while preserving substantial underpass areas.

This operation reduces the underpass count from ~2 million to **304,897** geometries.

To avoid geometric distortion from buffering operations, we retain the original difference polygons that survive the double buffer operation (i.e., the ones that do not result in empty geometries), as shown below:


```SQL
CREATE TABLE underpasses.non_sliver_geometries AS (
    SELECT DISTINCT identificatie 
    FROM underpasses.bag_minus_bgt 
    WHERE NOT ST_IsEmpty(ST_Buffer(ST_Buffer(geom, -0.2), 0.2))
);
```
  
⚠️ **Note:** This step primarily addresses cases where BGT and BAG polygons are nearly identical, with differences consisting mainly of sliver polygons. When substantial geometric differences exist between the datasets (eg an underpass or other architectural detail), some sliver polygons may also remain within the overall geometry and require further processing in subsequent steps. 

<table>
  <tr>
    <td>
      <figure>
        <img src="img/step2_removed.png" width="200"/>
        <figcaption>These polygons are removed in this step</figcaption>
      </figure>
    </td>
    <td>
      <figure>
        <img src="img/step2_not_removed.png" width="200"/>
        <figcaption>These polygons remain</figcaption>
      </figure>
    </td>
  </tr>
</table>

### Step 4: Double Snapping

For the filtered dataset, we perform a more sophisticated difference calculation using geometric snapping to better align BAG and BGT geometries. This step uses a 0.05m snapping tolerance to handle small misalignments between datasets:

```SQL
CREATE TABLE underpasses.snapped_differences AS
WITH joined AS (
    SELECT 
        bbj.identificatie,
        bbj.bag_geometrie,
        bbj.bgt_geometrie
    FROM underpasses.bag_bgt_join bbj
    JOIN underpasses.non_sliver_geometries nsg
        ON bbj.identificatie = nsg.identificatie
),
snapped AS (
    SELECT
        identificatie,
        bag_geometrie,
        bgt_geometrie,
        ST_MakeValid(ST_Snap(bag_geometrie, bgt_geometrie, 0.05)) AS bag_snap,
        ST_MakeValid(ST_Snap(bgt_geometrie, bag_geometrie, 0.05)) AS bgt_snap
    FROM joined
),
diff AS (
    SELECT
        identificatie,
        ST_Intersection(
            ST_Difference(bag_geometrie, bgt_snap),
            ST_Difference(bag_snap, bgt_geometrie)
        ) AS raw_geom
    FROM snapped
)
SELECT
    identificatie,
    ST_Multi(ST_CollectionExtract(raw_geom, 3)) AS geom
FROM diff
WHERE NOT ST_IsEmpty(raw_geom);
```

### Step 5: Final Filtering though Double Buffering per Geometry

As a final step, we break down multipolygons into individual components and apply another erosion/dilation operation at the polygon level. This removes any remaining thin artifacts within multipolygon geometries and then reassembles the surviving polygons back into multipolygons per building:

```SQL
CREATE TABLE underpasses.geometries AS
WITH exploded AS (
    -- Split multipolygons into individual polygons
    SELECT
        identificatie,
        (ST_Dump(geom)).geom AS single_poly
    FROM underpasses.snapped_differences
),
exploded_with_id AS (
    SELECT
        ROW_NUMBER() OVER () AS poly_id,
        identificatie,
        single_poly
    FROM exploded
),
filtered AS (
    -- Remove polygons that disappear after buffering
    SELECT
        poly_id,
        identificatie
    FROM exploded_with_id
    WHERE NOT ST_IsEmpty(ST_Buffer(ST_Buffer(single_poly, -0.2), 0.2))
)
-- Merge surviving polygons back into a multipolygon per identificatie
SELECT
    e.identificatie,
    ST_Multi(ST_Collect(e.single_poly)) AS geom
FROM filtered f 
JOIN exploded_with_id e ON f.poly_id = e.poly_id
GROUP BY e.identificatie;
```

This multi-step approach effectively removes sliver polygons while preserving genuine underpass geometries, resulting in a clean dataset suitable for further analysis.


### Results:

With Blue the parts that got removed and with red the parts that got preserved:

<table>
  <tr>
    <td>
      <figure>
        <img src="img/ex1.png" width="200"/>
      </figure>
    </td>
    <td>
      <figure>
        <img src="img/ex2.png" width="200"/>
      </figure>
    </td>
  </tr>
    <tr>
    <td>
      <figure>
        <img src="img/ex3.png" width="200"/>
      </figure>
    </td>
    <td>
      <figure>
        <img src="img/ex4.png" width="200"/>
      </figure>
    </td>
  </tr>
</table>


## Part 2: Edge Classification and expansion
