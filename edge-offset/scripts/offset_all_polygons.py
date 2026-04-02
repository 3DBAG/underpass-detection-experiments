from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import environ
from pathlib import Path
import sys
import time
from typing import List, Tuple

from psycopg import connect
from psycopg.sql import Identifier, SQL
from shapely import from_wkb, to_wkb

from edge_offset.linework import coerce_multiline_geometry, merge_multiline_geometries
from edge_offset.offset_linework import offset_polygon_from_classified_polygon
from edge_offset.postgis import EdgeRecord
from edge_offset.rings import classify_polygon_from_edge_sets


DEFAULT_EDGES_TABLE = Identifier("underpasses", "edges")
DEFAULT_OUTPUT_TABLE = Identifier("underpasses", "geometries_extended")
ENV_PATH = Path(".env")
CHUNK_SIZE = 1000  # Process 1000 underpasses at a time


def main() -> int:

    _load_dotenv(ENV_PATH)
    
    distance_value = environ.get("EDGE_OFFSET_OFFSET_DISTANCE")
    if not distance_value:
        raise ValueError("EDGE_OFFSET_OFFSET_DISTANCE must be set.")
    
    distance = float(distance_value)
    max_workers = int(environ.get("EDGE_OFFSET_MAX_WORKERS", "4"))
    
    # Database connection parameters
    db_params = {
        "host": _require_env("EDGE_OFFSET_DB_HOST"),
        "port": int(_require_env("EDGE_OFFSET_DB_PORT")),
        "dbname": _require_env("EDGE_OFFSET_DB_NAME"),
        "user": _require_env("EDGE_OFFSET_DB_USER"),
        "password": environ.get("EDGE_OFFSET_DB_PASSWORD", ""),
    }
    
    # Setup database and get chunks
    with connect(**db_params) as conn:
        setup_extended_geometries_table(conn)
        setup_skipped_underpasses_table(conn)
        
        # Check progress
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(DISTINCT underpass_id) FROM underpasses.extended_geometries")
            already_processed = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT underpass_id) FROM underpasses.skipped_underpasses")
            already_skipped = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT underpass_id) FROM underpasses.edges WHERE geom IS NOT NULL")
            total_underpasses = cursor.fetchone()[0]
            
        if already_processed > 0 or already_skipped > 0:
            print(f"Found {already_processed}/{total_underpasses} already processed underpasses")
            print(f"Found {already_skipped}/{total_underpasses} already skipped underpasses")
            remaining = total_underpasses - already_processed - already_skipped
            print(f"Will process remaining {remaining} underpasses")
        
        underpass_chunks = get_underpass_chunks(conn)
        
    if not underpass_chunks:
        print("All underpasses have been processed! ✅")
        return 0
        
    print(f"Found {len(underpass_chunks)} chunks to process")
    print(f"Using {max_workers} parallel workers")
    
    # Process chunks in parallel
    start_time = time.time()
    completed_chunks = 0
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_chunk = {
            executor.submit(process_chunk, chunk, chunk_num + 1, distance, db_params): (chunk, chunk_num + 1)
            for chunk_num, chunk in enumerate(underpass_chunks)
        }
        
        # Process completed chunks
        for future in as_completed(future_to_chunk):
            chunk, chunk_num = future_to_chunk[future]
            try:
                result = future.result()
                completed_chunks += 1
                elapsed = time.time() - start_time
                
                print(f"✅ Chunk {chunk_num}/{len(underpass_chunks)} completed: "
                      f"{result['processed']} underpasses, {result['failed']} failures "
                      f"({elapsed:.1f}s elapsed)")
                      
            except Exception as e:
                print(f"❌ Chunk {chunk_num}/{len(underpass_chunks)} failed: {e}")
        
    total_time = time.time() - start_time
    print(f"\nProcessing completed successfully in {total_time:.1f} seconds")
    return 0


