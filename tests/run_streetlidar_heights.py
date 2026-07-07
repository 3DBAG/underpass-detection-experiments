"""Estimate underpass heights from Amsterdam street lidar and write them to PostGIS.

The normal path is fully in memory:

1. read pending underpass polygons from PostGIS
2. spatially join them against the street-lidar tile index
3. stream intersecting LAZ chunks
4. select points inside each underpass polygon
5. estimate height from the selected points
6. update the source PostGIS table

Database authentication is expected to come from ~/.pgpass unless a password is
provided through normal libpq environment variables.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import laspy
import numpy as np
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from shapely import wkb
from shapely.strtree import STRtree

REPO_ROOT = Path(__file__).resolve().parents[1]
CROP_SCRIPT_DIR = REPO_ROOT / "crop_las_by_polygons" / "scripts"
HEIGHT_DIR = REPO_ROOT / "height_from_streetlidar"

for import_path in (CROP_SCRIPT_DIR, HEIGHT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from crop_las_by_polygons import (  # noqa: E402
    LasWriterSink,
    POLYGON_BUFFER_DISTANCE,
    TimingStats,
    buffer_outer_rings,
    las_open_options as crop_las_open_options,
    polygonal_geometry,
    prepare_feature,
    sanitize_filename,
    stream_points_for_features,
)
from height_estimation import gpkg_blob_to_geometry, estimate_underpass_height_from_points  # noqa: E402

DEFAULT_INDEX_PATH = Path("/data2/rypeters/amsterdam_data/2025/pointcloud/ams_index.gpkg")
DEFAULT_POINTCLOUD_ROOT = Path("/data2/rypeters/amsterdam_data/2025/pointcloud")
DEFAULT_CROP_POINTCLOUD_OUTPUT_DIR = Path("/data2/rypeters/amsterdam_data/2025/cropped")
DEFAULT_SOURCE_TABLE = "underpasses.extended_geometries_july"
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = 5432
DEFAULT_DB_NAME = "baseregisters"
DEFAULT_DB_USER = "rypeters"
DEFAULT_HEIGHT_WORKERS = max(1, min(4, os.cpu_count() or 1))
DEFAULT_PIP_WORKERS = max(1, min(4, os.cpu_count() or 1))
DEFAULT_LAZ_BACKEND = "lazrs-parallel"
DEFAULT_DECOMPRESSION = "xyz"
DEFAULT_BATCH_WORKERS = 1

RESULT_COLUMNS = {
    "h_underpass": "double precision",
    "h_underpass_source": "text",
    "h_underpass_status": "text",
    "h_underpass_z_min": "double precision",
    "h_underpass_z_max": "double precision",
    "h_underpass_candidate_peaks": "jsonb",
    "h_underpass_point_count": "integer",
    "h_underpass_laz_count": "integer",
    "h_underpass_error": "text",
    "h_underpass_updated_at": "timestamptz",
}


@dataclasses.dataclass
class TileRecord:
    path: Path
    geometry: object


@dataclasses.dataclass
class UnderpassRecord:
    identificatie: str
    underpass_id: int
    geometry: object

    @property
    def key(self) -> str:
        return f"{self.underpass_id}__{self.identificatie}"


@dataclasses.dataclass
class PointAccumulator:
    x_parts: list[np.ndarray] = dataclasses.field(default_factory=list)
    y_parts: list[np.ndarray] = dataclasses.field(default_factory=list)
    z_parts: list[np.ndarray] = dataclasses.field(default_factory=list)
    point_count: int = 0
    exceeded_limit: bool = False

    def add(
        self,
        xs: np.ndarray,
        ys: np.ndarray,
        zs: np.ndarray,
        indices: np.ndarray,
        max_points: int | None,
    ) -> None:
        count = int(indices.size)
        if count == 0:
            return

        self.point_count += count
        if max_points is not None and self.point_count > max_points:
            self.exceeded_limit = True
            return

        self.x_parts.append(np.asarray(xs[indices], dtype=np.float64))
        self.y_parts.append(np.asarray(ys[indices], dtype=np.float64))
        self.z_parts.append(np.asarray(zs[indices], dtype=np.float64))

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not self.x_parts:
            empty = np.empty(0, dtype=np.float64)
            return empty, empty, empty
        return (
            np.concatenate(self.x_parts),
            np.concatenate(self.y_parts),
            np.concatenate(self.z_parts),
        )


class HeightCropSink:
    def __init__(
        self,
        accumulators: list[PointAccumulator],
        max_points_per_underpass: int | None,
        writer_sink: LasWriterSink | None,
    ) -> None:
        self.accumulators = accumulators
        self.max_points_per_underpass = max_points_per_underpass
        self.writer_sink = writer_sink

    def add(
        self,
        feature_idx: int,
        chunk,
        xs: np.ndarray,
        ys: np.ndarray,
        zs: np.ndarray | None,
        selected_idx: np.ndarray,
        source_header: laspy.LasHeader,
    ) -> None:
        if zs is None:
            raise RuntimeError("Height estimation requires z coordinates")
        self.accumulators[feature_idx].add(
            xs,
            ys,
            zs,
            selected_idx,
            self.max_points_per_underpass,
        )
        if self.writer_sink is not None:
            self.writer_sink.add(feature_idx, chunk, xs, ys, zs, selected_idx, source_header)


@dataclasses.dataclass
class HeightResult:
    identificatie: str
    underpass_id: int
    status: str
    point_count: int
    laz_count: int
    h_underpass: float | None = None
    z_min: float | None = None
    z_max: float | None = None
    candidate_peaks: list[dict[str, object]] | None = None
    error: str | None = None


@dataclasses.dataclass
class HeightEstimationTask:
    identificatie: str
    underpass_id: int
    key: str
    crop_geometry: object
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    point_count: int
    laz_count: int
    error_text: str | None
    plot_dir: Path | None
    plot_rerun: bool


@dataclasses.dataclass
class SpatialBatch:
    grid_x: int
    grid_y: int
    part: int
    records: list[UnderpassRecord]


@dataclasses.dataclass
class BatchWorkerResult:
    batch_index: int
    results: list[HeightResult]
    timing: TimingStats
    elapsed_s: float


class TileIndex:
    def __init__(self, tiles: list[TileRecord]) -> None:
        self.tiles = tiles
        self.geometries = [tile.geometry for tile in tiles]
        self.tree = STRtree(self.geometries)
        self.geometry_id_to_index = {
            id(geometry): index for index, geometry in enumerate(self.geometries)
        }

    def query(self, geometry) -> list[TileRecord]:
        matches = self.tree.query(geometry)
        tiles: list[TileRecord] = []
        for match in matches:
            if isinstance(match, (int, np.integer)):
                tile = self.tiles[int(match)]
            else:
                tile = self.tiles[self.geometry_id_to_index[id(match)]]
            if tile.geometry.intersects(geometry):
                tiles.append(tile)
        return tiles


BATCH_WORKER_ARGS: argparse.Namespace | None = None
BATCH_WORKER_TILE_INDEX: TileIndex | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--index-layer", default=None)
    parser.add_argument("--pointcloud-root", type=Path, default=DEFAULT_POINTCLOUD_ROOT)
    parser.add_argument("--table", default=os.environ.get("UNDERPASS_POLYGON_TABLE", DEFAULT_SOURCE_TABLE))
    parser.add_argument("--db-host", default=os.environ.get("UNDERPASS_DB_HOST", DEFAULT_DB_HOST))
    parser.add_argument("--db-port", type=int, default=int(os.environ.get("UNDERPASS_DB_PORT", DEFAULT_DB_PORT)))
    parser.add_argument("--db-name", default=os.environ.get("UNDERPASS_DB_NAME", DEFAULT_DB_NAME))
    parser.add_argument("--db-user", default=os.environ.get("UNDERPASS_DB_USER", DEFAULT_DB_USER))
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--batch-workers",
        type=int,
        default=DEFAULT_BATCH_WORKERS,
        help="Process spatial batches in parallel. DB updates still happen in the parent process.",
    )
    parser.add_argument("--grid-cell-size", type=float, default=200.0)
    parser.add_argument("--chunk-size", type=int, default=1_000_000)
    parser.add_argument(
        "--laz-backend",
        choices=("auto", "lazrs-parallel", "lazrs", "laszip"),
        default=DEFAULT_LAZ_BACKEND,
        help="LAZ decompression backend. lazrs-parallel is usually fastest when available.",
    )
    parser.add_argument(
        "--decompression",
        choices=("all", "xyz"),
        default=DEFAULT_DECOMPRESSION,
        help="LAZ dimensions to decompress. xyz skips unused attributes.",
    )
    parser.add_argument(
        "--crop-output-dir",
        type=Path,
        default=DEFAULT_CROP_POINTCLOUD_OUTPUT_DIR,
        help="Directory for reusable cropped LAZ/LAS files, one per underpass.",
    )
    parser.add_argument("--crop-output-extension", default=".laz", help="Suffix for cropped point clouds.")
    parser.add_argument(
        "--reuse-cropped",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When --crop-output-dir is set, read existing cropped point clouds instead of rescanning source tiles.",
    )
    parser.add_argument(
        "--write-cropped",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When --crop-output-dir is set, write missing cropped point clouds while streaming source tiles.",
    )
    parser.add_argument("--height-workers", type=int, default=DEFAULT_HEIGHT_WORKERS)
    parser.add_argument(
        "--pip-workers",
        type=int,
        default=DEFAULT_PIP_WORKERS,
        help="Thread workers for point-in-polygon selection within each sequentially read LAZ chunk.",
    )
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--min-points", type=int, default=10000)
    parser.add_argument("--max-points-per-underpass", type=int, default=110_000_000)
    parser.add_argument(
        "--only-status",
        action="append",
        default=[],
        help="Only process rows with this existing h_underpass_status. Can be passed multiple times.",
    )
    parser.add_argument("--polygon-buffer", type=float, default=POLYGON_BUFFER_DISTANCE)
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MINX", "MINY", "MAXX", "MAXY"),
        help="Only process underpasses whose geometry intersects this EPSG:28992 bbox.",
    )
    parser.add_argument(
        "--within-index-extent",
        action="store_true",
        help="Only process underpasses intersecting the street-lidar index extent.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-underpass-id", type=int, action="append", default=[])
    parser.add_argument(
        "--only-identificatie",
        "--only-building-id",
        dest="only_identificatie",
        action="append",
        default=[],
        help="Only process rows with this identificatie/BAG building id. Can be passed multiple times.",
    )
    parser.add_argument("--all", action="store_true", help="Process rows even when h_underpass is already filled.")
    parser.add_argument(
        "--plot-dir",
        type=Path,
        default=None,
        help=(
            "Write diagnostic peak-grid PNG plots, selected-point LAS files, "
            "and candidate-peak JSON files to this directory."
        ),
    )
    parser.add_argument(
        "--plot-rerun",
        action="store_true",
        help="Also write/send the optional Rerun visualization when --plot-dir is used.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run the pipeline without updating PostGIS.")
    parser.add_argument("--skip-db-setup", action="store_true", help="Do not add missing result columns.")
    return parser.parse_args(argv)


def table_identifier(table_name: str) -> sql.Identifier:
    parts = [part for part in table_name.split(".") if part]
    if not parts:
        raise ValueError("table name cannot be empty")
    return sql.Identifier(*parts)


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def connect_db(args: argparse.Namespace) -> psycopg.Connection:
    return psycopg.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
    )


def laz_open_options(args: argparse.Namespace, decompression: str | None = None) -> dict[str, object]:
    return crop_las_open_options(args.laz_backend, decompression or args.decompression)


def ensure_result_columns(conn: psycopg.Connection, table_name: str) -> None:
    table = table_identifier(table_name)
    with conn.cursor() as cur:
        for column_name, column_type in RESULT_COLUMNS.items():
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {}").format(
                    table,
                    sql.Identifier(column_name),
                    sql.SQL(column_type),
                )
            )
    conn.commit()


def fetch_pending_records(conn: psycopg.Connection, args: argparse.Namespace) -> list[UnderpassRecord]:
    conditions = [
        sql.SQL("geom IS NOT NULL"),
        sql.SQL("NOT ST_IsEmpty(geom)"),
    ]
    params: list[object] = []

    if args.only_status:
        conditions.append(sql.SQL("h_underpass_status = ANY(%s::text[])"))
        params.append(args.only_status)
    elif not args.all:
        conditions.append(sql.SQL("h_underpass IS NULL"))

    if args.only_underpass_id:
        conditions.append(sql.SQL("underpass_id = ANY(%s)"))
        params.append(args.only_underpass_id)

    if args.only_identificatie:
        conditions.append(sql.SQL("identificatie::text = ANY(%s::text[])"))
        params.append(args.only_identificatie)

    if args.bbox:
        minx, miny, maxx, maxy = args.bbox
        conditions.append(sql.SQL("geom && ST_MakeEnvelope(%s, %s, %s, %s, 28992)"))
        params.extend([minx, miny, maxx, maxy])

    query = sql.SQL(
        """
        SELECT identificatie::text, underpass_id::integer, ST_AsBinary(geom)
        FROM {table}
        WHERE {conditions}
        ORDER BY
            floor(ST_X(ST_PointOnSurface(geom)) / %s),
            floor(ST_Y(ST_PointOnSurface(geom)) / %s),
            underpass_id
        """
    ).format(
        table=table_identifier(args.table),
        conditions=sql.SQL(" AND ").join(conditions),
    )
    params.extend([args.grid_cell_size, args.grid_cell_size])

    if args.limit is not None:
        query += sql.SQL(" LIMIT %s")
        params.append(args.limit)

    records: list[UnderpassRecord] = []
    with conn.cursor() as cur:
        cur.execute(query, params)
        for identificatie, underpass_id, geom_wkb in cur.fetchall():
            geometry = wkb.loads(bytes(geom_wkb))
            records.append(
                UnderpassRecord(
                    identificatie=str(identificatie),
                    underpass_id=int(underpass_id),
                    geometry=geometry,
                )
            )
    return records


def index_extent(index_path: Path, layer_name: str | None) -> tuple[float, float, float, float]:
    table_name, geometry_column = gpkg_feature_table_and_geometry_column(index_path, layer_name)
    rtree_table = f"rtree_{table_name}_{geometry_column}"
    with sqlite3.connect(index_path) as con:
        row = con.execute(
            f"""
            SELECT min(minx), min(miny), max(maxx), max(maxy)
            FROM {quote_sqlite_identifier(rtree_table)}
            """
        ).fetchone()
    if row is None or any(value is None for value in row):
        raise RuntimeError(f"Could not read spatial index extent from {index_path}:{table_name}")
    return tuple(float(value) for value in row)


def fetch_table_summary(conn: psycopg.Connection, table_name: str) -> dict[str, object]:
    query = sql.SQL(
        """
        SELECT
            count(*) AS total_rows,
            count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)) AS usable_geom_rows,
            count(*) FILTER (
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                  AND (
                    h_underpass IS NULL
                    OR h_underpass_status IN ('failed', 'no_laz_tiles', 'no_points', 'too_few_points')
                  )
            ) AS pending_rows,
            count(*) FILTER (WHERE h_underpass IS NOT NULL) AS rows_with_height
        FROM {table}
        """
    ).format(table=table_identifier(table_name))
    status_query = sql.SQL(
        """
        SELECT coalesce(h_underpass_status, '<null>') AS status, count(*)
        FROM {table}
        GROUP BY coalesce(h_underpass_status, '<null>')
        ORDER BY count(*) DESC, status
        LIMIT 12
        """
    ).format(table=table_identifier(table_name))

    with conn.cursor() as cur:
        cur.execute(query)
        total_rows, usable_geom_rows, pending_rows, rows_with_height = cur.fetchone()
        cur.execute(status_query)
        statuses = cur.fetchall()

    return {
        "total_rows": total_rows,
        "usable_geom_rows": usable_geom_rows,
        "pending_rows": pending_rows,
        "rows_with_height": rows_with_height,
        "statuses": statuses,
    }


def null_result(
    record: UnderpassRecord,
    status: str,
    point_count: int,
    laz_count: int,
    error: str | None,
) -> HeightResult:
    return null_result_values(
        record.identificatie,
        record.underpass_id,
        status,
        point_count,
        laz_count,
        error,
    )


def null_result_values(
    identificatie: str,
    underpass_id: int,
    status: str,
    point_count: int,
    laz_count: int,
    error: str | None,
) -> HeightResult:
    return HeightResult(
        identificatie=identificatie,
        underpass_id=underpass_id,
        status=status,
        h_underpass=None,
        point_count=point_count,
        laz_count=laz_count,
        candidate_peaks=None,
        error=error,
    )


def crop_output_path(record: UnderpassRecord, args: argparse.Namespace) -> Path | None:
    if args.crop_output_dir is None:
        return None
    extension = args.crop_output_extension
    if not extension.startswith("."):
        extension = f".{extension}"
    return args.crop_output_dir / f"{sanitize_filename(record.key)}{extension}"


def read_cached_crop_points(
    path: Path,
    accumulator: PointAccumulator,
    max_points_per_underpass: int | None,
    chunk_size: int,
    open_options: dict[str, object],
    timing: TimingStats,
) -> None:
    try:
        tile_size = path.stat().st_size
    except OSError:
        tile_size = 0

    t_open = time.perf_counter()
    with laspy.open(path, **open_options) as reader:
        timing.tile_open_s += time.perf_counter() - t_open
        if reader.header.point_count == 0:
            raise RuntimeError("Cached crop contains no points")
        timing.tiles_opened += 1
        timing.unique_tiles_opened += 1
        timing.laz_bytes_seen += tile_size

        chunk_iterator = reader.chunk_iterator(chunk_size)
        while True:
            t0 = time.perf_counter()
            try:
                chunk = next(chunk_iterator)
            except StopIteration:
                timing.chunk_read_s += time.perf_counter() - t0
                break
            timing.chunk_read_s += time.perf_counter() - t0
            timing.chunks += 1

            t0 = time.perf_counter()
            xs = np.asarray(chunk.x, dtype=np.float64)
            ys = np.asarray(chunk.y, dtype=np.float64)
            zs = np.asarray(chunk.z, dtype=np.float64)
            timing.chunk_coord_extract_s += time.perf_counter() - t0

            indices = np.arange(xs.size, dtype=np.int64)
            timing.points_read += int(xs.size)
            timing.points_selected += int(xs.size)
            accumulator.add(xs, ys, zs, indices, max_points_per_underpass)


def write_pointcloud(path: Path, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.array([float(np.min(x)), float(np.min(y)), float(np.min(z))])

    las = laspy.LasData(header)
    las.x = x
    las.y = y
    las.z = z
    try:
        las.write(path)
        return path
    except Exception:
        if path.suffix.lower() == ".laz":
            las_path = path.with_suffix(".las")
            try:
                las.write(las_path)
                return las_path
            except Exception:
                pass

        csv_path = path.with_suffix(".csv")
        np.savetxt(
            csv_path,
            np.column_stack((x, y, z)),
            delimiter=",",
            header="x,y,z",
            comments="",
        )
        return csv_path


def run_height_estimation_task(task: HeightEstimationTask) -> HeightResult:
    try:
        estimate = estimate_underpass_height_from_points(
            task.key,
            task.x,
            task.y,
            task.z,
            [task.crop_geometry],
            verbose=False,
        )
        metrics = estimate["underpass_metrics"]
        result_error = task.error_text
        if task.plot_dir is not None:
            candidate_peaks_path = task.plot_dir / f"{task.key}_candidate_peaks.json"
            try:
                task.plot_dir.mkdir(parents=True, exist_ok=True)
                with candidate_peaks_path.open("w", encoding="utf-8") as peaks_file:
                    json.dump(metrics["underpass_candidate_peaks"], peaks_file, indent=2)
                    peaks_file.write("\n")
                print(f"Saved candidate peaks to {candidate_peaks_path}", flush=True)
            except Exception as exc:
                peaks_error = f"Candidate-peak export failed: {short_error(exc)}"
                print(f"{task.key}: {peaks_error}", flush=True)
                result_error = (
                    f"{result_error}; {peaks_error}"
                    if result_error
                    else peaks_error
                )

            pointcloud_path = task.plot_dir / f"{task.key}_points.las"
            try:
                written_path = write_pointcloud(pointcloud_path, task.x, task.y, task.z)
                print(f"Saved point cloud to {written_path}", flush=True)
            except Exception as exc:
                pointcloud_error = f"Point-cloud export failed: {short_error(exc)}"
                print(f"{task.key}: {pointcloud_error}", flush=True)
                result_error = (
                    f"{result_error}; {pointcloud_error}"
                    if result_error
                    else pointcloud_error
                )

            try:
                from plot_z_histogram import plot_height_estimation_result

                plot_height_estimation_result(
                    estimate,
                    output_dir=task.plot_dir,
                    write_rerun=task.plot_rerun,
                )
            except Exception as exc:
                plot_error = f"Plot generation failed: {short_error(exc)}"
                print(f"{task.key}: {plot_error}", flush=True)
                result_error = (
                    f"{result_error}; {plot_error}"
                    if result_error
                    else plot_error
                )
        return HeightResult(
            identificatie=task.identificatie,
            underpass_id=task.underpass_id,
            status="success",
            h_underpass=float(metrics["underpass_h"]),
            z_min=float(metrics["underpass_z_min"]),
            z_max=float(metrics["underpass_z_max"]),
            candidate_peaks=metrics["underpass_candidate_peaks"],
            point_count=task.point_count,
            laz_count=task.laz_count,
            error=result_error,
        )
    except Exception as exc:
        return null_result_values(
            task.identificatie,
            task.underpass_id,
            status="failed",
            point_count=task.point_count,
            laz_count=task.laz_count,
            error=short_error(exc),
        )


def update_results(conn: psycopg.Connection, table_name: str, results: Iterable[HeightResult]) -> None:
    rows = [
        (
            result.h_underpass,
            "streetlidar" if result.status == "success" else "fallback",
            result.status,
            result.z_min,
            result.z_max,
            Jsonb(result.candidate_peaks) if result.candidate_peaks is not None else None,
            result.point_count,
            result.laz_count,
            result.error,
            result.identificatie,
            result.underpass_id,
        )
        for result in results
    ]
    if not rows:
        return

    query = sql.SQL(
        """
        UPDATE {table}
        SET h_underpass = %s,
            h_underpass_source = %s,
            h_underpass_status = %s,
            h_underpass_z_min = %s,
            h_underpass_z_max = %s,
            h_underpass_candidate_peaks = %s,
            h_underpass_point_count = %s,
            h_underpass_laz_count = %s,
            h_underpass_error = %s,
            h_underpass_updated_at = now()
        WHERE identificatie = %s
          AND underpass_id = %s
        """
    ).format(table=table_identifier(table_name))

    with conn.cursor() as cur:
        cur.executemany(query, rows)
    conn.commit()


def gpkg_feature_table_and_geometry_column(index_path: Path, layer_name: str | None) -> tuple[str, str]:
    with sqlite3.connect(index_path) as con:
        if layer_name is None:
            row = con.execute(
                """
                SELECT table_name
                FROM gpkg_contents
                WHERE data_type = 'features'
                ORDER BY table_name
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                raise RuntimeError(f"No feature layers found in {index_path}")
            table_name = str(row[0])
        else:
            table_name = layer_name

        row = con.execute(
            """
            SELECT column_name
            FROM gpkg_geometry_columns
            WHERE table_name = ?
            LIMIT 1
            """,
            (table_name,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"No geometry column found for {index_path}:{table_name}")
        geometry_column = str(row[0])

    return table_name, geometry_column


def load_tile_index(index_path: Path, pointcloud_root: Path, layer_name: str | None) -> TileIndex:
    selected_layer, geometry_column = gpkg_feature_table_and_geometry_column(index_path, layer_name)
    tiles: list[TileRecord] = []
    query = f'SELECT location, "{geometry_column}" FROM "{selected_layer}" WHERE location IS NOT NULL AND "{geometry_column}" IS NOT NULL'

    with sqlite3.connect(index_path) as con:
        for location, geometry_blob in con.execute(query):
            if not location or geometry_blob is None:
                continue

            path = Path(str(location))
            if not path.is_absolute():
                path = pointcloud_root / path
            tiles.append(TileRecord(path=path.resolve(), geometry=gpkg_blob_to_geometry(geometry_blob)))

    if not tiles:
        raise RuntimeError(f"No usable tile records found in {index_path}:{selected_layer}")
    return TileIndex(tiles)


def count_tile_index_records(index_path: Path, layer_name: str | None) -> int:
    selected_layer, geometry_column = gpkg_feature_table_and_geometry_column(index_path, layer_name)
    query = (
        f"SELECT count(*) FROM {quote_sqlite_identifier(selected_layer)} "
        f"WHERE location IS NOT NULL AND {quote_sqlite_identifier(geometry_column)} IS NOT NULL"
    )
    with sqlite3.connect(index_path) as con:
        row = con.execute(query).fetchone()
    return int(row[0]) if row is not None else 0


def spatial_sort(records: list[UnderpassRecord]) -> list[UnderpassRecord]:
    return sorted(
        records,
        key=lambda record: (
            record.geometry.bounds[0],
            record.geometry.bounds[1],
            record.underpass_id,
        ),
    )


def chunks(values: list[UnderpassRecord], size: int) -> Iterable[list[UnderpassRecord]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def record_grid_cell(record: UnderpassRecord, cell_size: float) -> tuple[int, int]:
    point = record.geometry.representative_point()
    return math.floor(point.x / cell_size), math.floor(point.y / cell_size)


def spatial_batches(
    records: list[UnderpassRecord],
    cell_size: float,
    max_batch_size: int,
) -> list[SpatialBatch]:
    records_by_cell: dict[tuple[int, int], list[UnderpassRecord]] = defaultdict(list)
    for record in records:
        records_by_cell[record_grid_cell(record, cell_size)].append(record)

    batches: list[SpatialBatch] = []
    for grid_x, grid_y in sorted(records_by_cell):
        cell_records = spatial_sort(records_by_cell[(grid_x, grid_y)])
        for part, batch_records in enumerate(chunks(cell_records, max_batch_size), start=1):
            batches.append(
                SpatialBatch(
                    grid_x=grid_x,
                    grid_y=grid_y,
                    part=part,
                    records=batch_records,
                )
            )
    return batches


def prepare_crop_geometry(record: UnderpassRecord, polygon_buffer: float):
    geometry = polygonal_geometry(record.geometry)
    if polygon_buffer != 0:
        geometry = buffer_outer_rings(geometry, polygon_buffer)
    return geometry


def build_batch_inputs(
    records: list[UnderpassRecord],
    tile_index: TileIndex,
    resolution: int,
    polygon_buffer: float,
    args: argparse.Namespace,
) -> tuple[list[UnderpassRecord], list[object], list[object], list[list[Path]], list[Path | None], list[HeightResult]]:
    prepared_records: list[UnderpassRecord] = []
    prepared_features: list[object] = []
    crop_geometries: list[object] = []
    feature_tile_paths: list[list[Path]] = []
    crop_paths: list[Path | None] = []
    early_results: list[HeightResult] = []

    for record in records:
        crop_path = crop_output_path(record, args)
        try:
            crop_geometry = prepare_crop_geometry(record, polygon_buffer)
            tiles = tile_index.query(crop_geometry)
            has_reusable_crop = (
                crop_path is not None
                and args.reuse_cropped
                and crop_path.is_file()
            )
            if not tiles and not has_reusable_crop:
                early_results.append(
                    null_result(
                        record,
                        status="no_laz_tiles",
                        point_count=0,
                        laz_count=0,
                        error="No street-lidar tiles intersect the underpass polygon",
                    )
                )
                continue

            prepared_feature = prepare_feature(
                crop_geometry,
                record.key,
                crop_path or Path(f"{record.key}.laz"),
                resolution,
            )
        except Exception as exc:
            early_results.append(
                null_result(
                    record,
                    status="invalid_geometry",
                    point_count=0,
                    laz_count=0,
                    error=short_error(exc),
                )
            )
            continue

        prepared_records.append(record)
        prepared_features.append(prepared_feature)
        crop_geometries.append(crop_geometry)
        feature_tile_paths.append(sorted({tile.path for tile in tiles}))
        crop_paths.append(crop_path)

    return prepared_records, prepared_features, crop_geometries, feature_tile_paths, crop_paths, early_results


def stream_points_for_batch(
    features: list[object],
    feature_tile_paths: list[list[Path]],
    accumulators: list[PointAccumulator],
    errors: list[list[str]],
    chunk_size: int,
    max_points_per_underpass: int | None,
    pip_workers: int,
    open_options: dict[str, object],
    timing: TimingStats,
    writer_sink: LasWriterSink | None = None,
    cached_feature_indices: set[int] | None = None,
) -> None:
    tile_to_feature_indices: dict[Path, list[int]] = defaultdict(list)
    for feature_idx, tile_paths in enumerate(feature_tile_paths):
        for tile_path in tile_paths:
            tile_to_feature_indices[tile_path].append(feature_idx)

    if not tile_to_feature_indices:
        return

    cached_feature_indices = cached_feature_indices or set()
    sink = HeightCropSink(accumulators, max_points_per_underpass, writer_sink)

    def should_skip(feature_idx: int) -> bool:
        if feature_idx in cached_feature_indices:
            return True
        return writer_sink is None and accumulators[feature_idx].exceeded_limit

    def record_error(feature_idx: int, message: str) -> None:
        errors[feature_idx].append(message)

    stream_points_for_features(
        tile_to_feature_indices,
        features,
        sink,
        chunk_size,
        timing,
        pip_workers=pip_workers,
        open_options=open_options,
        read_z=True,
        skip_feature=should_skip,
        record_error=record_error,
    )


def estimate_batch_results(
    records: list[UnderpassRecord],
    crop_geometries: list[object],
    feature_tile_paths: list[list[Path]],
    accumulators: list[PointAccumulator],
    errors: list[list[str]],
    min_points: int,
    max_points_per_underpass: int | None,
    height_workers: int,
    plot_dir: Path | None,
    plot_rerun: bool,
) -> list[HeightResult]:
    results: list[HeightResult] = []
    tasks: list[HeightEstimationTask] = []
    for record, crop_geometry, tile_paths, accumulator, record_errors in zip(
        records,
        crop_geometries,
        feature_tile_paths,
        accumulators,
        errors,
        strict=True,
    ):
        existing_laz_count = sum(1 for path in tile_paths if path.is_file())

        if accumulator.exceeded_limit:
            results.append(
                null_result(
                    record,
                    status="too_many_points",
                    point_count=accumulator.point_count,
                    laz_count=existing_laz_count,
                    error=f"Selected more than {max_points_per_underpass} points",
                )
            )
            continue

        if accumulator.point_count == 0:
            results.append(
                null_result(
                    record,
                    status="no_points",
                    point_count=0,
                    laz_count=existing_laz_count,
                    error="; ".join(record_errors)[:1000] if record_errors else "No points inside polygon",
                )
            )
            continue

        if accumulator.point_count < min_points:
            results.append(
                null_result(
                    record,
                    status="too_few_points",
                    point_count=accumulator.point_count,
                    laz_count=existing_laz_count,
                    error=f"Only {accumulator.point_count} points inside polygon; minimum is {min_points}",
                )
            )
            continue

        x, y, z = accumulator.arrays()
        tasks.append(
            HeightEstimationTask(
                identificatie=record.identificatie,
                underpass_id=record.underpass_id,
                key=record.key,
                crop_geometry=crop_geometry,
                x=x,
                y=y,
                z=z,
                point_count=accumulator.point_count,
                laz_count=existing_laz_count,
                error_text="; ".join(record_errors)[:1000] if record_errors else None,
                plot_dir=plot_dir,
                plot_rerun=plot_rerun,
            )
        )

    if not tasks:
        return results

    if height_workers <= 1 or len(tasks) == 1:
        results.extend(run_height_estimation_task(task) for task in tasks)
    else:
        worker_count = min(height_workers, len(tasks))
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            results.extend(executor.map(run_height_estimation_task, tasks))

    return results


def process_batch(
    records: list[UnderpassRecord],
    tile_index: TileIndex,
    args: argparse.Namespace,
) -> tuple[list[HeightResult], TimingStats]:
    timing = TimingStats()
    prepared_records, features, crop_geometries, feature_tile_paths, crop_paths, early_results = build_batch_inputs(
        records,
        tile_index,
        args.resolution,
        args.polygon_buffer,
        args,
    )
    accumulators = [PointAccumulator() for _ in features]
    errors: list[list[str]] = [[] for _ in features]
    cached_feature_indices: set[int] = set()
    writer_sink: LasWriterSink | None = None

    try:
        if args.crop_output_dir is not None and args.reuse_cropped:
            for feature_idx, crop_path in enumerate(crop_paths):
                if crop_path is None or not crop_path.is_file():
                    continue
                try:
                    read_cached_crop_points(
                        crop_path,
                        accumulators[feature_idx],
                        args.max_points_per_underpass,
                        args.chunk_size,
                        laz_open_options(args, "xyz"),
                        timing,
                    )
                    cached_feature_indices.add(feature_idx)
                except Exception as exc:
                    errors[feature_idx].append(f"Could not read cached crop {crop_path}: {short_error(exc)}")

        if args.crop_output_dir is not None and args.write_cropped:
            writer_sink = LasWriterSink(features, normalize_point_format=True, atomic=True)

        source_open_options = laz_open_options(
            args,
            "all" if writer_sink is not None else args.decompression,
        )
        stream_points_for_batch(
            features,
            feature_tile_paths,
            accumulators,
            errors,
            args.chunk_size,
            args.max_points_per_underpass,
            args.pip_workers,
            source_open_options,
            timing,
            writer_sink=writer_sink,
            cached_feature_indices=cached_feature_indices,
        )
        t0 = time.perf_counter()
        results = early_results + estimate_batch_results(
            prepared_records,
            crop_geometries,
            feature_tile_paths,
            accumulators,
            errors,
            args.min_points,
            args.max_points_per_underpass,
            args.height_workers,
            args.plot_dir,
            args.plot_rerun,
        )
        timing.height_estimation_s += time.perf_counter() - t0
    finally:
        if writer_sink is not None:
            writer_sink.close()
        for feature in features:
            feature.close()

    return results, timing


def init_batch_worker(args: argparse.Namespace) -> None:
    global BATCH_WORKER_ARGS, BATCH_WORKER_TILE_INDEX
    BATCH_WORKER_ARGS = args
    BATCH_WORKER_TILE_INDEX = load_tile_index(args.index, args.pointcloud_root, args.index_layer)


def process_batch_worker(batch_index: int, batch: SpatialBatch) -> BatchWorkerResult:
    if BATCH_WORKER_ARGS is None or BATCH_WORKER_TILE_INDEX is None:
        raise RuntimeError("Batch worker was not initialized")

    t0 = time.perf_counter()
    results, timing = process_batch(batch.records, BATCH_WORKER_TILE_INDEX, BATCH_WORKER_ARGS)
    elapsed_s = time.perf_counter() - t0
    return BatchWorkerResult(
        batch_index=batch_index,
        results=results,
        timing=timing,
        elapsed_s=elapsed_s,
    )


def consume_batch_result(
    batch_count: int,
    batch: SpatialBatch,
    batch_result: BatchWorkerResult,
    update_conn: psycopg.Connection | None,
    args: argparse.Namespace,
    total_counts: Counter[str],
) -> None:
    timing = batch_result.timing
    total_counts.update(result.status for result in batch_result.results)
    if update_conn is not None:
        t_db = time.perf_counter()
        update_results(update_conn, args.table, batch_result.results)
        timing.db_update_s += time.perf_counter() - t_db

    elapsed_s = batch_result.elapsed_s + timing.db_update_s
    print_batch_summary(
        batch_result.batch_index,
        batch_count,
        batch,
        batch_result.results,
        timing,
        elapsed_s,
    )


def short_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:1000]


def format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024.0 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{amount:.1f} TiB"


def format_rate(bytes_count: int, elapsed_s: float) -> str:
    if elapsed_s <= 0:
        return "n/a"
    return f"{bytes_count / 1024.0 / 1024.0 / elapsed_s:.1f} MiB/s"


def format_points_per_second(point_count: int, elapsed_s: float) -> str:
    if elapsed_s <= 0:
        return "n/a"
    return f"{point_count / 1_000_000.0 / elapsed_s:.2f} Mpts/s"


def print_batch_summary(
    batch_index: int,
    batch_count: int,
    batch: SpatialBatch,
    results: list[HeightResult],
    timing: TimingStats,
    elapsed_s: float,
) -> None:
    status_counts = Counter(result.status for result in results)
    statuses = ", ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
    print(
        f"batch {batch_index}/{batch_count}: {len(results)} underpasses, "
        f"grid=({batch.grid_x}, {batch.grid_y}), part={batch.part}, "
        f"{statuses}; chunks={timing.chunks}, "
        f"active_features_max={timing.active_features_max}, elapsed={elapsed_s:.1f}s"
    )
    print(
        "  profile: "
        f"tiles={timing.tiles_opened} unique={timing.unique_tiles_opened}, "
        f"laz={format_bytes(timing.laz_bytes_seen)}, "
        f"open={timing.tile_open_s:.2f}s, "
        f"read+decomp={timing.chunk_read_s:.2f}s ({format_rate(timing.laz_bytes_seen, timing.chunk_read_s)}), "
        f"coord={timing.chunk_coord_extract_s:.2f}s, "
        f"cull={timing.chunk_feature_cull_s:.2f}s, "
        f"pip_worker={timing.pip_select_s:.2f}s, "
        f"height={timing.height_estimation_s:.2f}s, "
        f"db={timing.db_update_s:.2f}s"
    )
    print(
        "  points: "
        f"read={timing.points_read:,} ({format_points_per_second(timing.points_read, timing.chunk_read_s)} read+decomp), "
        f"selected={timing.points_selected:,}, "
        f"feature_tests={timing.feature_tests:,}, "
        f"component_tests={timing.component_tests:,}"
    )
    failed_results = [result for result in results if result.status == "failed" and result.error]
    for result in failed_results[:3]:
        print(f"  failure {result.underpass_id} {result.identificatie}: {result.error}")
    if len(failed_results) > 3:
        print(f"  ... {len(failed_results) - 3} more failures")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.batch_workers <= 0:
        raise ValueError("--batch-workers must be positive")
    if args.grid_cell_size <= 0:
        raise ValueError("--grid-cell-size must be positive")
    if args.height_workers <= 0:
        raise ValueError("--height-workers must be positive")
    if args.pip_workers <= 0:
        raise ValueError("--pip-workers must be positive")
    if args.min_points < 0:
        raise ValueError("--min-points cannot be negative")
    if args.max_points_per_underpass <= 0:
        args.max_points_per_underpass = None
    if args.crop_output_dir is None:
        args.reuse_cropped = False
        args.write_cropped = False
    elif args.write_cropped:
        args.crop_output_dir.mkdir(parents=True, exist_ok=True)
    if args.within_index_extent:
        args.bbox = index_extent(args.index, args.index_layer)
        print(
            "Using street-lidar index extent bbox: "
            f"{args.bbox[0]:.3f}, {args.bbox[1]:.3f}, {args.bbox[2]:.3f}, {args.bbox[3]:.3f}"
        )

    with connect_db(args) as conn:
        if not args.skip_db_setup and not args.dry_run:
            ensure_result_columns(conn, args.table)
        records = fetch_pending_records(conn, args)
        if not records:
            summary = fetch_table_summary(conn, args.table)

    if not records:
        print(
            "No pending underpasses found in "
            f"{args.table} on {args.db_host}:{args.db_port}/{args.db_name} as {args.db_user}."
        )
        print(
            "Table summary: "
            f"total_rows={summary['total_rows']}, "
            f"usable_geom_rows={summary['usable_geom_rows']}, "
            f"pending_rows={summary['pending_rows']}, "
            f"rows_with_height={summary['rows_with_height']}"
        )
        statuses = summary["statuses"]
        if statuses:
            print("Status counts:")
            for status, count in statuses:
                print(f"  {status}: {count}")
        print("Use --all to ignore existing h_underpass values/statuses.")
        return 0

    print(f"Loaded {len(records)} pending underpasses from {args.table}")
    print(f"Loading street-lidar tile index from {args.index}")
    tile_index: TileIndex | None = None
    if args.batch_workers == 1:
        tile_index = load_tile_index(args.index, args.pointcloud_root, args.index_layer)
        tile_count = len(tile_index.tiles)
    else:
        tile_count = count_tile_index_records(args.index, args.index_layer)
    print(f"Loaded {tile_count} street-lidar tile footprints")

    record_batches = spatial_batches(records, args.grid_cell_size, args.batch_size)
    print(
        f"Built {len(record_batches)} spatial batches "
        f"using {args.grid_cell_size:g} m grid cells and max {args.batch_size} underpasses per batch"
    )
    print(f"LAZ backend: {args.laz_backend}; decompression: {args.decompression}")
    if args.crop_output_dir is not None:
        source_decompression = "all" if args.write_cropped else args.decompression
        print(
            f"Cropped point cloud cache: {args.crop_output_dir} "
            f"(reuse={args.reuse_cropped}, write={args.write_cropped}, "
            f"source_decompression={source_decompression})"
        )
    print(f"Batch workers: {args.batch_workers}")
    print(f"Point-in-polygon workers per batch: {args.pip_workers}")
    print(f"Height estimation workers per batch: {args.height_workers}")
    if args.batch_workers > 1 and (args.pip_workers > 1 or args.height_workers > 1):
        print(
            "Note: --pip-workers and --height-workers are per batch worker; "
            "reduce them if CPU oversubscribes."
        )
    if args.batch_workers > 1 and args.laz_backend == "lazrs-parallel":
        print(
            "Note: lazrs-parallel also uses Rayon threads per batch worker. "
            "Consider RAYON_NUM_THREADS or --laz-backend lazrs when tuning."
    )
    update_conn = None
    total_counts: Counter[str] = Counter()
    run_t0 = time.perf_counter()
    try:
        if args.batch_workers == 1:
            if tile_index is None:
                raise RuntimeError("Tile index was not loaded")
            if not args.dry_run:
                update_conn = connect_db(args)
            for batch_index, batch in enumerate(record_batches, start=1):
                t0 = time.perf_counter()
                results, timing = process_batch(batch.records, tile_index, args)
                batch_result = BatchWorkerResult(
                    batch_index=batch_index,
                    results=results,
                    timing=timing,
                    elapsed_s=time.perf_counter() - t0,
                )
                consume_batch_result(
                    len(record_batches),
                    batch,
                    batch_result,
                    update_conn,
                    args,
                    total_counts,
                )
        else:
            with ProcessPoolExecutor(
                max_workers=args.batch_workers,
                initializer=init_batch_worker,
                initargs=(args,),
            ) as executor:
                future_to_batch = {
                    executor.submit(process_batch_worker, batch_index, batch): batch
                    for batch_index, batch in enumerate(record_batches, start=1)
                }
                if not args.dry_run:
                    update_conn = connect_db(args)
                for future in as_completed(future_to_batch):
                    batch = future_to_batch[future]
                    batch_result = future.result()
                    consume_batch_result(
                        len(record_batches),
                        batch,
                        batch_result,
                        update_conn,
                        args,
                        total_counts,
                    )
    finally:
        if update_conn is not None:
            update_conn.close()

    total_statuses = ", ".join(f"{status}={count}" for status, count in sorted(total_counts.items()))
    print(f"Done: {total_statuses}; wall_elapsed={time.perf_counter() - run_t0:.1f}s")
    if args.dry_run:
        print("Dry run only; PostGIS was not updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
