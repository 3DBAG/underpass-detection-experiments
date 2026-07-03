#!/usr/bin/env python3
"""
Detect underpass geometries by comparing BAG and BGT building polygons.

Implements the 4-step pipeline from detection_2d/sql/underpasses.sql:
  1. Bag-BGT join (SQL)
  2. Bag minus BGT difference + double buffer filtering (Python/Shapely)
  3. Double snapping + intersection of differences (Python/Shapely)
  4. Final filtering + ID assignment (Python/Shapely)
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import environ
from pathlib import Path
import sys
import time
from typing import Any

from psycopg import connect
from shapely import from_wkb
from shapely.geometry import Polygon

from underpass_detection_2d.geometry_ops import (
    double_buffer_filter,
    dump_multi_to_polygons,
)
from underpass_detection_2d.pipeline import (
    compute_bag_minus_bgt,
    compute_snapped_differences,
)
from underpass_detection_2d.postgis import (
    create_bag_bgt_join_table,
    create_bag_minus_bgt_table,
    create_geometries_table,
    create_snapped_differences_table,
    get_bag_bgt_join_count,
    get_bag_minus_bgt_count,
    get_snapped_differences_count,
    load_bag_bgt_join_chunk,
    load_bag_minus_bgt_chunk,
    load_snapped_differences_chunk,
    write_bag_minus_bgt_rows,
    write_geometries_rows,
    write_snapped_differences_rows,
)

ENV_PATH = Path(".env")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                environ.setdefault(key.strip(), value.strip())


def _require_env(key: str) -> str:
    value = environ.get(key)
    if not value:
        raise ValueError(f"{key} environment variable must be set")
    return value


def _run_step1_bag_bgt_join(
    db_params: dict[str, Any],
    bag_bgt_join_table: str,
) -> None:
    """Step 1: BAG-BGT join using SQL (most efficient for large-table JOIN)."""
    print("=" * 60)
    print("Step 1: BAG-BGT Join")
    print("=" * 60)

    if "." in bag_bgt_join_table:
        schema, table = bag_bgt_join_table.split(".", 1)
    else:
        schema = "public"
        table = bag_bgt_join_table

    t0 = time.time()

    with connect(**db_params) as conn:
        create_bag_bgt_join_table(conn, bag_bgt_join_table)

    with connect(**db_params) as conn:
        query = f"""
            INSERT INTO {schema}.{table} (identificatie, bag_geometrie, bgt_geometrie)
            WITH filtered AS (
                SELECT
                    bag.identificatie,
                    bag.geometrie AS bag_geometrie,
                    bt.geometrie AS bgt_geometrie
                FROM lvbag.pandactueelbestaand bag
                JOIN bgt.pandactueelbestaand bt
                    ON bt.identificatiebagpnd = SUBSTRING(bag.identificatie FROM 15)
                    AND bag.geometrie && bt.geometrie
            )
            SELECT
                identificatie,
                bag_geometrie,
                ST_UnaryUnion(ST_Collect(bgt_geometrie)) AS bgt_geometrie
            FROM filtered
            GROUP BY identificatie, bag_geometrie
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
        conn.commit()

        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        count = cursor.fetchone()[0]

    t1 = time.time()
    print(f"  Created {count:,} bag_bgt_join records in {t1 - t0:.2f}s")
    print()


def _process_step2_chunk(
    chunk: list[tuple[str, Any, Any]],
    chunk_num: int,
    total_chunks: int,
    buffer_distance: float,
    bag_minus_bgt_table: str,
    db_params: dict[str, Any],
) -> dict[str, int]:
    successful = 0
    skipped = 0

    print(f"  Chunk {chunk_num}/{total_chunks}: Processing {len(chunk)} records...")

    results = []
    for identificatie, bag_geom, bgt_geom in chunk:
        try:
            diff = compute_bag_minus_bgt(bag_geom, bgt_geom, buffer_distance)
            if diff.is_empty:
                skipped += 1
                continue
            results.append((identificatie, diff))
            successful += 1
        except Exception as e:
            print(f"    Failed {identificatie}: {e}")
            skipped += 1

    if results:
        with connect(**db_params) as conn:
            write_bag_minus_bgt_rows(conn, results, bag_minus_bgt_table)
            conn.commit()

    print(f"    Chunk {chunk_num}: {successful} written, {skipped} skipped")
    return {"successful": successful, "skipped": skipped}


