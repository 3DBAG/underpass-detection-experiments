#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterable

import fiona
import laspy
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from zigpip import PreparedRing

POLYGON_BUFFER_DISTANCE = -0.2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crop a LAS/LAZ file into one output per polygon feature.")
    parser.add_argument("input_las", nargs="+", type=Path, help="One or more input LAS/LAZ point clouds")
    parser.add_argument("input_polygons", type=Path, help="Input polygon layer (GeoPackage)")
    parser.add_argument("output_dir", type=Path, help="Output directory for cropped point clouds")
    parser.add_argument("--layer", default=None, help="Feature layer name inside the GeoPackage")
    parser.add_argument("--id-field", default="identificatie", help="Feature attribute used in output file names")
    parser.add_argument("--resolution", type=int, default=64, help="Prepared grid resolution per ring")
    parser.add_argument("--chunk-size", type=int, default=1_000_000, help="LAS reader chunk size")
    parser.add_argument("--reproject-polygons", action="store_true", help="Reproject polygons into the LAS CRS when both CRS definitions are available")
    parser.add_argument("--output-extension", default=".laz", help="Output suffix, usually .laz or .las")
    return parser.parse_args()


@dataclass
class TimingStats:
    feature_transform_s: float = 0.0
    feature_buffer_s: float = 0.0
    feature_prepare_s: float = 0.0
    feature_write_gpkg_s: float = 0.0
    chunk_coord_extract_s: float = 0.0
    chunk_feature_cull_s: float = 0.0
    pip_select_s: float = 0.0
    point_write_s: float = 0.0
    chunks: int = 0
    active_features_total: int = 0
    active_features_max: int = 0
    feature_tests: int = 0
    feature_candidate_points_total: int = 0
    feature_hits_total: int = 0
    component_tests: int = 0
    component_candidate_points_total: int = 0
    component_hits_total: int = 0

    def total_feature_prep_s(self) -> float:
        return self.feature_transform_s + self.feature_buffer_s + self.feature_prepare_s + self.feature_write_gpkg_s

    def total_crop_s(self) -> float:
        return self.chunk_coord_extract_s + self.chunk_feature_cull_s + self.pip_select_s + self.point_write_s

    def avg_active_features_per_chunk(self) -> float:
        return self.active_features_total / self.chunks if self.chunks else 0.0

    def avg_feature_candidates_per_test(self) -> float:
        return self.feature_candidate_points_total / self.feature_tests if self.feature_tests else 0.0

    def avg_component_candidates_per_test(self) -> float:
        return self.component_candidate_points_total / self.component_tests if self.component_tests else 0.0


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "polygon"


def las_crs(path: Path) -> CRS | None:
    with laspy.open(path) as reader:
        try:
            parsed = reader.header.parse_crs()
        except Exception:
            return None
    return CRS.from_user_input(parsed) if parsed else None


def crs_equal(lhs: CRS | None, rhs: CRS | None) -> bool:
    if lhs is None or rhs is None:
        return lhs is rhs
    return lhs == rhs


def validate_input_headers(paths: list[Path]) -> tuple[laspy.LasHeader, CRS | None]:
    if not paths:
        raise RuntimeError("At least one input LAS/LAZ file is required")

    with laspy.open(paths[0]) as reader:
        base_header = reader.header.copy()
        base_crs = las_crs(paths[0])

    for path in paths[1:]:
        with laspy.open(path) as reader:
            header = reader.header
            crs = las_crs(path)

            if header.version != base_header.version:
                raise RuntimeError(f"Incompatible LAS version for {path}: expected {base_header.version}, got {header.version}")
            if header.point_format.id != base_header.point_format.id:
                raise RuntimeError(
                    f"Incompatible point format for {path}: expected {base_header.point_format.id}, got {header.point_format.id}"
                )
            if not crs_equal(crs, base_crs):
                raise RuntimeError(
                    f"Incompatible CRS for {path}: expected {base_crs.to_string() if base_crs else 'unknown'}, "
                    f"got {crs.to_string() if crs else 'unknown'}"
                )

    return base_header, base_crs


def source_crs(collection: fiona.Collection) -> CRS | None:
    if collection.crs_wkt:
        return CRS.from_wkt(collection.crs_wkt)
    if collection.crs:
        return CRS.from_user_input(collection.crs)
    return None


