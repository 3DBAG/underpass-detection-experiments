#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from py3dtiles.constants import SpecVersion
from py3dtiles.convert import convert


DEFAULT_INPUT_DIR = Path("/data2/rypeters/amsterdam_data/2025/cropped")
DEFAULT_OUTPUT_DIR = DEFAULT_INPUT_DIR / "3dtiles-v1.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert cropped LAS/LAZ point clouds to a 3D Tiles 1.1 tileset."
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing cropped .las/.laz files. Defaults to {DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output 3D Tiles directory. Defaults to {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument("--jobs", type=int, default=128, help="py3dtiles worker count")
    parser.add_argument(
        "--cache-size",
        type=int,
        default=None,
        help="py3dtiles cache size in MB. Defaults to py3dtiles' own memory-based value.",
    )
    parser.add_argument("--srs-in", type=int, default=None, help="Override input EPSG code")
    parser.add_argument("--srs-out", type=int, default=None, help="Output EPSG code")
    parser.add_argument(
        "--force-srs-in",
        action="store_true",
        help="Force --srs-in even when input files declare a different CRS.",
    )
    parser.add_argument(
        "--pyproj-always-xy",
        action="store_true",
        help="Pass always_xy=True to pyproj when reprojecting.",
    )
    parser.add_argument(
        "--no-rgb",
        action="store_true",
        help="Do not export RGB attributes.",
    )
    parser.add_argument(
        "--extra-fields",
        nargs="+",
        default=None,
        help="Extra point fields to include. All input files must provide compatible fields.",
    )
    parser.add_argument(
        "--color-scale",
        type=float,
        default=None,
        help="Force color scale, for example 256 for RGB stored as 8-bit values in 16-bit LAS fields.",
    )
    parser.add_argument(
        "--disable-processpool",
        action="store_true",
        help="Disable py3dtiles' process pool when writing tiles.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output directory if it already exists.",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Only read LAS/LAZ files directly inside input_dir.",
    )
    parser.add_argument(
        "--glob",
        default=None,
        help="Custom glob pattern relative to input_dir, e.g. 'crops/*.laz'. Overrides default cropped-file discovery.",
    )
    parser.add_argument(
        "--all-point-clouds",
        action="store_true",
        help="Include every discovered .las/.laz file. By default only crop-cache names containing '__' are included.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Convert only the first N discovered files. Useful for smoke tests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print discovered inputs and output path without converting.",
    )
    parser.add_argument("--verbose", "-v", action="count", default=0)
    return parser.parse_args()


def discover_point_clouds(
    input_dir: Path,
    pattern: str | None,
    recursive: bool,
    cropped_only: bool,
) -> list[Path]:
    if pattern is not None:
        paths = input_dir.glob(pattern)
    elif recursive:
        paths = input_dir.rglob("*")
    else:
        paths = input_dir.glob("*")

    return sorted(
        path
        for path in paths
        if path.is_file() and path.suffix.lower() in {".las", ".laz"}
        and (not cropped_only or "__" in path.stem)
    )


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    out_dir = args.out.resolve()

    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    files = discover_point_clouds(
        input_dir,
        args.glob,
        recursive=not args.non_recursive,
        cropped_only=args.glob is None and not args.all_point_clouds,
    )
    files = [path for path in files if out_dir not in path.parents]

    if args.limit is not None:
        files = files[: args.limit]

    if not files:
        suffix = " matching crop-cache names containing '__'" if args.glob is None and not args.all_point_clouds else ""
        raise SystemExit(f"No .las/.laz files{suffix} found in {input_dir}")

    print(f"Input directory: {input_dir}")
    print(f"Point clouds: {len(files)}")
    if args.glob is None and not args.all_point_clouds:
        print("Input filter: crop-cache filenames containing '__'")
    print(f"Output tileset: {out_dir}")
    print("3D Tiles spec version: 1.1")
    if args.dry_run:
        for path in files[:20]:
            print(path)
        if len(files) > 20:
            print(f"... {len(files) - 20} more")
        return 0

    kwargs = {
        "files": files,
        "outfolder": out_dir,
        "overwrite": args.overwrite,
        "jobs": args.jobs,
        "crs_out": args.srs_out,
        "crs_in": args.srs_in,
        "force_crs_in": args.force_srs_in,
        "pyproj_always_xy": args.pyproj_always_xy,
        "rgb": not args.no_rgb,
        "extra_fields": args.extra_fields,
        "color_scale": args.color_scale,
        "use_process_pool": not args.disable_processpool,
        "verbose": args.verbose,
        "spec_version": SpecVersion.V1_1,
    }
    if args.cache_size is not None:
        kwargs["cache_size"] = args.cache_size

    convert(**kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
