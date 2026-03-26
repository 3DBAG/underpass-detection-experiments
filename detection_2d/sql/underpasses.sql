
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
-- Step 2: Initial BAG-BGT Difference Calculation, filtered through Double Buffering per Geometry
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
WHERE NOT ST_IsEmpty(raw_diff) 
AND NOT ST_IsEmpty(ST_Buffer(ST_Buffer(raw_diff, -0.2), 0.2));


-- =====================================
-- Step 3: Double Snapping
-- =====================================

DROP TABLE IF EXISTS underpasses.snapped_differences;

CREATE TABLE underpasses.snapped_differences AS
WITH joined AS (
    SELECT
        bbj.identificatie,
        bbj.bag_geometrie,
        bbj.bgt_geometrie
    FROM underpasses.bag_bgt_join bbj
    JOIN underpasses.bag_minus_bgt nsg
        ON bbj.identificatie = nsg.identificatie
),
snapped AS (
    SELECT
        identificatie,
        bag_geometrie,
        bgt_geometrie,
        ST_MakeValid(ST_Snap(bag_geometrie, bgt_geometrie, 0.03)) AS bag_snap,
        ST_MakeValid(ST_Snap(bgt_geometrie, bag_geometrie, 0.03)) AS bgt_snap
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
-- Step 4: Final Filtering through Double Buffering per Geometry
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
filtered AS (
    SELECT
        identificatie,
        single_poly
    FROM exploded
    WHERE NOT ST_IsEmpty(ST_Buffer(ST_Buffer(single_poly, -0.2), 0.2))
)
SELECT
    ROW_NUMBER() OVER () AS underpass_id,
    identificatie,
    ST_CollectionExtract(single_poly, 3) AS geom
FROM filtered;

-- Add primary key constraint on underpass_id
ALTER TABLE underpasses.geometries ADD CONSTRAINT pk_underpasses_geometries PRIMARY KEY (underpass_id);

-- Also create index on identificatie for joins
CREATE INDEX IF NOT EXISTS idx_underpasses_geometries_identificatie
    ON underpasses.geometries (identificatie);

-- Create spatial index on underpasses.geometries if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_underpasses_geometries_geom
    ON underpasses.geometries USING GIST (geom);