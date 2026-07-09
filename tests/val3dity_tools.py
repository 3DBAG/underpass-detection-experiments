#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Run val3dity, merge reports into CityJSON, and summarise reports."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


DEFAULT_INPUT_DIR = Path("/data2/rypeters/ams-run-06-30-rf/seq")
DEFAULT_REPORT_PATTERN = "*.val3dity.json"
EXTENSION_URL = "https://cityjson.github.io/extensions/val3dity/0.1.0/val3dity.ext.json"
EXTENSION_VERSION = "0.1.0"
REPORT_PROPERTY = "+val3dity-report"
VALIDATION_ATTRIBUTE = "+val3dity-validation"


def cityjson_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and (path.name.endswith(".city.jsonl") or path.name.endswith(".city.json"))
    )


def cityjson_stem(path: Path) -> str:
    if path.name.endswith(".city.jsonl"):
        return path.name.removesuffix(".city.jsonl")
    if path.name.endswith(".city.json"):
        return path.name.removesuffix(".city.json")
    return path.stem


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cityjson(path: Path) -> tuple[bool, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return False, json.loads(text)
    except json.JSONDecodeError:
        objects = [json.loads(line) for line in text.splitlines() if line.strip()]
        if not objects:
            raise ValueError(f"{path} is empty")
        return True, objects


def write_cityjson(path: Path, is_seq: bool, cityjson: Any, compact: bool) -> None:
    with path.open("w", encoding="utf-8") as out:
        if is_seq:
            for obj in cityjson:
                json.dump(obj, out, ensure_ascii=False, separators=(",", ":"))
                out.write("\n")
        elif compact:
            json.dump(cityjson, out, ensure_ascii=False, separators=(",", ":"))
            out.write("\n")
        else:
            json.dump(cityjson, out, ensure_ascii=False, indent=2)
            out.write("\n")


def scalar_parameters(parameters: Any) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return {}
    return {
        key: value
        for key, value in parameters.items()
        if isinstance(value, bool | int | float | str)
    }


def error_code_summary(report: dict[str, Any]) -> list[dict[str, int]]:
    counts: Counter[int] = Counter()
    for feature in iter_features(report):
        for error in iter_feature_errors(feature):
            code = error.get("code")
            if isinstance(code, int):
                counts[code] += 1
    return [{"code": code, "count": counts[code]} for code in sorted(counts)]


def convert_dataset_error(error: Any) -> dict[str, Any] | None:
    if isinstance(error, int):
        return {"code": error, "description": "UNKNOWN"}
    if not isinstance(error, dict) or "code" not in error:
        return None

    out = {"code": error["code"], "description": str(error.get("description", "UNKNOWN"))}
    if error.get("info"):
        out["info"] = str(error["info"])
    source_id = error.get("id") or error.get("sourceId") or error.get("source_id")
    if source_id:
        out["sourceId"] = str(source_id)
    return out


def convert_report(report: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "type": "type",
        "val3dity_version": "val3dityVersion",
        "input_file": "inputFile",
        "input_file_type": "inputFileType",
        "time": "time",
        "validity": "validity",
        "features_overview": "featuresOverview",
        "primitives_overview": "primitivesOverview",
        "all_errors": "allErrors",
    }
    out = {target: report[source] for source, target in key_map.items() if source in report}
    if "parameters" in report:
        out["parameters"] = scalar_parameters(report["parameters"])
    out["errorCodeSummary"] = error_code_summary(report)
    out["datasetErrors"] = [
        converted
        for converted in (convert_dataset_error(error) for error in report.get("dataset_errors", []))
        if converted is not None
    ]
    return out


def parse_int(value: str | None, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed >= 0 else default


def parse_source_id(source_id: str, fallback_city_object_id: str) -> dict[str, Any]:
    raw = {}
    for part in source_id.split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            raw[key] = value

    location: dict[str, Any] = {
        "cityObjectId": raw.get("coid", fallback_city_object_id),
        "geometryIndex": parse_int(raw.get("geom"), 0),
    }
    for source_key, target_key in {
        "shell": "shellIndex",
        "face": "faceIndex",
        "ring": "ringIndex",
        "vertex": "vertexIndex",
    }.items():
        value = parse_int(raw.get(source_key), None)
        if value is not None:
            location[target_key] = value
    return location


def convert_error(error: dict[str, Any], fallback_city_object_id: str) -> dict[str, Any]:
    source_id = str(error.get("id") or error.get("sourceId") or error.get("source_id") or "")
    out = {
        "code": error.get("code"),
        "description": str(error.get("description", "UNKNOWN")),
        "sourceId": source_id,
        "location": parse_source_id(source_id, fallback_city_object_id),
    }
    if error.get("info"):
        out["info"] = str(error["info"])
    return out


def build_validations(report: dict[str, Any], include_valid: bool) -> dict[str, dict[str, Any]]:
    pending: dict[str, dict[str, Any]] = {}

    for feature in iter_features(report):
        feature_id = str(feature.get("id", ""))
        errors = iter_feature_errors(feature)
        if not errors:
            if include_valid and feature_id:
                pending.setdefault(feature_id, {"validity": bool(feature.get("validity", True))})
            continue

        for error in errors:
            converted = convert_error(error, feature_id)
            location = converted["location"]
            city_object_id = location["cityObjectId"]
            geometry_index = location["geometryIndex"]
            record = pending.setdefault(
                city_object_id,
                {
                    "validity": False,
                    "_geometries": defaultdict(lambda: {"validity": False, "errors": []}),
                },
            )
            if feature_id and feature_id != city_object_id:
                record.setdefault("reportFeatureId", feature_id)
            record["_geometries"][geometry_index]["errors"].append(converted)

    return finalize_validations(pending)


def finalize_validations(pending: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    finalized = {}
    for city_object_id, record in pending.items():
        out = {key: value for key, value in record.items() if not key.startswith("_")}
        geometries = record.get("_geometries")
        if geometries:
            out["geometries"] = [
                {
                    "geometryIndex": geometry_index,
                    "validity": geometry["validity"],
                    "errors": geometry["errors"],
                }
                for geometry_index, geometry in sorted(geometries.items())
            ]
        finalized[city_object_id] = out
    return finalized


def add_report(root: dict[str, Any], report: dict[str, Any]) -> None:
    root.setdefault("extensions", {})["val3dity"] = {
        "url": EXTENSION_URL,
        "version": EXTENSION_VERSION,
    }
    root[REPORT_PROPERTY] = convert_report(report)


def attach_validations(
    cityobjects: dict[str, Any],
    validations: dict[str, dict[str, Any]],
    applied: set[str],
) -> None:
    for city_object_id, validation in validations.items():
        city_object = cityobjects.get(city_object_id)
        if city_object is None:
            continue
        city_object.setdefault("attributes", {})[VALIDATION_ATTRIBUTE] = validation
        applied.add(city_object_id)


def merge_report(
    report_path: Path,
    cityjson_path: Path,
    output_path: Path,
    *,
    include_valid: bool,
    compact: bool,
) -> tuple[int, list[str]]:
    report = load_json(report_path)
    if not isinstance(report, dict):
        raise ValueError(f"{report_path} is not a val3dity report object")

    is_seq, cityjson = load_cityjson(cityjson_path)
    validations = build_validations(report, include_valid)
    applied: set[str] = set()

    if is_seq:
        add_report(cityjson[0], report)
        for feature in cityjson:
            attach_validations(feature.get("CityObjects", {}), validations, applied)
    else:
        add_report(cityjson, report)
        attach_validations(cityjson.get("CityObjects", {}), validations, applied)

    write_cityjson(output_path, is_seq, cityjson, compact)
    return len(applied), sorted(set(validations) - applied)


def report_path_for(input_path: Path, report_dir: Path) -> Path:
    return report_dir / f"{cityjson_stem(input_path)}.val3dity.json"


def run_val3dity_one(
    input_path: Path,
    report_dir: Path,
    val3dity: str,
    *,
    quiet: bool,
) -> tuple[Path, bool, str]:
    report_path = report_path_for(input_path, report_dir)
    command = [val3dity, str(input_path), "--report", str(report_path)]
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return input_path, False, completed.stderr.strip()

    return input_path, True, ""


def run_command(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    report_dir = args.report_dir.resolve() if args.report_dir else input_dir
    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}", file=sys.stderr)
        return 1

    val3dity = args.val3dity or shutil.which("val3dity")
    if not val3dity:
        print("error: val3dity executable not found; pass --val3dity", file=sys.stderr)
        return 1

    inputs = cityjson_files(input_dir)
    if not inputs:
        print(f"error: no .city.jsonl or .city.json files found in {input_dir}", file=sys.stderr)
        return 1

    report_dir.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for report_path in report_dir.glob(DEFAULT_REPORT_PATTERN):
            report_path.unlink()

    print(f"input:      {input_dir} ({len(inputs)} files)")
    print(f"reports:    {report_dir}")
    print(f"val3dity:   {val3dity}")
    print(f"jobs:       {args.jobs}")
    print(f"clean:      {args.clean}")
    print(f"merge:      {args.merge}")

    failed = 0
    validated_inputs: list[Path] = []
    print("phase:      val3dity")
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [
            executor.submit(
                run_val3dity_one,
                input_path,
                report_dir,
                val3dity,
                quiet=args.quiet,
            )
            for input_path in inputs
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            input_path, ok, message = future.result()
            if ok:
                validated_inputs.append(input_path)
                if not args.quiet:
                    print(f"[{index}/{len(inputs)}] ok {input_path.name}")
                continue
            failed += 1
            print(f"[{index}/{len(inputs)}] failed {input_path.name}: {message}", file=sys.stderr)

    if failed:
        print(f"failed: {failed}", file=sys.stderr)
        return 1

    if args.merge:
        print("phase:      merge")
        failed = merge_paths(
            validated_inputs,
            report_dir,
            None,
            jobs=args.jobs,
            include_valid=args.include_valid,
            compact=args.compact,
            overwrite=True,
            quiet=args.quiet,
        )
        if failed:
            print(f"failed: {failed}", file=sys.stderr)
            return 1
    return 0


def merge_command(args: argparse.Namespace) -> int:
    output_path = args.cityjson if args.in_place else args.output
    if output_path is None:
        print("error: output is required unless --in-place is used", file=sys.stderr)
        return 1
    if args.in_place and args.output is not None:
        print("error: --in-place cannot be used with an explicit output path", file=sys.stderr)
        return 1
    if output_path.exists() and output_path != args.cityjson and not args.overwrite:
        print(f"error: {output_path} already exists; use --overwrite", file=sys.stderr)
        return 1

    applied, missing = merge_report(
        args.report,
        args.cityjson,
        output_path,
        include_valid=args.include_valid,
        compact=args.compact,
    )
    print(f"Wrote {output_path}")
    print(f"Attached {applied} val3dity validation attribute(s)")
    if missing:
        print(
            f"Warning: {len(missing)} reported CityObject id(s) were not found: "
            + ", ".join(missing[:10]),
            file=sys.stderr,
        )
        if len(missing) > 10:
            print("Warning: missing id list truncated", file=sys.stderr)
    return 0


def merge_dir_one(
    cityjson_path: Path,
    report_dir: Path,
    output_dir: Path | None,
    *,
    include_valid: bool,
    compact: bool,
    overwrite: bool,
) -> tuple[Path, bool, str]:
    report_path = report_path_for(cityjson_path, report_dir)
    if not report_path.is_file():
        return cityjson_path, False, f"report not found: {report_path}"

    output_path = output_dir / cityjson_path.name if output_dir else cityjson_path
    if output_path != cityjson_path and output_path.exists() and not overwrite:
        return output_path, False, "output exists; use --overwrite"

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merge_report(
            report_path,
            cityjson_path,
            output_path,
            include_valid=include_valid,
            compact=compact,
        )
    except Exception as exc:
        return cityjson_path, False, str(exc)

    return cityjson_path, True, ""


def merge_paths(
    inputs: list[Path],
    report_dir: Path,
    output_dir: Path | None,
    *,
    jobs: int,
    include_valid: bool,
    compact: bool,
    overwrite: bool,
    quiet: bool,
) -> int:
    failed = 0
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = [
            executor.submit(
                merge_dir_one,
                input_path,
                report_dir,
                output_dir,
                include_valid=include_valid,
                compact=compact,
                overwrite=overwrite,
            )
            for input_path in inputs
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            cityjson_path, ok, message = future.result()
            if ok:
                if not quiet:
                    print(f"[{index}/{len(inputs)}] ok {cityjson_path.name}")
                continue
            failed += 1
            print(f"[{index}/{len(inputs)}] failed {cityjson_path.name}: {message}", file=sys.stderr)
    return failed


def merge_dir_command(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    report_dir = args.report_dir.resolve() if args.report_dir else input_dir
    output_dir = args.output_dir.resolve() if args.output_dir else None

    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}", file=sys.stderr)
        return 1
    if not report_dir.is_dir():
        print(f"error: report directory not found: {report_dir}", file=sys.stderr)
        return 1
    if output_dir is not None and output_dir == input_dir:
        output_dir = None

    inputs = cityjson_files(input_dir)
    if not inputs:
        print(f"error: no .city.jsonl or .city.json files found in {input_dir}", file=sys.stderr)
        return 1

    print(f"input:      {input_dir} ({len(inputs)} files)")
    print(f"reports:    {report_dir}")
    print(f"output:     {output_dir if output_dir else 'in-place'}")
    print(f"jobs:       {args.jobs}")

    failed = merge_paths(
        inputs,
        report_dir,
        output_dir,
        jobs=args.jobs,
        include_valid=args.include_valid,
        compact=args.compact,
        overwrite=args.overwrite,
        quiet=args.quiet,
    )
    if failed:
        print(f"failed: {failed}", file=sys.stderr)
        return 1
    return 0


def iter_dataset_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    dataset_errors = report.get("dataset_errors", [])
    if isinstance(dataset_errors, list):
        return [error for error in dataset_errors if isinstance(error, dict)]
    return []


def iter_features(report: dict[str, Any]) -> list[dict[str, Any]]:
    features = report.get("features", [])
    if isinstance(features, list):
        return [feature for feature in features if isinstance(feature, dict)]
    return []


def iter_feature_errors(feature: dict[str, Any]) -> list[dict[str, Any]]:
    feature_errors = feature.get("errors", [])
    if isinstance(feature_errors, list):
        return [error for error in feature_errors if isinstance(error, dict)]
    return []


def code_sort_key(code: str) -> tuple[int, int | str]:
    try:
        return (0, int(code))
    except ValueError:
        return (1, code)


def summarise_command(args: argparse.Namespace) -> int:
    report_dir = args.report_dir.resolve()
    if not report_dir.is_dir():
        print(f"error: report directory not found: {report_dir}", file=sys.stderr)
        return 1

    report_paths = sorted(report_dir.glob(args.pattern))
    if not report_paths:
        print(f"error: no reports matching {args.pattern!r} found in {report_dir}", file=sys.stderr)
        return 1

    occurrence_counts: Counter[str] = Counter()
    object_counts: Counter[str] = Counter()
    descriptions: dict[str, str] = {}
    failed = 0
    total_objects = 0
    objects_with_errors = 0

    for report_path in report_paths:
        try:
            report = load_json(report_path)
        except (OSError, json.JSONDecodeError) as exc:
            failed += 1
            print(f"warning: failed to read {report_path}: {exc}", file=sys.stderr)
            continue

        if not isinstance(report, dict):
            failed += 1
            print(f"warning: report is not a JSON object: {report_path}", file=sys.stderr)
            continue

        for error in iter_dataset_errors(report):
            code = str(error.get("code", "UNKNOWN"))
            occurrence_counts[code] += 1
            description = error.get("description")
            if isinstance(description, str) and description:
                descriptions.setdefault(code, description)

        for feature in iter_features(report):
            total_objects += 1
            feature_errors = iter_feature_errors(feature)
            if feature_errors:
                objects_with_errors += 1

            feature_error_codes: set[str] = set()
            for error in feature_errors:
                code = str(error.get("code", "UNKNOWN"))
                occurrence_counts[code] += 1
                feature_error_codes.add(code)
                description = error.get("description")
                if isinstance(description, str) and description:
                    descriptions.setdefault(code, description)

            object_counts.update(feature_error_codes)

    print(f"reports: {len(report_paths)}")
    if failed:
        print(f"failed:  {failed}")
    print(f"objects: {total_objects}")
    if total_objects:
        object_error_percentage = objects_with_errors / total_objects * 100
        print(f"objects with errors: {objects_with_errors} ({object_error_percentage:.2f}%)")
    else:
        print("objects with errors: 0 (0.00%)")
    print(f"error occurrences: {occurrence_counts.total()}")

    if not occurrence_counts:
        return 0

    print()
    print(
        f"{'code':>6} {'occurrences':>12} {'objects':>10} "
        f"{'objects_%':>10} {'of_error_objects_%':>18}  description"
    )
    print(f"{'-' * 6} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 18}  {'-' * 11}")
    for code in sorted(occurrence_counts, key=code_sort_key):
        affected_objects = object_counts[code]
        object_percentage = affected_objects / total_objects * 100 if total_objects else 0
        error_object_percentage = (
            affected_objects / objects_with_errors * 100 if objects_with_errors else 0
        )
        print(
            f"{code:>6} {occurrence_counts[code]:>12} {affected_objects:>10} "
            f"{object_percentage:>9.2f}% {error_object_percentage:>17.2f}%  "
            f"{descriptions.get(code, '')}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run val3dity reports for CityJSON files")
    run_parser.add_argument("input_dir", nargs="?", type=Path, default=DEFAULT_INPUT_DIR)
    run_parser.add_argument("--report-dir", type=Path, help="Report directory (default: input_dir)")
    run_parser.add_argument("--jobs", type=int, default=32)
    run_parser.add_argument("--val3dity", help="Path to val3dity executable")
    run_parser.add_argument("--clean", action="store_true", help="Delete existing *.val3dity.json first")
    run_parser.add_argument(
        "--no-merge",
        dest="merge",
        action="store_false",
        help="Only write report JSON files; do not merge into CityJSON.",
    )
    run_parser.add_argument(
        "--include-valid",
        action="store_true",
        help="Also attach validity=true attributes for valid objects while merging.",
    )
    run_parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write merged normal CityJSON compactly (default: true).",
    )
    run_parser.add_argument("--quiet", action="store_true", help="Suppress val3dity stdout")
    run_parser.set_defaults(func=run_command, merge=True)

    merge_parser = subparsers.add_parser("merge", help="Merge one val3dity report into CityJSON")
    merge_parser.add_argument("report", type=Path)
    merge_parser.add_argument("cityjson", type=Path)
    merge_parser.add_argument("output", type=Path, nargs="?")
    merge_parser.add_argument("--in-place", action="store_true")
    merge_parser.add_argument("--overwrite", action="store_true")
    merge_parser.add_argument("--include-valid", action="store_true")
    merge_parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write normal CityJSON compactly (default: true).",
    )
    merge_parser.set_defaults(func=merge_command)

    merge_dir_parser = subparsers.add_parser(
        "merge-dir",
        help="Merge existing val3dity reports into every CityJSON file in a directory",
    )
    merge_dir_parser.add_argument("input_dir", type=Path)
    merge_dir_parser.add_argument("--report-dir", type=Path, help="Report directory (default: input_dir)")
    merge_dir_parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write merged CityJSON files here instead of modifying input files in place.",
    )
    merge_dir_parser.add_argument("--jobs", type=int, default=32)
    merge_dir_parser.add_argument("--overwrite", action="store_true")
    merge_dir_parser.add_argument("--include-valid", action="store_true")
    merge_dir_parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write normal CityJSON compactly (default: true).",
    )
    merge_dir_parser.add_argument("--quiet", action="store_true")
    merge_dir_parser.set_defaults(func=merge_dir_command)

    summarise_parser = subparsers.add_parser(
        "summarise",
        aliases=["summarize"],
        help="Summarise val3dity reports",
    )
    summarise_parser.add_argument("report_dir", nargs="?", type=Path, default=DEFAULT_INPUT_DIR)
    summarise_parser.add_argument("--pattern", default=DEFAULT_REPORT_PATTERN)
    summarise_parser.set_defaults(func=summarise_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {"run", "merge-dir"} and args.jobs < 1:
        parser.error("--jobs must be >= 1")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