def setup_skipped_underpasses_table(conn):
    """Create skipped_underpasses table to track failed processing attempts."""
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS underpasses.skipped_underpasses (
                identificatie TEXT NOT NULL,
                underpass_id INTEGER NOT NULL,
                skip_reason TEXT,
                skipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (identificatie, underpass_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_skipped_underpass_id ON underpasses.skipped_underpasses (underpass_id);
            CREATE INDEX IF NOT EXISTS idx_skipped_identificatie ON underpasses.skipped_underpasses (identificatie);
        """)
        conn.commit()
    print("Skipped underpasses table ready")


def setup_extended_geometries_table(conn):
    """Create extended_geometries table if it doesn't exist (don't drop if exists)."""
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS underpasses.extended_geometries (
                identificatie TEXT NOT NULL,
                underpass_id INTEGER NOT NULL,
                offset_distance DOUBLE PRECISION,
                geom GEOMETRY(POLYGON, 28992),
                PRIMARY KEY (identificatie, underpass_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_extended_geom_identificatie ON underpasses.extended_geometries (identificatie);
            CREATE INDEX IF NOT EXISTS idx_extended_geom_underpass_id ON underpasses.extended_geometries (underpass_id);
            CREATE INDEX IF NOT EXISTS idx_extended_geom_spatial ON underpasses.extended_geometries USING GIST (geom);
        """)
        conn.commit()
    print("Extended geometries table ready (preserving existing data)")


