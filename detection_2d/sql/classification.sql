-- =====================================
-- ROADS TABLE CREATION
-- =====================================

CREATE TABLE underpasses.roads AS
SELECT
    osm.id,
    osm.class,
    osm.subclass,
    ST_Transform(osm.wkb_geometry, 28992) AS geom
FROM underpasses.osm_segments AS osm
WHERE osm.subtype = 'road';

-- Create spatial index on underpasses.roads if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_roads_geom
    ON underpasses.roads USING GIST (geom);

-- =====================================
-- CLASSIFICATION QUERY
-- =====================================

-- classification driven by geometries (outer)
DROP TABLE IF EXISTS underpasses.classes;
CREATE TABLE underpasses.classes AS
SELECT
  un.identificatie,
  CASE
    WHEN EXISTS (
      SELECT 1
      FROM underpasses.roads r
      WHERE r.geom && un.geom                -- helps use the GiST index on roads
        AND ST_Intersects(un.geom, r.geom)   -- exact check
      LIMIT 1
    ) THEN 'car_accessible' ELSE 'other' END AS class
FROM underpasses.geometries un;

-- Refresh planner statistics to help the planner choose spatial indexes
ANALYZE underpasses.geometries;
ANALYZE underpasses.roads;
