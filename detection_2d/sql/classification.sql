-- =====================================
-- CLASSIFICATION QUERY
-- =====================================

DROP TABLE IF EXISTS underpasses.roads;

CREATE TABLE underpasses.roads AS
SELECT 
    id, 
    class, 
    st_transform(wkb_geometry, 28992) AS geom 
FROM underpasses.osm_segments os 
WHERE subtype = 'road' 
    AND os.class IN (
        'primary', 'secondary', 'tertiary', 'residential', 
        'motorway', 'service', 'living_street', 'trunk'
    );

-- Add spatial index for geometric operations
CREATE INDEX idx_roads_geom 
    ON underpasses.roads USING GIST (geom);

-- Add B-tree index for class filtering
CREATE INDEX idx_roads_class 
    ON underpasses.roads (class);

-- Add primary key
ALTER TABLE underpasses.roads 
    ADD PRIMARY KEY (id);


-- Add car_accessible column if it doesn't exist
ALTER TABLE underpasses.geometries 
ADD COLUMN IF NOT EXISTS car_accessible BOOLEAN;

-- Update the column with the accessibility classification based on intersection with roads
UPDATE underpasses.geometries g
SET car_accessible = CASE
    WHEN EXISTS (
        SELECT 1
        FROM underpasses.roads r
        WHERE r.geom && g.geom
            AND ST_Intersects(g.geom, r.geom)
        LIMIT 1
    ) THEN TRUE
    ELSE FALSE
END;

-- Add index on the new accessibility column
CREATE INDEX IF NOT EXISTS idx_geometries_car_accessible 
    ON underpasses.geometries (car_accessible);


-- Add pass_through column if it doesn't exist
ALTER TABLE underpasses.geometries 
ADD COLUMN IF NOT EXISTS pass_through BOOLEAN;

-- Update the column with the underpass type classification
WITH detailed_normals AS (
    SELECT
        underpass_id,
        COS(
            ST_Azimuth(ST_StartPoint(geom), ST_EndPoint(geom)) + (PI() / 2)
        ) AS normal_x,
        SIN(
            ST_Azimuth(ST_StartPoint(geom), ST_EndPoint(geom)) + (PI() / 2)
        ) AS normal_y
    FROM underpasses.edges
    WHERE edge_type = 'exterior'
        AND ST_GeometryType(geom) = 'ST_LineString'
),
normal_stats AS (
    SELECT
        underpass_id,
        COUNT(*) AS exterior_edge_count,
        SQRT(
            POWER(STDDEV(normal_x), 2) + POWER(STDDEV(normal_y), 2)
        ) AS normal_variability
    FROM detailed_normals
    GROUP BY underpass_id
)
UPDATE underpasses.geometries 
SET pass_through = CASE
    WHEN ns.exterior_edge_count = 1 
        THEN FALSE
    WHEN ns.exterior_edge_count > 1 
        AND ns.normal_variability >= 0.7 
        THEN TRUE
    WHEN ns.exterior_edge_count > 1 
        AND ns.normal_variability < 0.7 
        THEN FALSE
    ELSE FALSE
END
FROM normal_stats ns 
WHERE underpasses.geometries.underpass_id = ns.underpass_id;

-- Add index on the new pass_through column
CREATE INDEX IF NOT EXISTS idx_geometries_pass_through 
    ON underpasses.geometries (pass_through);


