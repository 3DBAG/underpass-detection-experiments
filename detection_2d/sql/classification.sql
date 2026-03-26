-- =====================================
-- CLASSIFICATION QUERY
-- =====================================
DROP TABLE IF EXISTS underpasses.classes;

CREATE TABLE underpasses.classes AS
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
SELECT
    g.*,
    CASE
        WHEN ns.exterior_edge_count = 1 
            THEN 'arcade'
        WHEN ns.exterior_edge_count > 1 
            AND ns.normal_variability >= 0.7 
            THEN 'pass-through'
        WHEN ns.exterior_edge_count > 1 
            AND ns.normal_variability < 0.7 
            THEN 'arcade but weird'
        ELSE 'undefined'
    END AS underpass_type
FROM underpasses.geometries g
    LEFT JOIN normal_stats ns ON g.underpass_id = ns.underpass_id;