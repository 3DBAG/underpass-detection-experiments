#!/usr/bin/env python3

import argparse
import statistics
from pathlib import Path


def parse_report(path: Path) -> tuple[str, list[tuple[str, str, float, str | float, int]]]:
    title = ""
    rows: list[tuple[str, str, float, str | float, int]] = []
    current_polygon = ""

    for raw_line in path.read_text().splitlines():
        line = raw_line.rstrip()
        if line.startswith("Benchmarking"):
            title = line
            continue
        if not line or line.startswith("polygon") or line.startswith("-"):
            continue

        polygon = line[:24].strip()
        strategy = line[24:42].strip()
        parts = line[42:].split()
        if len(parts) != 3:
            continue

        if polygon:
            current_polygon = polygon
        if not current_polygon:
            continue

        ns = float(parts[0])
        prep = parts[1] if parts[1] == "-" else float(parts[1])
        inside = int(parts[2])
        rows.append((current_polygon, strategy, ns, prep, inside))

    return title, rows


def format_report(title: str, rows: list[tuple[str, str, float, str | float, int]]) -> str:
    out = [
        title,
        f"{'polygon':<24} {'strategy':<18} {'ns/query':>14}  {'prep (us)':>10}  inside",
        "-" * 86,
    ]

    last_polygon = None
    for polygon, strategy, ns, prep, inside in rows:
        label = polygon if polygon != last_polygon else ""
        prep_text = prep if isinstance(prep, str) else f"{prep:.1f}"
        out.append(f"{label:<24} {strategy:<18} {ns:>14.1f}  {prep_text:>10}  {inside}")
        last_polygon = polygon
    out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    parsed = [parse_report(path) for path in args.inputs]
    titles = {title for title, _ in parsed}
    if len(titles) != 1:
        raise SystemExit("benchmark inputs do not share the same title")

    row_sets = [rows for _, rows in parsed]
    first_rows = row_sets[0]
    for rows in row_sets[1:]:
        if len(rows) != len(first_rows):
            raise SystemExit("benchmark inputs have different row counts")

    merged: list[tuple[str, str, float, str | float, int]] = []
    for idx, first in enumerate(first_rows):
        polygon, strategy, _, prep, inside = first
        samples = [rows[idx] for rows in row_sets]
        if any((row[0], row[1], row[3], row[4]) != (polygon, strategy, prep, inside) for row in samples):
            prep_values = [row[3] for row in samples]
            if any((row[0], row[1], row[4]) != (polygon, strategy, inside) for row in samples):
                raise SystemExit("benchmark inputs have mismatched row layouts")
            if any((value == "-") != (prep == "-") for value in prep_values):
                raise SystemExit("benchmark inputs mix numeric and '-' preprocess values")
        median_ns = statistics.median(row[2] for row in samples)
        median_prep = prep if prep == "-" else statistics.median(float(row[3]) for row in samples)
        merged.append((polygon, strategy, median_ns, median_prep, inside))

    args.out.write_text(format_report(next(iter(titles)), merged))


if __name__ == "__main__":
    main()
