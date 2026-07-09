# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Concatenate .city.jsonl files from a single tile directory into one file.

The output file is named after the source directory and placed in the output
directory. The first line is the contents of metadata.json from the input root
(parent of the source directory), serialized as a single JSON line.

Intended to be called once per source subdirectory, parallelized with GNU parallel.
For the reconstruction layout, emit only tile directories:

    find input_dir/reconstruction -mindepth 3 -maxdepth 3 -type d \\
        | parallel python concat_cityjsonl.py input_dir {} /path/to/output_dir

A source directory at input_dir/x/y/z produces output_dir/x-y-z.city.jsonl.

For reconstruction outputs laid out as input_dir/reconstruction/z/x/y/objects/*
the z/x/y tile directory is the unit of work. Files below its objects subtree are
concatenated into input_dir/reconstruction-z-x-y.city.jsonl, and deeper
directories visited by find are skipped.
"""

import argparse
import json
import sys
from pathlib import Path


def is_in_objects_subtree(relative: Path) -> bool:
    return "objects" in relative.parts


def is_reconstruction_tile_dir(source_dir: Path, relative: Path) -> bool:
    return (
        len(relative.parts) >= 4
        and relative.parts[0] == "reconstruction"
        and (source_dir / "objects").is_dir()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_root",
        type=Path,
        help="Root input directory containing metadata.json.",
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Directory containing .city.jsonl files to concatenate.",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Flat output directory (sibling of the input root).",
    )
    args = parser.parse_args(argv)

    input_root: Path = args.input_root.resolve()
    source_dir: Path = args.source_dir.resolve()
    output_dir: Path = args.output_dir.resolve()

    if not source_dir.is_dir():
        print(f"error: not a directory: {source_dir}", file=sys.stderr)
        return 1

    metadata_path = input_root / "metadata.json"

    if not metadata_path.is_file():
        print(f"error: metadata.json not found in {input_root}", file=sys.stderr)
        return 1

    relative = source_dir.relative_to(input_root)

    if is_in_objects_subtree(relative):
        return 0

    if is_reconstruction_tile_dir(source_dir, relative):
        source_files = sorted((source_dir / "objects").rglob("*.city.jsonl"))
    else:
        source_files = sorted(source_dir.glob("*.city.jsonl"))

    if not source_files:
        if relative.parts and relative.parts[0] == "reconstruction":
            return 0
        print(f"warning: no .city.jsonl files in {source_dir}", file=sys.stderr)
        return 0

    stem = "-".join(relative.parts)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{stem}.city.jsonl"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    with output_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps(metadata, separators=(",", ":")))
        out.write("\n")
        for source_file in source_files:
            content = source_file.read_text(encoding="utf-8")
            if content and not content.endswith("\n"):
                content += "\n"
            out.write(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
