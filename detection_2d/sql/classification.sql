
-- =====================================
-- CLASSIFICATION QUERY
-- =====================================

-- Classification driven by geometries and edge analysis
DROP TABLE IF EXISTS underpasses.classes;

CREATE TABLE underpasses.classes AS
WITH edge_counts AS (
    SELECT
        underpass_id,
        COUNT(*) FILTER (WHERE edge_type = 'exterior') AS exterior_edge_count
    FROM underpasses.edges
    GROUP BY underpass_id
)
SELECT
    g.*,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM underpasses.test_roads r
            WHERE r.geom && g.geom                -- helps use the GiST index on roads
                AND ST_Intersects(g.geom, r.geom)   -- exact check
                AND r.class IN ('primary', 'secondary', 'tertiary', 'residential', 'motorway', 'service')
            LIMIT 1
        ) THEN 'car_accessible' 
        WHEN EXISTS (
            SELECT 1
            FROM underpasses.test_roads r
            WHERE r.geom && g.geom                -- helps use the GiST index on roads
                AND ST_Intersects(g.geom, r.geom)   -- exact check
                AND r.class IN ('steps', 'cycleway','pedestrian', 'path', 'bridleway', 'footway', 'trunk', 'track')
            LIMIT 1
        ) THEN 'pedestrian_accessible' 
        ELSE 'other' 
    END AS accessibility,
    
    CASE 
        WHEN ec.exterior_edge_count = 1 THEN 'arcade'
        WHEN ec.exterior_edge_count > 1 THEN 'pass-through'
        ELSE 'undefined'
    END AS underpass_type
    
FROM underpasses.geometries g
LEFT JOIN edge_counts ec ON g.underpass_id = ec.underpass_id;

