from concurrent.futures import ProcessPoolExecutor, as_completed
from os import environ
from pathlib import Path
import signal
import sys
import time
from typing import List, Tuple

from psycopg import connect
from psycopg.sql import Identifier, SQL
from shapely import to_wkb

from edge_offset.postgis import offset_polygon_features_from_db


# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    global shutdown_requested
    print("\n🛑 Shutdown requested... finishing current chunks and exiting gracefully")
    shutdown_requested = True

DEFAULT_EDGES_TABLE = Identifier("underpasses", "edges")
DEFAULT_OUTPUT_TABLE = Identifier("underpasses", "geometries_extended")
ENV_PATH = Path(".env")
CHUNK_SIZE = 1000  # Process 1000 underpasses at a time


def main() -> int:
    global shutdown_requested
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
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
        
        # Check progress
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(DISTINCT underpass_id) FROM underpasses.extended_geometries")
            already_processed = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT underpass_id) FROM underpasses.edges WHERE geom IS NOT NULL")
            total_underpasses = cursor.fetchone()[0]
            
        if already_processed > 0:
            print(f"Found {already_processed}/{total_underpasses} already processed underpasses")
            print(f"Will process remaining {total_underpasses - already_processed} underpasses")
        
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
            if shutdown_requested:
                print("🛑 Canceling remaining chunks...")
                break
                
            chunk, chunk_num = future_to_chunk[future]
            try:
                result = future.result()
                completed_chunks += 1
                elapsed = time.time() - start_time
                
                print(f"✅ Chunk {chunk_num}/{len(underpass_chunks)} completed: "
                      f"{result['processed']} underpasses, {result['failed']} failures "
                      f"({elapsed:.1f}s elapsed)")
                      
            except KeyboardInterrupt:
                print(f"Chunk {chunk_num}/{len(underpass_chunks)} interrupted by user")
                shutdown_requested = True
                break
            except Exception as e:
                print(f"❌ Chunk {chunk_num}/{len(underpass_chunks)} failed: {e}")
    
    if shutdown_requested:
        print(f"\n⚠️  Processing interrupted after {completed_chunks} chunks")
    else:
        print(f"\n✅ Processing completed successfully")
    
    total_time = time.time() - start_time
    print(f"\nProcessing completed in {total_time:.1f} seconds")
    return 0


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
    """Get underpass_id ranges for chunking, excluding already processed ones."""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT e.underpass_id 
            FROM underpasses.edges e
            LEFT JOIN underpasses.extended_geometries eg 
                ON e.underpass_id = eg.underpass_id 
                AND e.identificatie = eg.identificatie
            WHERE e.geom IS NOT NULL 
                AND eg.underpass_id IS NULL  -- Only unprocessed underpasses
            ORDER BY e.underpass_id
        """)
        underpass_ids = [row[0] for row in cursor.fetchall()]
    
    if not underpass_ids:
        print("No unprocessed underpasses found - all work is complete!")
        return []
    
    print(f"Found {len(underpass_ids)} unprocessed underpasses")
    
    # Create chunks with actual ID lists (not ranges)
    chunks = []
    for i in range(0, len(underpass_ids), CHUNK_SIZE):
        chunk_ids = underpass_ids[i:i + CHUNK_SIZE]
        chunks.append(chunk_ids)  # Keep the actual list of IDs
    
    return chunks


def process_chunk(chunk: List[int], chunk_num: int, distance: float, db_params: dict) -> dict:
    """Process a chunk of underpasses and store results in database."""
    processed = 0
    failed = 0
    
    print(f"🔄 Starting chunk {chunk_num}: {len(chunk)} underpasses [{chunk[0]}...{chunk[-1]}]")
    
    # Set up signal handler for this process
    def local_signal_handler(sig, frame):
        print(f"\n🛑 Chunk {chunk_num} received interrupt signal - finishing current underpass...")
        raise KeyboardInterrupt("Interrupted by signal")
    
    signal.signal(signal.SIGINT, local_signal_handler)
    signal.signal(signal.SIGTERM, local_signal_handler)
    
    # Create database connection for this worker process
    with connect(**db_params) as conn:
        # Batch insert data
        batch_inserts = []
        
        # Process each underpass individually  
        for i, underpass_id in enumerate(chunk):
            try:
                # Create temporary view for this specific underpass
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        CREATE OR REPLACE VIEW temp_single_underpass AS
                        SELECT * FROM underpasses.edges 
                        WHERE underpass_id = {underpass_id}
                        AND geom IS NOT NULL
                    """)
                
                # Process this single underpass
                features = offset_polygon_features_from_db(
                    conn,
                    edges_table=Identifier("public", "temp_single_underpass"),
                    distance=distance,
                    tolerance=1e-3,
                )
                
                # Collect results for batch insert
                if features:
                    for feature in features:
                        props = feature.properties
                        geom = feature.geometry
                        batch_inserts.append((
                            props['identificatie'],
                            props['underpass_id'], 
                            props['offset_distance'],
                            to_wkb(geom)
                        ))
                    processed += 1
                else:
                    print(f"No features generated for underpass {underpass_id}")
                
            except KeyboardInterrupt:
                print(f"🛑 Chunk {chunk_num} interrupted at underpass {underpass_id}")
                break
            except ValueError as e:
                if "Polygon boundary segment was not found" in str(e):
                    print(f"Skipping underpass {underpass_id} - edge matching failed")
                    failed += 1
                else:
                    print(f"ValueError for underpass {underpass_id}: {e}")
                    failed += 1
            except Exception as e:
                print(f"Error processing underpass {underpass_id}: {e}")
                failed += 1
            finally:
                # Cleanup temp view
                with conn.cursor() as cursor:
                    cursor.execute("DROP VIEW IF EXISTS temp_single_underpass")
        
        # Batch insert all results in one transaction
        if batch_inserts:
            print(f"💾 Chunk {chunk_num}: Batch inserting {len(batch_inserts)} records...")
            with conn.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO underpasses.extended_geometries 
                    (identificatie, underpass_id, offset_distance, geom)
                    VALUES (%s, %s, %s, ST_GeomFromWKB(%s, 28992))
                    ON CONFLICT (identificatie, underpass_id) DO NOTHING
                """, batch_inserts)
                
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
