"""Database operations for underpass detection."""

from typing import Any

from psycopg import Connection
from psycopg.sql import SQL, Identifier
from shapely import from_wkb, to_wkb
from shapely.geometry import MultiPolygon, Polygon


def _parse_table(table_name: str) -> tuple[str, str]:
    if "." in table_name:
        schema, table = table_name.split(".", 1)
    else:
        schema = "public"
        table = table_name
    return schema, table


def create_bag_bgt_join_table(
    connection: Connection[Any],
    table_name: str = "underpasses.bag_bgt_join",
) -> str:
    schema, table = _parse_table(table_name)
    idx_name = f"idx_{table}_identificatie"

    query = SQL("""
        DROP TABLE IF EXISTS {table};
        CREATE TABLE {table} (
            identificatie TEXT NOT NULL,
            bag_geometrie GEOMETRY(MultiPolygon, 28992),
            bgt_geometrie GEOMETRY(MultiPolygon, 28992)
        );
        CREATE INDEX IF NOT EXISTS {idx}
            ON {table} (identificatie);
    """).format(table=Identifier(schema, table), idx=Identifier(idx_name))

    with connection.cursor() as cursor:
        cursor.execute(query)
    connection.commit()

    return table_name


def create_bag_minus_bgt_table(
    connection: Connection[Any],
    table_name: str = "underpasses.bag_minus_bgt",
) -> str:
    schema, table = _parse_table(table_name)
    idx_name = f"idx_{table}_identificatie"

    query = SQL("""
        DROP TABLE IF EXISTS {table};
        CREATE TABLE {table} (
            identificatie TEXT NOT NULL,
            geom GEOMETRY(MultiPolygon, 28992)
        );
        CREATE INDEX IF NOT EXISTS {idx}
            ON {table} (identificatie);
    """).format(table=Identifier(schema, table), idx=Identifier(idx_name))

    with connection.cursor() as cursor:
        cursor.execute(query)
    connection.commit()

    return table_name


def create_snapped_differences_table(
    connection: Connection[Any],
    table_name: str = "underpasses.snapped_differences",
) -> str:
    schema, table = _parse_table(table_name)
    idx_name = f"idx_{table}_identificatie"

    query = SQL("""
        DROP TABLE IF EXISTS {table};
        CREATE TABLE {table} (
            identificatie TEXT NOT NULL,
            geom GEOMETRY(MultiPolygon, 28992)
        );
        CREATE INDEX IF NOT EXISTS {idx}
            ON {table} (identificatie);
    """).format(table=Identifier(schema, table), idx=Identifier(idx_name))

    with connection.cursor() as cursor:
        cursor.execute(query)
    connection.commit()

    return table_name


def create_geometries_table(
    connection: Connection[Any],
    table_name: str = "underpasses.geometries",
) -> str:
    schema, table = _parse_table(table_name)
    pk_name = f"pk_{table}"
    idx_ident_name = f"idx_{table}_identificatie"
    idx_geom_name = f"idx_{table}_geom"

    query = SQL("""
        DROP TABLE IF EXISTS {table} CASCADE;
        CREATE TABLE {table} (
            underpass_id INTEGER NOT NULL,
            identificatie TEXT NOT NULL,
            geom GEOMETRY(Polygon, 28992)
        );
        ALTER TABLE {table}
            ADD CONSTRAINT {pk}
            PRIMARY KEY (underpass_id);
        CREATE INDEX IF NOT EXISTS {idx_ident}
            ON {table} (identificatie);
        CREATE INDEX IF NOT EXISTS {idx_geom}
            ON {table} USING GIST (geom);
    """).format(
        table=Identifier(schema, table),
        pk=Identifier(pk_name),
        idx_ident=Identifier(idx_ident_name),
        idx_geom=Identifier(idx_geom_name),
    )

    with connection.cursor() as cursor:
        cursor.execute(query)
    connection.commit()

    return table_name


def load_bag_bgt_join_chunk(
    connection: Connection[Any],
    offset: int,
    limit: int,
    table_name: str = "underpasses.bag_bgt_join",
) -> list[tuple[str, Polygon | MultiPolygon, Polygon | MultiPolygon]]:
    schema, table = _parse_table(table_name)
    query = SQL("""
        SELECT bbj.identificatie::text,
               ST_AsBinary(bbj.bag_geometrie),
               ST_AsBinary(bbj.bgt_geometrie)
        FROM {table} bbj
        ORDER BY bbj.identificatie
        OFFSET %s LIMIT %s
    """).format(table=Identifier(schema, table))

    with connection.cursor() as cursor:
        cursor.execute(query, (offset, limit))
        rows = []
        for identificatie, bag_wkb, bgt_wkb in cursor.fetchall():
            bag_geom = from_wkb(bag_wkb)
            bgt_geom = from_wkb(bgt_wkb)
            rows.append((identificatie, bag_geom, bgt_geom))

    return rows


