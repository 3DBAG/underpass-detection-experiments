DROP TABLE IF EXISTS underpasses.edges;

CREATE TABLE underpasses.edges AS (
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
);