def _process_step3_chunk(
    offset: int,
    limit: int,
    chunk_num: int,
    total_chunks: int,
    snap_tolerance: float,
    snapped_diff_table: str,
    bag_bgt_join_table: str,
    bag_minus_bgt_table: str,
    db_params: dict[str, Any],
) -> dict[str, int]:
    if "." in bag_bgt_join_table:
        join_schema, join_table = bag_bgt_join_table.split(".", 1)
    else:
        join_schema = "public"
        join_table = bag_bgt_join_table

    with connect(**db_params) as conn:
        chunk = load_bag_minus_bgt_chunk(
            conn, offset, limit, bag_minus_bgt_table
        )

        if not chunk:
            return {"successful": 0, "skipped": 0}

        identificaties = [row[0] for row in chunk]
        cursor = conn.cursor()
        cursor.execute(
            f"""
                SELECT identificatie::text,
                       ST_AsBinary(bag_geometrie),
                       ST_AsBinary(bgt_geometrie)
                FROM {join_schema}.{join_table}
                WHERE identificatie = ANY(%s::text[])
            """,
            (identificaties,),
        )
        join_data = {
            row[0]: (from_wkb(row[1]), from_wkb(row[2]))
            for row in cursor.fetchall()
        }

    print(f"  Chunk {chunk_num}/{total_chunks}: Processing {len(chunk)} records...")

    successful = 0
    no_join = 0
    filtered = 0
    results = []
    for identificatie, diff_geom in chunk:
        if identificatie not in join_data:
            no_join += 1
            continue
        bag_geom, bgt_geom = join_data[identificatie]
        try:
            snapped = compute_snapped_differences(
                bag_geom, bgt_geom, snap_tolerance
            )
            if snapped.is_empty:
                filtered += 1
                continue
            results.append((identificatie, snapped))
            successful += 1
        except Exception as e:
            print(f"    Failed {identificatie}: {e}")
            filtered += 1

    if results:
        with connect(**db_params) as conn:
            write_snapped_differences_rows(conn, results, snapped_diff_table)
            conn.commit()

    print(f"    Chunk {chunk_num}: {successful} written, {no_join} missing join, {filtered} filtered")
    return {"successful": successful, "no_join": no_join, "filtered": filtered}


