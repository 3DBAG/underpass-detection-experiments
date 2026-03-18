import csv
import random
import sqlite3
import struct
from pathlib import Path


CSV_PATH = Path("underpass_heights.csv")
GPKG_PATH = Path("/Users/ravi/git/underpass-detection-experiments/modelling_3d/sample_data/demo_ams_underpasses.gpkg")
FEATURE_TABLE = "offset_polygons"
TARGET_COLUMN = "underpass_h"
SOURCE_COLUMN = "underpass_h_source"
RANDOM_MIN = 2.5
RANDOM_MAX = 3.5
RANDOM_SEED = 42


def gpkg_geometry_info(blob):
    if blob is None:
        return None

    blob = bytes(blob)
    if blob[:2] != b"GP":
        raise ValueError("Geometry blob is not in GeoPackage binary format")

    flags = blob[3]
    empty = bool(flags & 0b10000)
    envelope_indicator = (flags >> 1) & 0b111
    byte_order = "<" if (flags & 0b1) == 1 else ">"

    if empty:
        return {"is_empty": True, "bounds": None}

    envelope_sizes = {
        0: 0,
        1: 32,
        2: 48,
        3: 48,
        4: 64,
    }
    if envelope_indicator not in envelope_sizes:
        raise ValueError(f"Unsupported GeoPackage envelope type: {envelope_indicator}")

    if envelope_indicator == 0:
        raise ValueError("GeoPackage geometry is missing an envelope")

    min_x, max_x, min_y, max_y = struct.unpack(
        f"{byte_order}4d",
        blob[8:40],
    )
    return {"is_empty": False, "bounds": (min_x, min_y, max_x, max_y)}


def connect_gpkg(path):
    con = sqlite3.connect(path)

    def geometry_info_or_none(blob):
        if blob is None:
            return None
        return gpkg_geometry_info(blob)

    con.create_function(
        "ST_IsEmpty",
        1,
        lambda blob: int(
            geometry_info_or_none(blob) is not None and geometry_info_or_none(blob)["is_empty"]
        ),
    )
    con.create_function(
        "ST_MinX",
        1,
        lambda blob: None if geometry_info_or_none(blob) is None else geometry_info_or_none(blob)["bounds"][0],
    )
    con.create_function(
        "ST_MinY",
        1,
        lambda blob: None if geometry_info_or_none(blob) is None else geometry_info_or_none(blob)["bounds"][1],
    )
    con.create_function(
        "ST_MaxX",
        1,
        lambda blob: None if geometry_info_or_none(blob) is None else geometry_info_or_none(blob)["bounds"][2],
    )
    con.create_function(
        "ST_MaxY",
        1,
        lambda blob: None if geometry_info_or_none(blob) is None else geometry_info_or_none(blob)["bounds"][3],
    )
    return con


def load_underpass_values(csv_path):
    with csv_path.open(newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return {
            row["identificatie"]: float(row["underpass_h"])
            for row in reader
            if row.get("identificatie") and row.get("underpass_h")
        }


def ensure_real_column(con, table_name, column_name):
    columns = {
        row[1]: row[2].upper()
        for row in con.execute(f'pragma table_info("{table_name}")')
    }

    if column_name not in columns:
        con.execute(f'alter table "{table_name}" add column "{column_name}" REAL')
        return

    if columns[column_name] != "REAL":
        raise ValueError(
            f'Column "{column_name}" already exists in "{table_name}" with type {columns[column_name]!r}'
        )


def ensure_text_column(con, table_name, column_name):
    columns = {
        row[1]: row[2].upper()
        for row in con.execute(f'pragma table_info("{table_name}")')
    }

    if column_name not in columns:
        con.execute(f'alter table "{table_name}" add column "{column_name}" TEXT')
        return

    if columns[column_name] != "TEXT":
        raise ValueError(
            f'Column "{column_name}" already exists in "{table_name}" with type {columns[column_name]!r}'
        )


def merge_underpass_values(gpkg_path, underpass_values):
    rng = random.Random(RANDOM_SEED)

    with connect_gpkg(gpkg_path) as con:
        ensure_real_column(con, FEATURE_TABLE, TARGET_COLUMN)
        ensure_text_column(con, FEATURE_TABLE, SOURCE_COLUMN)

        rows = con.execute(
            f'select fid, identificatie from "{FEATURE_TABLE}"'
        ).fetchall()

        updates = []
        matched_rows = 0
        random_rows = 0
        for fid, identificatie in rows:
            if identificatie in underpass_values:
                value = underpass_values[identificatie]
                source = "streetlidar"
                matched_rows += 1
            else:
                value = rng.uniform(RANDOM_MIN, RANDOM_MAX)
                source = "heuristic"
                random_rows += 1
            updates.append((value, source, fid))

        con.executemany(
            f'update "{FEATURE_TABLE}" set "{TARGET_COLUMN}" = ?, "{SOURCE_COLUMN}" = ? where fid = ?',
            updates,
        )
        con.commit()

    return len(rows), matched_rows, random_rows


def main():
    underpass_values = load_underpass_values(CSV_PATH)
    total_rows, matched_rows, random_rows = merge_underpass_values(
        GPKG_PATH, underpass_values
    )
    print(f"Loaded {len(underpass_values)} values from {CSV_PATH}")
    print(f"Updated {total_rows} rows in {GPKG_PATH}")
    print(f"Rows using CSV value: {matched_rows}")
    print(f"Rows using random fallback: {random_rows}")


if __name__ == "__main__":
    main()
