#!/usr/bin/env python3

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_report(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current_polygon = ""
    number_re = re.compile(r"^-?\d+(?:\.\d+)?$")

    for raw_line in path.read_text().splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("Benchmarking") or line.startswith("polygon") or line.startswith("-"):
            continue

        polygon = line[:24].strip()
        strategy = normalize_strategy(line[24:42].strip())
        rest = line[42:].split()
        if len(rest) != 3:
            continue

        if polygon:
            current_polygon = polygon
        if not current_polygon or not strategy:
            continue
        if not number_re.match(rest[0]):
            continue

        prep = None if rest[1] == "-" else float(rest[1])
        rows.append(
            {
                "polygon": current_polygon,
                "strategy": strategy,
                "ns": float(rest[0]),
                "prep_us": prep,
            }
        )

    return rows


def normalize_strategy(strategy: str) -> str:
    if strategy.startswith("C "):
        return strategy[2:].strip()
    return strategy


def rows_by_key(rows: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
    return {(row["polygon"], row["strategy"]): row for row in rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zig", required=True, type=Path)
    parser.add_argument("--c", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    zig_rows = parse_report(args.zig)
    c_rows = parse_report(args.c)
    zig_map = rows_by_key(zig_rows)
    c_map = rows_by_key(c_rows)

    common_keys = [key for key in zig_map if key in c_map]
    if not common_keys:
        raise SystemExit("no common benchmark rows found")

    polygon_order = []
    seen_polygons = set()
    for polygon, _ in common_keys:
        if polygon not in seen_polygons:
            polygon_order.append(polygon)
            seen_polygons.add(polygon)

    def strategy_rank(strategy: str) -> tuple[int, int]:
        if strategy == "naive":
            return (0, 0)
        match = re.match(r"grid res=(\d+)$", strategy)
        if match:
            return (1, int(match.group(1)))
        return (2, 0)

    common_keys.sort(key=lambda item: (polygon_order.index(item[0]), strategy_rank(item[1])))

    labels = [f"{polygon}\n{strategy}" for polygon, strategy in common_keys]
    zig_ns = [zig_map[key]["ns"] for key in common_keys]
    c_ns = [c_map[key]["ns"] for key in common_keys]

    prep_keys = [key for key in common_keys if zig_map[key]["prep_us"] is not None and c_map[key]["prep_us"] is not None]
    prep_labels = [f"{polygon}\n{strategy}" for polygon, strategy in prep_keys]
    zig_prep = [zig_map[key]["prep_us"] for key in prep_keys]
    c_prep = [c_map[key]["prep_us"] for key in prep_keys]

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(20, 24),
        constrained_layout=True,
        gridspec_kw={"height_ratios": [2.2, 1.8, 2.8]},
    )
    width = 0.42

    x = np.arange(len(labels))
    axes[0].bar(x - width / 2, c_ns, width, label="C", color="#4063D8")
    axes[0].bar(x + width / 2, zig_ns, width, label="Zig", color="#E07A1F")
    axes[0].set_title("Point-in-Polygon Benchmark Comparison")
    axes[0].set_ylabel("ns/query")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=60, ha="right")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend()

    px = np.arange(len(prep_labels))
    axes[1].bar(px - width / 2, c_prep, width, label="C", color="#4063D8")
    axes[1].bar(px + width / 2, zig_prep, width, label="Zig", color="#E07A1F")
    axes[1].set_title("Grid Preprocess Cost")
    axes[1].set_ylabel("prep (us)")
    axes[1].set_xticks(px)
    axes[1].set_xticklabels(prep_labels, rotation=60, ha="right")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend()

    axes[2].axis("off")
    table_rows = []
    for key in common_keys:
        c_ns_val = float(c_map[key]["ns"])
        zig_ns_val = float(zig_map[key]["ns"])
        speedup = c_ns_val / zig_ns_val
        table_rows.append(
            [
                key[0],
                key[1],
                f"{c_ns_val:.1f}",
                f"{zig_ns_val:.1f}",
                f"{speedup:.2f}x",
            ]
        )

    table = axes[2].table(
        cellText=table_rows,
        colLabels=["Polygon", "Strategy", "C ns/query", "Zig ns/query", "Speedup"],
        cellLoc="center",
        colLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.35)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#E8ECF7")
        elif col == 4:
            cell.set_facecolor("#FCE6D5")
    axes[2].set_title("Query Timing Table", pad=18)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=180)


if __name__ == "__main__":
    main()
