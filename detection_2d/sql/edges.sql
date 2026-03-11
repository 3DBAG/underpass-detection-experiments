DROP TABLE IF EXISTS underpasses.edges;
CREATE TABLE underpasses.edges AS
WITH
    primary_edges AS (
           SELECT
        un.identificatie,
        ST_Multi(
            ST_CollectionExtract(
                ST_Intersection(
                    ST_Boundary(un.geom),
                    ST_Boundary(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03))
                ),
                2
            )
        ) AS interior_edges,
        ST_Multi(
            ST_CollectionExtract(
                ST_Difference(
                    ST_Boundary(un.geom),
                    ST_Boundary(ST_Snap(bbj.bgt_geometrie, un.geom, 0.03))
                ),
                2
            )
        ) AS exterior_edges
    FROM underpasses.geometries un
    JOIN underpasses.bag_bgt_join bbj 
        ON un.identificatie = bbj.identificatie
    WHERE NOT ST_IsEmpty(un.geom)
    ),

    adjacent_buildings AS (
        SELECT
            ba.identificatie,
            UNNEST (ba.adjacent_ids) AS adjacent_id
        FROM
            building_types.bag_adjacency_3 ba
        WHERE ba.adjacent_ids IS NOT NULL
        AND array_length(ba.adjacent_ids, 1) > 0
    ),
    adjacent_geometries AS (
        SELECT
            ab.identificatie,
            ab.adjacent_id,
            bag.geometrie AS adjacent_geom
        FROM
            adjacent_buildings ab
            JOIN lvbag.pandactueelbestaand bag 
            ON bag.identificatie = ab.adjacent_id
            WHERE NOT ST_IsEmpty(bag.geometrie)
    ),
edge_intersections AS (
SELECT
    e.identificatie,
    e.exterior_edges,
    e.interior_edges,
            ST_Multi(
            ST_CollectionExtract(
                ST_Intersection(
                    e.exterior_edges,
                    ST_Boundary(ST_Snap(ag.adjacent_geom, e.exterior_edges, 0.03))
                ),
                2
            )
        ) AS intersection_geom,
        ST_Intersects(e.exterior_edges, ag.adjacent_geom) AS has_intersection
FROM
    primary_edges e
    LEFT JOIN adjacent_geometries ag ON e.identificatie = ag.identificatie
WHERE
    NOT ST_IsEmpty (e.exterior_edges)
)
SELECT
    identificatie,
    interior_edges,
    -- Only union non-empty intersections
    ST_Union(intersection_geom) FILTER (WHERE NOT ST_IsEmpty(intersection_geom)) AS shared_edges,
    -- Non-intersection edges (exterior edges not touching adjacent buildings)
    CASE 
        WHEN ST_Union(intersection_geom) FILTER (WHERE NOT ST_IsEmpty(intersection_geom)) IS NOT NULL
        THEN ST_Multi(
            ST_CollectionExtract(
                ST_Difference(
                    exterior_edges, 
                    ST_Union(intersection_geom) FILTER (WHERE NOT ST_IsEmpty(intersection_geom))
                ), 
                2
            )
        )
        ELSE exterior_edges
    END AS exterior_edges
FROM edge_intersections
GROUP BY identificatie, exterior_edges, interior_edges
;
