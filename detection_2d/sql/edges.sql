DROP TABLE IF EXISTS underpasses.edges;

CREATE TABLE underpasses.edges AS
WITH
-- Unnest adjacent building IDs to get individual rows for each adjacent building
adjacent_buildings AS (
    SELECT
        ba.identificatie,
        UNNEST(ba.adjacent_ids) AS adjacent_id
    FROM building_types.bag_adjacency_3 ba
    WHERE ba.adjacent_ids IS NOT NULL
        AND array_length(ba.adjacent_ids, 1) > 0
),

-- Get the geometries of the adjacent buildings from BAG
adjacent_geometries AS (
    SELECT
        ab.identificatie,
        ab.adjacent_id,
        bag.geometrie AS adjacent_geom
    FROM adjacent_buildings ab
    JOIN lvbag.pandactueelbestaand bag
        ON bag.identificatie = ab.adjacent_id
    WHERE NOT ST_IsEmpty(bag.geometrie)
),

-- Find interior and exterior edges of underpasses by intersecting with the BGT polygons
primary_edges AS (
    SELECT
        un.underpass_id,
        un.identificatie,
                st_linemerge(ST_Intersection(
                    ST_ExteriorRing(un.geom),
                    CASE 
                        WHEN ST_GeometryType(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03)) = 'ST_MultiPolygon' 
                        THEN ST_Union(ARRAY(
                            SELECT ST_ExteriorRing((ST_Dump(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03))).geom)
                        ))
                        ELSE ST_ExteriorRing(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03))
                    END
            )
        ) AS interior_edges,
                st_linemerge(ST_Difference(
                    ST_ExteriorRing(un.geom),
                    CASE 
                        WHEN ST_GeometryType(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03)) = 'ST_MultiPolygon' 
                        THEN ST_Union(ARRAY(
                            SELECT ST_ExteriorRing((ST_Dump(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03))).geom)
                        ))
                        ELSE ST_ExteriorRing(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03))
                    END
            )
        ) AS exterior_edges
    FROM underpasses.geometries un
    JOIN underpasses.bag_bgt_join bbj
        ON un.identificatie = bbj.identificatie
    WHERE NOT ST_IsEmpty(un.geom)
),

-- Find intersections between exterior edges and adjacent building geometries to identify shared edges
edge_intersection_with_adjacent AS (
    SELECT
        e.underpass_id,
        e.identificatie,
        e.exterior_edges,
                st_linemerge(ST_Intersection(
                    e.exterior_edges,
                    CASE 
                        WHEN ST_GeometryType(ST_Snap(ag.adjacent_geom, e.exterior_edges, 0.03)) = 'ST_MultiPolygon' 
                        THEN ST_Union(ARRAY(
                            SELECT ST_ExteriorRing((ST_Dump(ST_Snap(ag.adjacent_geom, e.exterior_edges, 0.03))).geom)
                        ))
                        ELSE ST_ExteriorRing(ST_Snap(ag.adjacent_geom, e.exterior_edges, 0.03))
                    END
        )
        ) AS intersection_geom
    FROM primary_edges e
    LEFT JOIN adjacent_geometries ag
        ON e.identificatie = ag.identificatie
    WHERE NOT ST_IsEmpty(e.exterior_edges)
),

-- Separate shared edges (intersections) from exterior edges
edges_merged AS (
    SELECT
        underpass_id,
        identificatie,
        -- Only union non-empty intersections
        ST_Union(intersection_geom) FILTER (WHERE NOT ST_IsEmpty(intersection_geom)) AS shared_edges,
        -- Non-intersection edges (exterior edges not touching adjacent buildings)
        CASE
            WHEN ST_Union(intersection_geom) FILTER (WHERE NOT ST_IsEmpty(intersection_geom)) IS NOT NULL
            THEN 
                ST_linemerge(
                    ST_Difference(
                        exterior_edges,
                        ST_Union(intersection_geom) FILTER (WHERE NOT ST_IsEmpty(intersection_geom))
                    )
                )
            ELSE exterior_edges
        END AS exterior_edges
    FROM edge_intersection_with_adjacent
    GROUP BY underpass_id, identificatie, exterior_edges
),

-- Dump MULTILINESTRING to individual linestrings, keep LINESTRING intact
interior_segments AS (
    SELECT
        t.underpass_id,
        t.identificatie,
        'interior' AS edge_type,
        (t.dump_result).path[1] AS linestring_id,
        (t.dump_result).geom AS geom
    FROM (
        SELECT 
            underpass_id,
            identificatie,
            ST_Dump(interior_edges) AS dump_result
        FROM primary_edges as pe
        WHERE interior_edges IS NOT NULL 
            AND NOT ST_IsEmpty(interior_edges)
    ) t
),
exterior_segments AS (
    SELECT 
        t.underpass_id,
        t.identificatie,
        'exterior' AS edge_type,
        (t.dump_result).path[1] AS linestring_id,
        (t.dump_result).geom AS geom
    FROM (
        SELECT 
            underpass_id,
            identificatie,
            ST_Dump(exterior_edges) AS dump_result
        FROM edges_merged
        WHERE exterior_edges IS NOT NULL 
            AND NOT ST_IsEmpty(exterior_edges)
    ) t
),
shared_segments AS (
    SELECT 
        t.underpass_id,
        t.identificatie,
        'shared' AS edge_type,
        (t.dump_result).path[1] AS linestring_id,
        (t.dump_result).geom AS geom
    FROM (
        SELECT 
            underpass_id,
            identificatie,
            ST_Dump(shared_edges) AS dump_result
        FROM edges_merged
        WHERE shared_edges IS NOT NULL 
            AND NOT ST_IsEmpty(shared_edges)
) t
)
SELECT
    ROW_NUMBER() OVER() AS edge_id,
    underpass_id,
    identificatie,
    edge_type,
    geom
FROM (
    SELECT * FROM interior_segments
    UNION ALL
    SELECT * FROM exterior_segments
    UNION ALL
    SELECT * FROM shared_segments
) all_segments;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_edges_underpass_id
    ON underpasses.edges (underpass_id);

CREATE INDEX IF NOT EXISTS idx_edges_identificatie
    ON underpasses.edges (identificatie);

CREATE INDEX IF NOT EXISTS idx_edges_edge_type
    ON underpasses.edges (edge_type);

CREATE INDEX IF NOT EXISTS idx_edges_geom
    ON underpasses.edges USING GIST (geom);
