
-- *************************************
-- UNDERPASS DETECTION SQL PIPELINE
-- *************************************

-- =====================================
-- Step 1: Preprocessing and Geometry Join: 
-- Join BAG and BGT geometries and merge BGT geometries per pand
-- =====================================

DROP TABLE IF EXISTS underpasses.bag_bgt_join;

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


-- =====================================
-- Step 2: Initial BAG-BGT Difference Calculation
-- =====================================

DROP TABLE IF EXISTS underpasses.bag_minus_bgt;

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


-- =====================================
-- Step 3: Filtering through Double Buffering per Geometry
-- =====================================

DROP TABLE IF EXISTS underpasses.non_sliver_geometries;

CREATE TABLE underpasses.non_sliver_geometries AS (
    SELECT DISTINCT identificatie 
    FROM underpasses.bag_minus_bgt 
    WHERE NOT ST_IsEmpty(ST_Buffer(ST_Buffer(geom, -0.2), 0.2))
);


-- =====================================
-- Step 4: Double Snapping
-- =====================================

DROP TABLE IF EXISTS underpasses.snapped_differences;

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


-- =====================================
-- Step 5: Final Filtering though Double Buffering per Geometry
-- =====================================

DROP TABLE IF EXISTS underpasses.geometries;

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
        ROW_NUMBER() OVER () AS poly_id,  -- Unique ID for each polygon
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