def load_bag_minus_bgt_chunk(
    connection: Connection[Any],
    offset: int,
    limit: int,
    table_name: str = "underpasses.bag_minus_bgt",
) -> list[tuple[str, Polygon | MultiPolygon]]:
    schema, table = _parse_table(table_name)
    query = SQL("""
        SELECT bmb.identificatie::text,
               ST_AsBinary(bmb.geom)
        FROM {table} bmb
        ORDER BY bmb.identificatie
        OFFSET %s LIMIT %s
    """).format(table=Identifier(schema, table))

    with connection.cursor() as cursor:
        cursor.execute(query, (offset, limit))
        rows = []
        for identificatie, geom_wkb in cursor.fetchall():
            geom = from_wkb(geom_wkb)
            rows.append((identificatie, geom))

    return rows


def load_snapped_differences_chunk(
    connection: Connection[Any],
    offset: int,
    limit: int,
    table_name: str = "underpasses.snapped_differences",
) -> list[tuple[str, Polygon | MultiPolygon]]:
    schema, table = _parse_table(table_name)
    query = SQL("""
        SELECT sd.identificatie::text,
               ST_AsBinary(sd.geom)
        FROM {table} sd
        ORDER BY sd.identificatie
        OFFSET %s LIMIT %s
    """).format(table=Identifier(schema, table))

    with connection.cursor() as cursor:
        cursor.execute(query, (offset, limit))
        rows = []
        for identificatie, geom_wkb in cursor.fetchall():
            geom = from_wkb(geom_wkb)
            rows.append((identificatie, geom))

    return rows


def get_bag_bgt_join_count(
    connection: Connection[Any],
    table_name: str = "underpasses.bag_bgt_join",
) -> int:
    schema, table = _parse_table(table_name)

    query = SQL("SELECT COUNT(*) FROM {table}").format(
        table=Identifier(schema, table)
    )

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchone()[0]


def get_bag_minus_bgt_count(
    connection: Connection[Any],
    table_name: str = "underpasses.bag_minus_bgt",
) -> int:
    schema, table = _parse_table(table_name)

    query = SQL("SELECT COUNT(*) FROM {table}").format(
        table=Identifier(schema, table)
    )

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchone()[0]


def get_snapped_differences_count(
    connection: Connection[Any],
    table_name: str = "underpasses.snapped_differences",
) -> int:
    schema, table = _parse_table(table_name)

    query = SQL("SELECT COUNT(*) FROM {table}").format(
        table=Identifier(schema, table)
    )

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchone()[0]


def write_bag_bgt_join_rows(
    connection: Connection[Any],
    rows: list[tuple[str, Polygon | MultiPolygon, Polygon | MultiPolygon]],
    table_name: str = "underpasses.bag_bgt_join",
) -> None:
    if not rows:
        return

    schema, table = _parse_table(table_name)

    insert_query = SQL("""
        INSERT INTO {table} (identificatie, bag_geometrie, bgt_geometrie)
        VALUES (%s, ST_GeomFromWKB(%s, 28992), ST_GeomFromWKB(%s, 28992))
    """).format(table=Identifier(schema, table))

    data = [
        (identificatie, to_wkb(bag_geom), to_wkb(bgt_geom))
        for identificatie, bag_geom, bgt_geom in rows
    ]

    with connection.cursor() as cursor:
        cursor.executemany(insert_query, data)


def write_bag_minus_bgt_rows(
    connection: Connection[Any],
    rows: list[tuple[str, Polygon | MultiPolygon]],
    table_name: str = "underpasses.bag_minus_bgt",
) -> None:
    if not rows:
        return

    schema, table = _parse_table(table_name)

    insert_query = SQL("""
        INSERT INTO {table} (identificatie, geom)
        VALUES (%s, ST_GeomFromWKB(%s, 28992))
    """).format(table=Identifier(schema, table))

    data = [
        (identificatie, to_wkb(geom))
        for identificatie, geom in rows
    ]

    with connection.cursor() as cursor:
        cursor.executemany(insert_query, data)


def write_snapped_differences_rows(
    connection: Connection[Any],
    rows: list[tuple[str, Polygon | MultiPolygon]],
    table_name: str = "underpasses.snapped_differences",
) -> None:
    if not rows:
        return

    schema, table = _parse_table(table_name)

    insert_query = SQL("""
        INSERT INTO {table} (identificatie, geom)
        VALUES (%s, ST_GeomFromWKB(%s, 28992))
    """).format(table=Identifier(schema, table))

    data = [
        (identificatie, to_wkb(geom))
        for identificatie, geom in rows
    ]

    with connection.cursor() as cursor:
        cursor.executemany(insert_query, data)


def write_geometries_rows(
    connection: Connection[Any],
    rows: list[tuple[int, str, Polygon]],
    table_name: str = "underpasses.geometries",
) -> None:
    if not rows:
        return

    schema, table = _parse_table(table_name)

    insert_query = SQL("""
        INSERT INTO {table} (underpass_id, identificatie, geom)
        VALUES (%s, %s, ST_GeomFromWKB(%s, 28992))
    """).format(table=Identifier(schema, table))

    data = [
        (underpass_id, identificatie, to_wkb(geom))
        for underpass_id, identificatie, geom in rows
    ]

    with connection.cursor() as cursor:
        cursor.executemany(insert_query, data)