def _process_step4_chunk(
    offset: int,
    limit: int,
    chunk_num: int,
    total_chunks: int,
    buffer_distance: float,
    snapped_diff_table: str,
    db_params: dict[str, Any],
) -> tuple[int, list[tuple[str, Polygon]]]:
    with connect(**db_params) as conn:
        rows = load_snapped_differences_chunk(
            conn, offset, limit, snapped_diff_table
        )

    polygons: list[tuple[str, Polygon]] = []
    for identificatie, geom in rows:
        if geom is None or geom.is_empty:
            continue
        for poly in dump_multi_to_polygons(geom):
            if double_buffer_filter(poly, buffer_distance).is_empty:
                continue
            polygons.append((identificatie, poly))

    print(f"  Chunk {chunk_num}/{total_chunks}: "
          f"{len(polygons)} polygons from {len(rows)} records")
    return chunk_num, polygons


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect underpass geometries by comparing BAG and BGT building polygons."
    )
    parser.add_argument(
        "--skip-step1",
        action="store_true",
        help="Skip Step 1 (BAG-BGT join). Use when bag_bgt_join table already exists.",
    )
    parser.add_argument(
        "--skip-step2",
        action="store_true",
        help="Skip Step 2 (bag minus BGT difference). Use when bag_minus_bgt table already exists.",
    )
    parser.add_argument(
        "--skip-step3",
        action="store_true",
        help="Skip Step 3 (double snapping). Use when snapped_differences table already exists.",
    )
    return parser


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        parser = _build_parser()
        args = parser.parse_args()

    _load_dotenv(ENV_PATH)

    max_workers = int(environ.get("UNDERPASS_DETECTION_2D_MAX_WORKERS", "4"))
    chunk_size = int(environ.get("UNDERPASS_DETECTION_2D_CHUNK_SIZE", "1000"))
    snap_tolerance = float(
        environ.get("UNDERPASS_DETECTION_2D_SNAP_TOLERANCE", "0.01")
    )
    buffer_distance = float(
        environ.get("UNDERPASS_DETECTION_2D_BUFFER_DISTANCE", "0.2")
    )

    bag_bgt_join_table = environ.get(
        "UNDERPASS_DETECTION_2D_BAG_BGT_JOIN_TABLE", "underpasses.bag_bgt_join"
    )
    bag_minus_bgt_table = environ.get(
        "UNDERPASS_DETECTION_2D_BAG_MINUS_BGT_TABLE", "underpasses.bag_minus_bgt"
    )
    snapped_diff_table = environ.get(
        "UNDERPASS_DETECTION_2D_SNAPPED_DIFFERENCES_TABLE",
        "underpasses.snapped_differences",
    )
    geometries_table = environ.get(
        "UNDERPASS_DETECTION_2D_GEOMETRIES_TABLE", "underpasses.geometries"
    )

    db_params = {
        "host": _require_env("UNDERPASS_DETECTION_2D_DB_HOST"),
        "port": int(_require_env("UNDERPASS_DETECTION_2D_DB_PORT")),
        "dbname": _require_env("UNDERPASS_DETECTION_2D_DB_NAME"),
        "user": _require_env("UNDERPASS_DETECTION_2D_DB_USER"),
        "password": environ.get("UNDERPASS_DETECTION_2D_DB_PASSWORD", ""),
    }

    print("=" * 80)
    print("Underpass Detection 2D Pipeline")
    print("=" * 80)
    print(f"Max workers:      {max_workers}")
    print(f"Chunk size:       {chunk_size}")
    print(f"Snap tolerance:   {snap_tolerance}")
    print(f"Buffer distance:  {buffer_distance}")
    print(f"Bag-BGT join:     {bag_bgt_join_table}")
    print(f"Bag minus BGT:    {bag_minus_bgt_table}")
    print(f"Snapped diffs:    {snapped_diff_table}")
    print(f"Geometries:       {geometries_table}")
    if args.skip_step1:
        print("SKIP step 1:      yes")
    if args.skip_step2:
        print("SKIP step 2:      yes")
    if args.skip_step3:
        print("SKIP step 3:      yes")
    print()

    overall_start = time.time()

    # ------------------------------------------------------------------
    # Step 1: BAG-BGT Join (SQL)
    # ------------------------------------------------------------------
    if args.skip_step1:
        print("  Skipping Step 1 (--skip-step1)")
        print()
    else:
        _run_step1_bag_bgt_join(db_params, bag_bgt_join_table)

    # ------------------------------------------------------------------
    # Step 2: Bag minus BGT difference + double buffer filtering
    # ------------------------------------------------------------------
    if args.skip_step2:
        print("=" * 60)
        print("Step 2: Bag Minus BGT")
        print("=" * 60)
        print("  Skipping Step 2 (--skip-step2)")
        print()
    else:
        print("=" * 60)
        print("Step 2: Bag Minus BGT")
        print("=" * 60)

        t0 = time.time()
        with connect(**db_params) as conn:
            create_bag_minus_bgt_table(conn, bag_minus_bgt_table)
            total_count = get_bag_bgt_join_count(conn, bag_bgt_join_table)

        print(f"  Total records to process: {total_count:,}")

        offsets = list(range(0, total_count, chunk_size))
        chunks = []
        for offset in offsets:
            limit = min(chunk_size, total_count - offset)
            with connect(**db_params) as conn:
                chunk_data = load_bag_bgt_join_chunk(
                    conn, offset, limit, bag_bgt_join_table
                )
            chunks.append(chunk_data)

        total_successful = 0
        total_skipped = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(
                    _process_step2_chunk,
                    chunk,
                    i + 1,
                    len(chunks),
                    buffer_distance,
                    bag_minus_bgt_table,
                    db_params,
                ): i
                for i, chunk in enumerate(chunks)
            }

            for future in as_completed(future_to_chunk):
                try:
                    result = future.result()
                    total_successful += result["successful"]
                    total_skipped += result["skipped"]
                except Exception as e:
                    print(f"  Chunk failed: {e}")

        t1 = time.time()
        print(f"  Step 2 complete: {total_successful} written, {total_skipped} skipped in {t1 - t0:.2f}s")
        print()

    # ------------------------------------------------------------------
    # Step 3: Double snapping + intersection of differences
    # ------------------------------------------------------------------
    if args.skip_step3:
        print("=" * 60)
        print("Step 3: Double Snapping")
        print("=" * 60)
        print("  Skipping Step 3 (--skip-step3)")
        print()
    else:
        print("=" * 60)
        print("Step 3: Double Snapping")
        print("=" * 60)

        t0 = time.time()
        with connect(**db_params) as conn:
            create_snapped_differences_table(conn, snapped_diff_table)
            total_count = get_bag_minus_bgt_count(conn, bag_minus_bgt_table)
        print(f"  Total records to process: {total_count:,}")

        offsets = list(range(0, total_count, chunk_size))
        total_chunks = len(offsets)
        print(f"  Total chunks: {total_chunks}")

        total_successful = 0
        total_no_join = 0
        total_filtered = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(
                    _process_step3_chunk,
                    offset,
                    min(chunk_size, total_count - offset),
                    i + 1,
                    total_chunks,
                    snap_tolerance,
                    snapped_diff_table,
                    bag_bgt_join_table,
                    bag_minus_bgt_table,
                    db_params,
                ): i
                for i, offset in enumerate(offsets)
            }

            for future in as_completed(future_to_chunk):
                try:
                    result = future.result()
                    total_successful += result["successful"]
                    total_no_join += result["no_join"]
                    total_filtered += result["filtered"]
                except Exception as e:
                    print(f"  Chunk failed: {e}")

        t1 = time.time()
        print(f"  Step 3 complete: {total_successful} written, {total_no_join} missing join, {total_filtered} filtered to empty in {t1 - t0:.2f}s")
        print()

    # ------------------------------------------------------------------
    # Step 4: Final filtering + ID assignment
    # ------------------------------------------------------------------
    print("=" * 60)
    print("Step 4: Final Filtering and ID Assignment")
    print("=" * 60)

    t0 = time.time()
    with connect(**db_params) as conn:
        create_geometries_table(conn, geometries_table)
        total_count = get_snapped_differences_count(conn, snapped_diff_table)

    print(f"  Total records to process: {total_count:,}")

    offsets = list(range(0, total_count, chunk_size))
    total_chunks = len(offsets)
    print(f"  Total chunks: {total_chunks}")

    chunk_results: dict[int, list[tuple[str, Polygon]]] = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_chunk = {
            executor.submit(
                _process_step4_chunk,
                offset,
                min(chunk_size, total_count - offset),
                i + 1,
                total_chunks,
                buffer_distance,
                snapped_diff_table,
                db_params,
            ): i
            for i, offset in enumerate(offsets)
        }

        for future in as_completed(future_to_chunk):
            try:
                idx, polygons = future.result()
                chunk_results[idx] = polygons
            except Exception as e:
                print(f"  Chunk failed: {e}")

    all_processed: list[tuple[int, str, Polygon]] = []
    next_id = 1
    for chunk_num in sorted(chunk_results):
        for identificatie, poly in chunk_results[chunk_num]:
            all_processed.append((next_id, identificatie, poly))
            next_id += 1

    if all_processed:
        with connect(**db_params) as conn:
            write_geometries_rows(conn, all_processed, geometries_table)
            conn.commit()

    t1 = time.time()
    print(f"  Step 4 complete: {len(all_processed)} underpass polygons in {t1 - t0:.2f}s")
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    elapsed = time.time() - overall_start
    print("=" * 80)
    print("Pipeline Complete")
    print("=" * 80)
    print(f"Total underpass polygons detected: {len(all_processed)}")
    print(f"Output table: {geometries_table}")
    print(f"Total time: {elapsed:.2f}s ({elapsed / 60:.1f} min)")
    print()

    return 0


if __name__ == "__main__":
    parser = _build_parser()
    sys.exit(main(parser.parse_args()))
