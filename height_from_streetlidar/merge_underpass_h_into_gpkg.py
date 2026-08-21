import csv
import json
import sqlite3
import struct
from pathlib import Path


CSV_PATH = Path("underpass_heights.csv")
GPKG_PATH = Path("/Users/ravi/git/underpass-detection-experiments/modelling_3d/sample_data/demo_ams_underpasses.gpkg")
FEATURE_TABLE = "offset_polygons"
TARGET_COLUMN = "underpass_candidate_elevations"
DEBUG_COLUMN = "underpass_candidate_peaks"
SOURCE_COLUMN = "underpass_source"


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
    values = {}
    with csv_path.open(newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            identificatie = row.get("identificatie")
            encoded_elevations = row.get("underpass_candidate_elevations")
            if not identificatie or not encoded_elevations:
                continue
            elevations = json.loads(encoded_elevations)
            if not isinstance(elevations, (int, float, list)):
                raise ValueError(
                    f"Candidate elevations for {identificatie} are not a number or list"
                )
            encoded_peaks = row.get("underpass_candidate_peaks")
            values[identificatie] = (
                json.dumps(elevations, separators=(",", ":")),
                encoded_peaks or None,
            )
    return values


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
    with connect_gpkg(gpkg_path) as con:
        ensure_text_column(con, FEATURE_TABLE, TARGET_COLUMN)
        ensure_text_column(con, FEATURE_TABLE, DEBUG_COLUMN)
        ensure_text_column(con, FEATURE_TABLE, SOURCE_COLUMN)

        rows = con.execute(
            f'select fid, identificatie from "{FEATURE_TABLE}"'
        ).fetchall()

        updates = []
        matched_rows = 0
        fallback_rows = 0
        for fid, identificatie in rows:
            if identificatie in underpass_values:
                value, debug_value = underpass_values[identificatie]
                source = "streetlidar"
                matched_rows += 1
            else:
                value = None
                debug_value = None
                source = "fallback"
                fallback_rows += 1
            updates.append((value, debug_value, source, fid))

        con.executemany(
            f'update "{FEATURE_TABLE}" set "{TARGET_COLUMN}" = ?, "{DEBUG_COLUMN}" = ?, "{SOURCE_COLUMN}" = ? where fid = ?',
            updates,
        )
        con.commit()

    return len(rows), matched_rows, fallback_rows


def main():
    underpass_values = load_underpass_values(CSV_PATH)
    total_rows, matched_rows, fallback_rows = merge_underpass_values(
        GPKG_PATH, underpass_values
    )
    print(f"Loaded {len(underpass_values)} elevation lists from {CSV_PATH}")
    print(f"Updated {total_rows} rows in {GPKG_PATH}")
    print(f"Rows using CSV elevations: {matched_rows}")
    print(f"Rows using modeller fallback: {fallback_rows}")


if __name__ == "__main__":
    main()
