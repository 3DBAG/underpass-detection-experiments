# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "psycopg[binary]",
# ]
# ///
"""Create PostgreSQL views from CityJSONL bounding boxes.

For each .city.jsonl file in the output directory produced by concat_cityjsonl.py,
reads the bounding box from the first (metadata) line and creates a view in the
underpasses schema that spatially subsets underpasses.extended_geometries_2 to
only those features whose geometry intersects the bounding box.

View names follow the pattern u_<stem>, e.g. a-b-c.city.jsonl → underpasses.u_a-b-c.

Database credentials are read from ~/.pgpass for host=localhost, dbname=baseregisters.

Usage:
    python create_views.py /path/to/output_dir
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg
from psycopg import sql


SRID_3D_TO_2D = {7415: 28992}
TARGET_SCHEMA = "underpasses"
TARGET_TABLE = "extended_geometries_2"
DB_HOST = "localhost"
DB_NAME = "baseregisters"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory of .city.jsonl files produced by concat_cityjsonl.py.",
    )
    args = parser.parse_args(argv)
    output_dir: Path = args.output_dir.resolve()

    if not output_dir.is_dir():
        print(f"error: not a directory: {output_dir}", file=sys.stderr)
        return 1

    pgpass_path = Path.home() / ".pgpass"
    if not pgpass_path.is_file():
        print("error: ~/.pgpass not found", file=sys.stderr)
        return 1

    creds = read_pgpass(pgpass_path, host=DB_HOST, dbname=DB_NAME)
    if creds is None:
        print(
            f"error: no matching entry in ~/.pgpass for host={DB_HOST} dbname={DB_NAME}",
            file=sys.stderr,
        )
        return 1

    host, port, dbname, user, password = creds

    files = sorted(output_dir.glob("*.city.jsonl"))
    if not files:
        print(f"warning: no .city.jsonl files in {output_dir}", file=sys.stderr)
        return 0

    with psycopg.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        autocommit=True,
    ) as conn:
        for cityjsonl_file in files:
            stem = cityjsonl_file.name.removesuffix(".city.jsonl")
            bbox = extract_bbox(cityjsonl_file)
            if bbox is None:
                print(
                    f"warning: skipping {cityjsonl_file.name}: could not extract bbox",
                    file=sys.stderr,
                )
                continue
            minx, miny, maxx, maxy, srid = bbox
            create_view(conn, stem, minx, miny, maxx, maxy, srid)
            print(f"created view {TARGET_SCHEMA}.u_{stem}")

    return 0


def extract_bbox(path: Path) -> tuple[float, float, float, float, int] | None:
    """Return (minx, miny, maxx, maxy, srid) from the metadata line of a CityJSONL file."""
    with path.open(encoding="utf-8") as f:
        first_line = f.readline()
    if not first_line.strip():
        return None

    try:
        obj = json.loads(first_line)
    except json.JSONDecodeError:
        return None

    metadata = obj.get("metadata", {})
    extent = metadata.get("geographicalExtent")
    ref_sys = metadata.get("referenceSystem", "")

    if not extent or len(extent) != 6:
        return None

    minx, miny, _minz, maxx, maxy, _maxz = extent

    try:
        epsg = int(ref_sys.rstrip("/").rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        epsg = 28992  # fallback for Dutch data

    srid = SRID_3D_TO_2D.get(epsg, epsg)
    return minx, miny, maxx, maxy, srid


def create_view(
    conn: psycopg.Connection,
    stem: str,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    srid: int,
) -> None:
    view_name = f"u_{stem}"
    query = sql.SQL(
        "CREATE OR REPLACE VIEW {schema}.{view} AS "
        "SELECT * FROM {schema}.{table} "
        "WHERE ST_Intersects(geom, ST_MakeEnvelope({minx}, {miny}, {maxx}, {maxy}, {srid}))"
    ).format(
        schema=sql.Identifier(TARGET_SCHEMA),
        view=sql.Identifier(view_name),
        table=sql.Identifier(TARGET_TABLE),
        minx=sql.Literal(minx),
        miny=sql.Literal(miny),
        maxx=sql.Literal(maxx),
        maxy=sql.Literal(maxy),
        srid=sql.Literal(srid),
    )
    with conn.cursor() as cur:
        cur.execute(query)


def read_pgpass(
    path: Path, host: str, dbname: str
) -> tuple[str, int, str, str, str] | None:
    """Return (host, port, dbname, user, password) from the first matching ~/.pgpass entry."""
    mode = oct(path.stat().st_mode)[-3:]
    if mode != "600":
        print(f"warning: ~/.pgpass permissions are {mode}, should be 600", file=sys.stderr)

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = _split_pgpass_line(stripped)
        if len(fields) != 5:
            continue
        pg_host, pg_port, pg_db, pg_user, pg_password = fields
        if not _pgpass_field_matches(pg_host, host):
            continue
        if not _pgpass_field_matches(pg_db, dbname):
            continue
        port = 5432 if pg_port == "*" else int(pg_port)
        return host, port, dbname, pg_user, pg_password
    return None


def _pgpass_field_matches(pattern: str, value: str) -> bool:
    return pattern == "*" or pattern == value


def _split_pgpass_line(line: str) -> list[str]:
    """Split a pgpass line on unescaped colons, respecting backslash escapes."""
    fields: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] in (":", "\\"):
            current.append(line[i + 1])
            i += 2
        elif line[i] == ":":
            fields.append("".join(current))
            current = []
            i += 1
        else:
            current.append(line[i])
            i += 1
    fields.append("".join(current))
    return fields


if __name__ == "__main__":
    sys.exit(main())
