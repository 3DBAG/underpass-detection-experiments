#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Build a FlatGeobuf index of CityJSONSeq tile extents.

Each ``*.city.jsonl`` file below the input directory contributes one extent
polygon.  Its ``tile_id`` is the ``x-y-z`` suffix of its filename and its
``filepath`` is relative to the input directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator


DEFAULT_INPUT_DIR = Path("/data2/rypeters/ams-run-08-24-rf/seq_underpasses_manifold")
CITYJSONSEQ_SUFFIX = ".city.jsonl"
TILE_ID_RE = re.compile(r"(?P<tile_id>\d+-\d+-\d+)\.city\.jsonl$")


def cityjsonseq_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.rglob(f"*{CITYJSONSEQ_SUFFIX}") if path.is_file())


def tile_id_from_path(path: Path) -> str:
    match = TILE_ID_RE.search(path.name)
    if match is None:
        raise ValueError(
            f"filename does not end in an x-y-z tile ID: {path.name} "
            "(expected e.g. reconstruction-2-48-16.city.jsonl)"
        )
    return match.group("tile_id")


def epsg_from_reference_system(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"EPSG(?:/0)?[/:](\d+)$", value, re.IGNORECASE)
    return f"EPSG:{match.group(1)}" if match else None


def transformed_vertices(record: dict[str, Any], transform: dict[str, Any]) -> Iterator[tuple[float, float, float]]:
    vertices = record.get("vertices")
    if not isinstance(vertices, list):
        return
    scale = transform.get("scale")
    translate = transform.get("translate")
    if not (
        isinstance(scale, list)
        and isinstance(translate, list)
        and len(scale) >= 3
        and len(translate) >= 3
    ):
        raise ValueError("CityJSON transform must contain three scale and translate values")
    for vertex in vertices:
        if not isinstance(vertex, list) or len(vertex) < 3:
            continue
        if not all(isinstance(value, int | float) for value in vertex[:3]):
            continue
        yield tuple(float(vertex[i]) * float(scale[i]) + float(translate[i]) for i in range(3))


def tile_extent(path: Path) -> tuple[tuple[float, float, float, float], str | None]:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    transform: dict[str, Any] | None = None
    reference_system: str | None = None

    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(record, dict):
                continue
            if transform is None:
                candidate = record.get("transform")
                if isinstance(candidate, dict):
                    transform = candidate
                metadata = record.get("metadata")
                if isinstance(metadata, dict):
                    reference_system = epsg_from_reference_system(metadata.get("referenceSystem"))
            if transform is None:
                continue
            for x, y, _z in transformed_vertices(record, transform):
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if transform is None:
        raise ValueError("CityJSON transform is missing")
    if min_x == float("inf"):
        raise ValueError("no vertices found")
    return (min_x, min_y, max_x, max_y), reference_system


def feature(tile_id: str, filepath: Path, extent: tuple[float, float, float, float]) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = extent
    return {
        "type": "Feature",
        "properties": {"tile_id": tile_id, "filepath": filepath.as_posix()},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y], [min_x, min_y]]],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, nargs="?", default=DEFAULT_INPUT_DIR)
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output FlatGeobuf path (default: <input_dir>/tile_index.fgb).",
    )
    args = parser.parse_args(argv)

    input_dir = args.input_dir.resolve()
    output = (args.output or input_dir / "tile_index.fgb").resolve()
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        parser.error("ogr2ogr is required to write FlatGeobuf")

    features: list[dict[str, Any]] = []
    reference_systems: set[str] = set()
    failures = 0
    for path in cityjsonseq_files(input_dir):
        try:
            extent, reference_system = tile_extent(path)
            features.append(feature(tile_id_from_path(path), path.relative_to(input_dir), extent))
            if reference_system is not None:
                reference_systems.add(reference_system)
        except ValueError as exc:
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)
            failures += 1

    if not features:
        print(f"error: no tile extents produced from {input_dir}", file=sys.stderr)
        return 1
    if len(reference_systems) > 1:
        print(f"error: inconsistent reference systems: {', '.join(sorted(reference_systems))}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    # FlatGeobuf is a single-file dataset, but GDAL's -overwrite cannot replace
    # an existing FlatGeobuf layer reliably. Write a new file beside the target
    # and replace it only after GDAL has completed successfully.
    with tempfile.TemporaryDirectory(prefix="cityjson-tile-index-", dir=output.parent) as temporary_directory:
        geojson_path = Path(temporary_directory) / "tile_index.geojson"
        temporary_output = Path(temporary_directory) / "tile_index.fgb"
        geojson_path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
            encoding="utf-8",
        )
        command = [ogr2ogr, "-f", "FlatGeobuf", "-lco", "SPATIAL_INDEX=YES"]
        if reference_systems:
            command.extend(["-a_srs", reference_systems.pop()])
        command.extend([str(temporary_output), str(geojson_path)])
        subprocess.run(command, check=True)
        os.replace(temporary_output, output)

    print(f"Wrote {len(features)} tile extents to {output}")
    if failures:
        print(f"Skipped {failures} invalid tile file(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
