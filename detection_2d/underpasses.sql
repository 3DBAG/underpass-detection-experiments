-- Combine join and difference in one query
CREATE TABLE bgt.underpasses AS
WITH
    bgt_bag_join AS (
        SELECT
            bt.identificatiebagpnd,
            bag.identificatie,
            bt.geometrie AS bgt_geometrie,
            bag.geometrie AS bag_geometrie
        FROM
            bgt.pandactueelbestaand bt
            INNER JOIN lvbag.pandactueelbestaand bag ON bt.identificatiebagpnd = SUBSTRING(
                bag.identificatie
                FROM
                    15
            )
    )
SELECT
    identificatie,
    identificatiebagpnd,
    bag_geometrie,
    bgt_geometrie,
    ST_Multi (
        ST_CollectionExtract (
            ST_Difference (bag_geometrie, bgt_geometrie) AS bag_minus_bgt
        ),
        3
    ),
    ST_Multi (
        ST_CollectionExtract (
            ST_Intersection (
                ST_difference (
                    St_makevalid (ST_Snap (bag_geometrie, bgt_geometrie, 0.2)),
                    bgt_geometrie
                ),
                ST_difference (
                    bag_geometrie,
                    St_makevalid (ST_Snap (bgt_geometrie, bag_geometrie, 0.2))
                )
            ),
            3
        )
    ) AS simplified_diff
FROM
    bgt_bag_join
WHERE
    NOT ST_IsEmpty (ST_Difference (bag_geometrie, bgt_geometrie));

CREATE TABLE bgt.undepass_edges as (
    select
        identificatie,
        simplified_diff,
        ST_Intersection (
            ST_Boundary (simplified_diff),
            ST_Boundary (bgt_geometrie)
        ) AS interior_edges,
        st_difference (
            ST_Boundary (simplified_diff),
            ST_Boundary (bgt_geometrie)
        ) AS exterior_edges
    FROM
        bgt.underpasses un
    where
        NOT ST_IsEmpty (simplified_diff);
)