def get_underpass_chunks(conn) -> List[List[int]]:
    """Get underpass_id ranges for chunking, excluding already processed and skipped ones."""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT e.underpass_id 
            FROM underpasses.edges e
            LEFT JOIN underpasses.extended_geometries eg 
                ON e.underpass_id = eg.underpass_id 
                AND e.identificatie = eg.identificatie
            LEFT JOIN underpasses.skipped_underpasses su
                ON e.underpass_id = su.underpass_id 
                AND e.identificatie = su.identificatie
            WHERE e.geom IS NOT NULL 
                AND eg.underpass_id IS NULL  -- Only unprocessed underpasses
                AND su.underpass_id IS NULL  -- Only non-skipped underpasses
            ORDER BY e.underpass_id
        """)
        underpass_ids = [row[0] for row in cursor.fetchall()]
    
    if not underpass_ids:
        print("No unprocessed underpasses found - all work is complete!")
        return []
    
    print(f"Found {len(underpass_ids)} unprocessed underpasses (excluding skipped)")
    
    # Create chunks with actual ID lists (not ranges)
    chunks = []
    for i in range(0, len(underpass_ids), CHUNK_SIZE):
        chunk_ids = underpass_ids[i:i + CHUNK_SIZE]
        chunks.append(chunk_ids)  # Keep the actual list of IDs
    
    return chunks


def _build_edge_records(rows) -> dict[int, list[EdgeRecord]]:
    """Group raw DB rows into EdgeRecords keyed by underpass_id."""
    edge_groups: dict[tuple[str, int], dict[str, list[bytes]]] = {}
    for identificatie, underpass_id, edge_type, edge_wkb in rows:
        key = (str(identificatie), int(underpass_id))
        if key not in edge_groups:
            edge_groups[key] = {'exterior': [], 'shared': [], 'interior': []}
        if edge_type in edge_groups[key] and edge_wkb is not None:
            edge_groups[key][edge_type].append(edge_wkb)

    records_by_underpass: dict[int, list[EdgeRecord]] = defaultdict(list)
    for (identificatie, underpass_id), edge_types in edge_groups.items():
        exterior_geoms = [coerce_multiline_geometry(from_wkb(bytes(w))) for w in edge_types['exterior']]
        movable_edges = merge_multiline_geometries(*exterior_geoms)
        shared_geoms = [coerce_multiline_geometry(from_wkb(bytes(w))) for w in edge_types['shared']]
        interior_geoms = [coerce_multiline_geometry(from_wkb(bytes(w))) for w in edge_types['interior']]
        fixed_edges = merge_multiline_geometries(*(shared_geoms + interior_geoms))
        records_by_underpass[underpass_id].append(
            EdgeRecord(
                identificatie=identificatie,
                underpass_id=underpass_id,
                movable_edges=movable_edges,
                fixed_edges=fixed_edges,
            )
        )
    return records_by_underpass


def process_chunk(chunk: List[int], chunk_num: int, distance: float, db_params: dict) -> dict:
    """Process a chunk of underpasses and store results in database."""
    processed = 0
    failed = 0

    print(f"🔄 Starting chunk {chunk_num}: {len(chunk)} underpasses")

    with connect(**db_params) as conn:
        # 1. Batch-load ALL edges for this chunk in ONE query
        t0 = time.time()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT identificatie::text, underpass_id, edge_type,
                       ST_AsBinary(geom) AS edge_wkb
                FROM underpasses.edges
                WHERE underpass_id = ANY(%s)
                  AND geom IS NOT NULL AND NOT ST_IsEmpty(geom)
                ORDER BY identificatie, underpass_id, edge_type
            """, (chunk,))
            rows = cursor.fetchall()
        print(f"📥 Chunk {chunk_num}: Loaded {len(rows)} edges in {time.time()-t0:.1f}s")

        # 2. Build EdgeRecords from in-memory data
        records_by_underpass = _build_edge_records(rows)
        del rows  # free memory

        # 3. Process each underpass purely in-memory (no more DB calls)
        batch_inserts = []
        skipped_inserts = []

        for underpass_id in chunk:
            records = records_by_underpass.get(underpass_id, [])
            if not records:
                continue

            for record in records:
                try:
                    classified = classify_polygon_from_edge_sets(
                        movable_edges=record.movable_edges,
                        fixed_edges=record.fixed_edges,
                        tolerance=1e-3,
                    )
                    polygon = offset_polygon_from_classified_polygon(
                        classified,
                        distance=distance,
                        tolerance=1e-3,
                        strategy="boolean_patch",
                    )
                    batch_inserts.append((
                        record.identificatie,
                        record.underpass_id,
                        distance,
                        to_wkb(polygon),
                    ))
                    processed += 1
                except KeyboardInterrupt:
                    print(f"🛑 Chunk {chunk_num} interrupted at underpass {underpass_id}")
                    break
                except ValueError as e:
                    if "Polygon boundary segment was not found" in str(e):
                        print(f"❌ Skipping underpass {underpass_id} - edge matching failed")
                    else:
                        print(f"ValueError for underpass {underpass_id}: {e}")
                    skipped_inserts.append((record.identificatie, underpass_id, "edge_matching_failed"))
                    failed += 1
                except Exception as e:
                    print(f"Error processing underpass {underpass_id}: {e}")
                    failed += 1
            else:
                continue
            break  # propagate KeyboardInterrupt break from inner loop

        # 4. Batch insert results in one transaction
        if batch_inserts:
            print(f"💾 Chunk {chunk_num}: Inserting {len(batch_inserts)} records...")
            with conn.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO underpasses.extended_geometries
                    (identificatie, underpass_id, offset_distance, geom)
                    VALUES (%s, %s, %s, ST_GeomFromWKB(%s, 28992))
                    ON CONFLICT (identificatie, underpass_id) DO NOTHING
                """, batch_inserts)
            conn.commit()

        if skipped_inserts:
            print(f"💾 Chunk {chunk_num}: Recording {len(skipped_inserts)} skipped...")
            with conn.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO underpasses.skipped_underpasses
                    (identificatie, underpass_id, skip_reason)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (identificatie, underpass_id) DO NOTHING
                """, skipped_inserts)
            conn.commit()

    print(f"🏁 Chunk {chunk_num} completed: {processed} processed, {failed} skipped")
    return {"processed": processed, "failed": failed}


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
