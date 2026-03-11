-- Get summary of exterior edge overlaps per building
WITH
    adjacent_buildings AS (
        SELECT
            ba.identificatie,
            UNNEST (ba.adjacent_ids) AS adjacent_id
        FROM
            building_types.bag_adjacency_3 ba
    ),
    adjacent_geometries AS (
        SELECT
            ab.identificatie,
            ab.adjacent_id,
            bag.geometrie AS adjacent_geom
        FROM
            adjacent_buildings ab
            JOIN lvbag.pandactueelbestaand bag ON bag.identificatie = ab.adjacent_id
    )
SELECT
    e.identificatie,
    e.exterior_edges,
    e.interior_edges,
    ST_Union (
        ST_Multi (
            ST_CollectionExtract (
                ST_Intersection (
                    e.exterior_edges,
                    ST_Boundary (
                        ST_Snap (ag.adjacent_geom, e.exterior_edges, 0.03)
                    )
                ),
                2
            )
        )
    ) AS all_overlaps,
    COUNT(ag.adjacent_id) AS total_adjacent_buildings,
    COUNT(
        CASE
            WHEN ST_Intersects (e.exterior_edges, ag.adjacent_geom) THEN 1
        END
    ) AS overlapping_buildings
FROM
    underpasses.edges e
    JOIN adjacent_geometries ag ON e.identificatie = ag.identificatie
WHERE
    NOT ST_IsEmpty (e.exterior_edges)
GROUP BY
    e.identificatie,
    e.exterior_edges,
    e.interior_edges