def iter_polygons(geometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms
    else:
        raise TypeError(f"Expected Polygon or MultiPolygon, got {geometry.geom_type}")


def polygonal_geometry(geometry) -> Polygon | MultiPolygon:
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry

    geoms = getattr(geometry, "geoms", None)
    if geoms is None:
        raise TypeError(f"Expected polygonal geometry, got {geometry.geom_type}")

    polygons = [geom for geom in geoms if isinstance(geom, Polygon) and not geom.is_empty]
    if not polygons:
        raise TypeError(f"Expected polygonal geometry, got {geometry.geom_type}")
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def buffer_polygon_outer_ring(polygon: Polygon, distance: float) -> Polygon | MultiPolygon | None:
    buffered_shell = Polygon(polygon.exterior).buffer(distance)
    if buffered_shell.is_empty:
        return None

    holes = [Polygon(ring) for ring in polygon.interiors]
    if holes:
        buffered_shell = buffered_shell.difference(MultiPolygon(holes))
        if buffered_shell.is_empty:
            return None

    return polygonal_geometry(buffered_shell)


def buffer_outer_rings(geometry: Polygon | MultiPolygon, distance: float) -> Polygon | MultiPolygon:
    buffered_parts: list[Polygon] = []
    for polygon in iter_polygons(geometry):
        buffered = buffer_polygon_outer_ring(polygon, distance)
        if buffered is None:
            continue
        buffered_parts.extend(iter_polygons(buffered))

    if not buffered_parts:
        raise ValueError("Buffered geometry is empty")
    if len(buffered_parts) == 1:
        return buffered_parts[0]
    return MultiPolygon(buffered_parts)


@dataclass
class PreparedComponent:
    bbox: tuple[float, float, float, float]
    shell: PreparedRing
    holes: list[PreparedRing]

    def close(self) -> None:
        self.shell.close()
        for hole in self.holes:
            hole.close()

    def contains_indexed(self, xs: np.ndarray, ys: np.ndarray, indices: np.ndarray, timing: TimingStats) -> np.ndarray:
        timing.component_tests += 1
        timing.component_candidate_points_total += int(indices.size)
        inside = self.shell.contains_indexed(xs, ys, indices)
        if not inside.any():
            return inside

        if self.holes:
            remaining_idx = indices[inside]
            remaining_local = np.flatnonzero(inside)

            for hole in self.holes:
                in_hole = hole.contains_indexed(xs, ys, remaining_idx)
                if in_hole.any():
                    inside[remaining_local[in_hole]] = False
                    keep = ~in_hole
                    remaining_idx = remaining_idx[keep]
                    remaining_local = remaining_local[keep]
                    if remaining_idx.size == 0:
                        break

        timing.component_hits_total += int(inside.sum())
        return inside


@dataclass
class PreparedFeature:
    identifier: str
    bbox: tuple[float, float, float, float]
    components: list[PreparedComponent]
    output_path: Path
    polygon_path: Path

    def close(self) -> None:
        for component in self.components:
            component.close()

    def select_indices(self, xs: np.ndarray, ys: np.ndarray, timing: TimingStats) -> np.ndarray:
        timing.feature_tests += 1
        minx, miny, maxx, maxy = self.bbox
        bbox_mask = (xs >= minx) & (xs <= maxx) & (ys >= miny) & (ys <= maxy)
        if not bbox_mask.any():
            return np.empty(0, dtype=np.int64)

        candidate_idx = np.flatnonzero(bbox_mask)
        timing.feature_candidate_points_total += int(candidate_idx.size)
        hit = np.zeros(candidate_idx.shape, dtype=bool)

        for component in self.components:
            pending_idx = np.flatnonzero(~hit)
            if pending_idx.size == 0:
                break
            pending_abs = candidate_idx[pending_idx]
            comp_hit = component.contains_indexed(xs, ys, pending_abs, timing)
            if comp_hit.any():
                hit[pending_idx[comp_hit]] = True

        result = candidate_idx[hit]
        timing.feature_hits_total += int(result.size)
        return result


def prepare_feature(geometry, identifier: str, output_path: Path, resolution: int) -> PreparedFeature:
    components: list[PreparedComponent] = []
    for polygon in iter_polygons(geometry):
        shell = PreparedRing(np.asarray(polygon.exterior.coords), resolution=resolution)
        holes = [PreparedRing(np.asarray(ring.coords), resolution=resolution) for ring in polygon.interiors]
        components.append(PreparedComponent(bbox=polygon.bounds, shell=shell, holes=holes))

    return PreparedFeature(
        identifier=identifier,
        bbox=geometry.bounds,
        components=components,
        output_path=output_path,
        polygon_path=output_path.with_suffix(".gpkg"),
    )


def write_feature_gpkg(
    path: Path,
    layer_name: str,
    geometry,
    properties: dict,
    property_schema: dict,
    crs: CRS | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = {
        "geometry": geometry.geom_type,
        "properties": property_schema,
    }
    with fiona.open(
        path,
        mode="w",
        driver="GPKG",
        layer=layer_name,
        schema=schema,
        crs_wkt=crs.to_wkt() if crs else None,
    ) as dst:
        dst.write(
            {
                "geometry": mapping(geometry),
                "properties": properties,
            }
        )


def load_features(
    polygon_path: Path,
    layer: str | None,
    id_field: str,
    resolution: int,
    output_dir: Path,
    output_extension: str,
    target_crs: CRS | None,
    reproject: bool,
    timing: TimingStats,
) -> tuple[list[PreparedFeature], str, CRS | None]:
    layers = fiona.listlayers(polygon_path)
    if not layers:
        raise RuntimeError(f"No layers found in {polygon_path}")

    selected_layer = layer or layers[0]
    if selected_layer not in layers:
        raise RuntimeError(f"Layer {selected_layer!r} not found. Available layers: {', '.join(layers)}")

    prepared: list[PreparedFeature] = []
    used_paths: set[Path] = set()

    with fiona.open(polygon_path, layer=selected_layer) as src:
        polygon_crs = source_crs(src)
        output_crs = target_crs if target_crs and polygon_crs and target_crs != polygon_crs and reproject else polygon_crs
        transform_fn = None

        if target_crs and polygon_crs and target_crs != polygon_crs:
            if not reproject:
                raise RuntimeError(
                    f"CRS mismatch: polygons are {polygon_crs.to_string()} while LAS is {target_crs.to_string()}. "
                    "Pass --reproject-polygons to transform polygons into the LAS CRS."
                )
            transformer = Transformer.from_crs(polygon_crs, target_crs, always_xy=True)
            transform_fn = transformer.transform

        for feature in src:
            if not feature.get("geometry"):
                continue

            geometry = shape(feature["geometry"])
            if geometry.is_empty:
                continue

            if transform_fn is not None:
                t0 = perf_counter()
                geometry = transform(transform_fn, geometry)
                timing.feature_transform_s += perf_counter() - t0

            geometry = polygonal_geometry(geometry)
            try:
                t0 = perf_counter()
                geometry = buffer_outer_rings(geometry, POLYGON_BUFFER_DISTANCE)
                timing.feature_buffer_s += perf_counter() - t0
            except ValueError:
                continue

            raw_id = feature["properties"].get(id_field) if feature.get("properties") else None
            identifier = str(raw_id or feature.get("id") or f"feature_{len(prepared)}")
            filename = sanitize_filename(identifier)
            output_path = output_dir / f"{filename}{output_extension}"
            polygon_output_path = output_dir / f"{filename}.gpkg"

            suffix = 1
            while output_path in used_paths:
                output_path = output_dir / f"{filename}_{suffix}{output_extension}"
                polygon_output_path = output_dir / f"{filename}_{suffix}.gpkg"
                suffix += 1
            used_paths.add(output_path)

            t0 = perf_counter()
            prepared_feature = prepare_feature(geometry, identifier, output_path, resolution)
            timing.feature_prepare_s += perf_counter() - t0
            prepared_feature.polygon_path = polygon_output_path
            t0 = perf_counter()
            write_feature_gpkg(
                path=prepared_feature.polygon_path,
                layer_name=selected_layer,
                geometry=geometry,
                properties=dict(feature["properties"] or {}),
                property_schema=dict(src.schema["properties"]),
                crs=output_crs,
            )
            timing.feature_write_gpkg_s += perf_counter() - t0
            prepared.append(prepared_feature)

        return prepared, selected_layer, polygon_crs


def crop_point_cloud(
    input_las_paths: list[Path],
    base_header: laspy.LasHeader,
    features: list[PreparedFeature],
    chunk_size: int,
    timing: TimingStats,
) -> dict[str, int]:
    counts = [0] * len(features)
    writers: list[laspy.LasWriter] = []
    feature_minx = np.fromiter((feature.bbox[0] for feature in features), dtype=np.float64, count=len(features))
    feature_miny = np.fromiter((feature.bbox[1] for feature in features), dtype=np.float64, count=len(features))
    feature_maxx = np.fromiter((feature.bbox[2] for feature in features), dtype=np.float64, count=len(features))
    feature_maxy = np.fromiter((feature.bbox[3] for feature in features), dtype=np.float64, count=len(features))

    try:
        for feature in features:
            writers.append(laspy.open(feature.output_path, mode="w", header=base_header.copy()))

        for input_las in input_las_paths:
            with laspy.open(input_las) as reader:
                for chunk in reader.chunk_iterator(chunk_size):
                    timing.chunks += 1
                    t0 = perf_counter()
                    xs = np.asarray(chunk.x, dtype=np.float64)
                    ys = np.asarray(chunk.y, dtype=np.float64)
                    timing.chunk_coord_extract_s += perf_counter() - t0

                    t0 = perf_counter()
                    chunk_minx = float(xs.min())
                    chunk_miny = float(ys.min())
                    chunk_maxx = float(xs.max())
                    chunk_maxy = float(ys.max())
                    active_feature_idx = np.flatnonzero(
                        (feature_minx <= chunk_maxx)
                        & (feature_maxx >= chunk_minx)
                        & (feature_miny <= chunk_maxy)
                        & (feature_maxy >= chunk_miny)
                    )
                    active_count = int(active_feature_idx.size)
                    timing.active_features_total += active_count
                    timing.active_features_max = max(timing.active_features_max, active_count)
                    timing.chunk_feature_cull_s += perf_counter() - t0

                    for feature_idx in active_feature_idx:
                        feature = features[int(feature_idx)]
                        t0 = perf_counter()
                        selected_idx = feature.select_indices(xs, ys, timing)
                        timing.pip_select_s += perf_counter() - t0
                        if selected_idx.size == 0:
                            continue

                        t0 = perf_counter()
                        writers[int(feature_idx)].write_points(chunk[selected_idx])
                        timing.point_write_s += perf_counter() - t0
                        counts[int(feature_idx)] += int(selected_idx.size)
    finally:
        for writer in writers:
            writer.close()

    return {feature.identifier: count for feature, count in zip(features, counts, strict=True)}


def main(args: argparse.Namespace) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_extension = args.output_extension if args.output_extension.startswith(".") else f".{args.output_extension}"
    timing = TimingStats()

    base_header, point_cloud_crs = validate_input_headers(args.input_las)
    features, layer_name, polygon_crs = load_features(
        polygon_path=args.input_polygons,
        layer=args.layer,
        id_field=args.id_field,
        resolution=args.resolution,
        output_dir=args.output_dir,
        output_extension=output_extension,
        target_crs=point_cloud_crs,
        reproject=args.reproject_polygons,
        timing=timing,
    )

    if not features:
        raise RuntimeError("No polygon features were prepared")

    try:
        counts = crop_point_cloud(args.input_las, base_header, features, args.chunk_size, timing)
    finally:
        for feature in features:
            feature.close()

    print(f"Prepared {len(features)} features from layer {layer_name!r}")
    print(f"Input point clouds: {len(args.input_las)}")
    print(f"Polygon CRS: {polygon_crs.to_string() if polygon_crs else 'unknown'}")
    print(f"LAS CRS: {point_cloud_crs.to_string() if point_cloud_crs else 'unknown'}")
    print(
        "Timings (s): "
        f"feature_prep={timing.total_feature_prep_s():.3f} "
        f"[transform={timing.feature_transform_s:.3f}, "
        f"buffer={timing.feature_buffer_s:.3f}, "
        f"prepare={timing.feature_prepare_s:.3f}, "
        f"write_gpkg={timing.feature_write_gpkg_s:.3f}] "
        f"crop={timing.total_crop_s():.3f} "
        f"[coords={timing.chunk_coord_extract_s:.3f}, "
        f"feature_cull={timing.chunk_feature_cull_s:.3f}, "
        f"pip={timing.pip_select_s:.3f}, "
        f"write={timing.point_write_s:.3f}]"
    )
    print(
        "Counters: "
        f"chunks={timing.chunks} "
        f"active_features_total={timing.active_features_total} "
        f"active_features_avg={timing.avg_active_features_per_chunk():.2f} "
        f"active_features_max={timing.active_features_max} "
        f"feature_tests={timing.feature_tests} "
        f"feature_candidates_total={timing.feature_candidate_points_total} "
        f"feature_candidates_avg={timing.avg_feature_candidates_per_test():.1f} "
        f"feature_hits_total={timing.feature_hits_total} "
        f"component_tests={timing.component_tests} "
        f"component_candidates_total={timing.component_candidate_points_total} "
        f"component_candidates_avg={timing.avg_component_candidates_per_test():.1f} "
        f"component_hits_total={timing.component_hits_total}"
    )
    for feature in features:
        print(f"{feature.identifier}: {counts[feature.identifier]} points -> {feature.output_path}; polygon -> {feature.polygon_path}")

    return 0


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(args))
