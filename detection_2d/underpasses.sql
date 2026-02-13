
-- Combine join and difference in one query
CREATE TABLE bgt.underpasses AS
WITH bgt_bag_join AS (
    SELECT
        bt.identificatiebagpnd,
        bag.identificatie,
        bt.geometrie AS bgt_geometrie,
        bag.geometrie AS bag_geometrie
    FROM
        bgt.pandactueelbestaand bt
        INNER JOIN lvbag.pandactueelbestaand bag ON bt.identificatiebagpnd = SUBSTRING(bag.identificatie FROM 15)
)
SELECT
    identificatie,
    identificatiebagpnd,
    bag_geometrie,
    bgt_geometrie,
    ST_Difference(bag_geometrie, bgt_geometrie) AS bag_minus_bgt,
    ST_Buffer(
        ST_Buffer(
            ST_Difference(bag_geometrie, bgt_geometrie),
            -0.5
        ),
        0.5
    ) AS simplified_diff
FROM
    bgt_bag_join
WHERE
    NOT ST_IsEmpty(ST_Difference(bag_geometrie, bgt_geometrie))
