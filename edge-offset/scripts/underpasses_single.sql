/* Modified from detection_2d/sql/underpasses.sql so that we have single polygons with unique ids, instead of multipolygons per BAG pand*/

-- =====================================
-- Step 5: Final Filtering though Double Buffering per Geometry
-- =====================================

DROP TABLE IF EXISTS underpasses.geometries;

CREATE TABLE underpasses.geometries AS
WITH exploded AS (
    -- Split multipolygons into individual polygons
    SELECT identificatie, (ST_Dump(geom)).geom AS single_poly
    FROM underpasses.snapped_differences
    -- Test area for project meeting
    WHERE geom &&
          st_geomfromewkt('SRID=28992;POLYGON ((122093.33100000000558794 485890.39699999999720603, 122593.33100000000558794 485890.39699999999720603, 122593.33100000000558794 486390.39699999999720603, 122093.33100000000558794 486390.39699999999720603, 122093.33100000000558794 485890.39699999999720603))')
       OR geom &&
          st_geomfromewkt('SRID=28992; POLYGON ((124593.33100000000558794 488890.39699999999720603, 125593.33100000000558794 488890.39699999999720603, 125593.33100000000558794 489890.39699999999720603, 124593.33100000000558794 489890.39699999999720603, 124593.33100000000558794 488890.39699999999720603))'))
   , exploded_with_id
    AS (SELECT ROW_NUMBER() OVER () AS underpass_id -- Unique ID for each polygon
             , identificatie
             , single_poly
        FROM exploded)
   , filtered AS (
    -- Remove polygons that disappear after buffering
    SELECT underpass_id, identificatie
    FROM exploded_with_id
    WHERE NOT ST_IsEmpty(ST_Buffer(ST_Buffer(single_poly, -0.2), 0.2)))
-- Merge surviving polygons back into a multipolygon per identificatie
SELECT e.identificatie, e.underpass_id, e.single_poly AS geom
FROM filtered f
         JOIN exploded_with_id e ON f.underpass_id = e.underpass_id;