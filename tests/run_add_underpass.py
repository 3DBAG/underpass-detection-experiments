# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "psutil",
# ]
# ///
"""Run add_underpass on a single .city.jsonl file and record runtime metrics.

Designed to be called by GNU parallel, one invocation per input file.

Sub-commands
------------
run
    Process one file, write {log_dir}/{stem}.json (metrics) and
    {log_dir}/{stem}.log (combined stdout+stderr of add_underpass).

aggregate
    Read all *.json files from log_dir and write a summary CSV.

Typical GNU parallel invocation:
    ls /data/input/*.city.jsonl | \\
      parallel uv run run_add_underpass.py run \\
        --executable /path/to/add_underpass \\
        --input {} \\
        --output-dir /data/output \\
        --log-dir /data/logs

Aggregation:
    uv run run_add_underpass.py aggregate \\
      --log-dir /data/logs \\
      --output results.csv
"""

import argparse
import csv
import dataclasses
import datetime
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import psutil

# Prime psutil CPU measurement; first call always returns 0.0 (establishes baseline).
psutil.cpu_percent(interval=None)

HEIGHT_ATTR: str = "h_underpass_z_max"
ID_ATTR: str = "identificatie"
METHOD: str = "manifold"
DB_HOST: str = os.environ.get("UNDERPASS_DB_HOST", "localhost")
DB_PORT: str = os.environ.get("UNDERPASS_DB_PORT", "5432")
DB_NAME: str = os.environ.get("UNDERPASS_DB_NAME", "baseregisters")
DB_USER: str = os.environ.get("UNDERPASS_DB_USER", "rypeters")
DB_TABLE: str = os.environ.get("UNDERPASS_POLYGON_TABLE", "underpasses.extended_geometries_2")
CITY_JSONL_SUFFIX: str = ".city.jsonl"

CSV_FIELDNAMES: list[str] = [
    "file_name",
    "stem",
    "start_time",
    "wall_clock_seconds",
    "peak_rss_kb",
    "exit_code",
    "success",
    "cpu_percent_at_start",
    "load_avg_1min",
    "load_avg_5min",
    "load_avg_15min",
    "memory_total_mb",
    "memory_available_mb",
    "memory_percent",
    "disk_read_bytes_at_start",
    "disk_write_bytes_at_start",
    "log_file",
]


@dataclasses.dataclass
class SystemLoadSnapshot:
    cpu_percent_at_start: float
    load_avg_1min: float
    load_avg_5min: float
    load_avg_15min: float
    memory_total_mb: float
    memory_available_mb: float
    memory_percent: float
    disk_read_bytes_at_start: int
    disk_write_bytes_at_start: int


@dataclasses.dataclass
class RunResult:
    file_name: str
    stem: str
    start_time: str        # ISO 8601
    wall_clock_seconds: float
    peak_rss_kb: int
    exit_code: int
    success: bool
    log_file: str          # absolute path to .log file
    cpu_percent_at_start: float
    load_avg_1min: float
    load_avg_5min: float
    load_avg_15min: float
    memory_total_mb: float
    memory_available_mb: float
    memory_percent: float
    disk_read_bytes_at_start: int
    disk_write_bytes_at_start: int


def snapshot_system_load() -> SystemLoadSnapshot:
    """Capture a system resource snapshot immediately before subprocess launch."""
    cpu = psutil.cpu_percent(interval=None)
    load1, load5, load15 = os.getloadavg()
    mem = psutil.virtual_memory()
    io = psutil.disk_io_counters()
    return SystemLoadSnapshot(
        cpu_percent_at_start=cpu,
        load_avg_1min=load1,
        load_avg_5min=load5,
        load_avg_15min=load15,
        memory_total_mb=mem.total / 1_048_576,
        memory_available_mb=mem.available / 1_048_576,
        memory_percent=mem.percent,
        disk_read_bytes_at_start=io.read_bytes if io is not None else 0,
        disk_write_bytes_at_start=io.write_bytes if io is not None else 0,
    )


