from os import environ
from pathlib import Path
import sys

from psycopg import connect
from psycopg.sql import Identifier

from edge_offset.postgis import write_offset_polygons_from_db

DEFAULT_EDGES_TABLE = Identifier("underpasses_edge_extension", "edges")
ENV_PATH = Path(".env")


def main() -> int:
    _load_dotenv(ENV_PATH)

    output_path_value = environ.get("EDGE_OFFSET_OUTPUT_PATH")
    if not output_path_value:
        raise ValueError("EDGE_OFFSET_OUTPUT_PATH must be set.")

    distance_value = environ.get("EDGE_OFFSET_OFFSET_DISTANCE")
    if not distance_value:
        raise ValueError("EDGE_OFFSET_OFFSET_DISTANCE must be set.")

    connection = connect(
        host=_require_env("EDGE_OFFSET_DB_HOST"),
        port=int(_require_env("EDGE_OFFSET_DB_PORT")),
        dbname=_require_env("EDGE_OFFSET_DB_NAME"),
        user=_require_env("EDGE_OFFSET_DB_USER"),
        password=environ.get("EDGE_OFFSET_DB_PASSWORD", ""),
    )
    with connection:
        write_offset_polygons_from_db(
            connection,
            edges_table=DEFAULT_EDGES_TABLE,
            distance=float(distance_value),
            output_path=Path(output_path_value),
        )
    return 0


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        environ.setdefault(key.strip(), value.strip())


def _require_env(name: str) -> str:
    value = environ.get(name)
    if value:
        return value
    raise ValueError(f"{name} must be set.")


if __name__ == "__main__":
    sys.exit(main())