def build_command(executable: Path, input_file: Path, output_file: Path) -> list[str]:
    """Return the argv list for add_underpass."""
    ogr_source = (
        f"PG:dbname='{DB_NAME}' host={DB_HOST} port={DB_PORT} "
        f"user={DB_USER} tables={DB_TABLE}(geom)"
    )
    return [
        str(executable),
        ogr_source,
        str(input_file),
        str(output_file),
        HEIGHT_ATTR,
        ID_ATTR,
        METHOD,
    ]


def run_single(
    executable: Path,
    input_file: Path,
    output_dir: Path,
    log_dir: Path,
) -> RunResult:
    """Run add_underpass on one file, record metrics, return RunResult.

    Never raises on subprocess failure — failures are captured in RunResult.
    """
    stem = input_file.name.removesuffix(CITY_JSONL_SUFFIX)
    output_file = output_dir / input_file.name
    log_file = log_dir / f"{stem}.log"
    metrics_file = log_dir / f"{stem}.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    load = snapshot_system_load()
    start_time = datetime.datetime.now().isoformat()
    t0 = time.perf_counter()

    with log_file.open("w", encoding="utf-8") as log_fh:
        proc = subprocess.run(
            build_command(executable, input_file, output_file),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )

    wall_clock_seconds = time.perf_counter() - t0
    peak_rss_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss

    result = RunResult(
        file_name=input_file.name,
        stem=stem,
        start_time=start_time,
        wall_clock_seconds=wall_clock_seconds,
        peak_rss_kb=peak_rss_kb,
        exit_code=proc.returncode,
        success=proc.returncode == 0,
        log_file=str(log_file.resolve()),
        **dataclasses.asdict(load),
    )

    metrics_file.write_text(
        json.dumps(dataclasses.asdict(result), indent=2),
        encoding="utf-8",
    )

    if proc.returncode != 0:
        print(
            f"warning: add_underpass failed for {input_file.name} "
            f"(exit {proc.returncode}), see {log_file}",
            file=sys.stderr,
        )

    return result


def cmd_run(args: argparse.Namespace) -> int:
    executable: Path = args.executable.resolve()
    input_file: Path = args.input.resolve()

    if not executable.is_file():
        print(f"error: executable not found: {executable}", file=sys.stderr)
        return 1
    if not input_file.is_file():
        print(f"error: input file not found: {input_file}", file=sys.stderr)
        return 1

    run_single(executable, input_file, args.output_dir.resolve(), args.log_dir.resolve())
    return 0


def aggregate(log_dir: Path, output_csv: Path) -> int:
    """Read all *.json metric files from log_dir and write a summary CSV."""
    json_files = sorted(log_dir.glob("*.json"))
    if not json_files:
        print(f"warning: no *.json metric files in {log_dir}", file=sys.stderr)
        return 1

    records = []
    for path in json_files:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"warning: skipping {path.name}: {exc}", file=sys.stderr)

    if not records:
        print("error: no valid records found", file=sys.stderr)
        return 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_FIELDNAMES, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(records)

    print(f"wrote {len(records)} rows to {output_csv}")
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    if not args.log_dir.is_dir():
        print(f"error: not a directory: {args.log_dir}", file=sys.stderr)
        return 1
    return aggregate(args.log_dir.resolve(), args.output.resolve())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run add_underpass on a single .city.jsonl file.")
    p_run.add_argument("--executable", type=Path, required=True,
                       help="Full path to the add_underpass executable.")
    p_run.add_argument("--input", type=Path, required=True,
                       help="Path to the input .city.jsonl file.")
    p_run.add_argument("--output-dir", type=Path, required=True,
                       help="Directory for processed .city.jsonl output files.")
    p_run.add_argument("--log-dir", type=Path, required=True,
                       help="Directory for per-file .log and .json metric files.")
    p_run.set_defaults(func=cmd_run)

    p_agg = sub.add_parser("aggregate",
                            help="Aggregate per-file JSON metrics into a CSV.")
    p_agg.add_argument("--log-dir", type=Path, required=True,
                       help="Directory containing *.json metric files.")
    p_agg.add_argument("--output", type=Path, required=True,
                       help="Output CSV file path.")
    p_agg.set_defaults(func=cmd_aggregate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
