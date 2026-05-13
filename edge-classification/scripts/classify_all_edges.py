#!/usr/bin/env python3
"""
Classify edges for all underpasses in parallel.

This script processes all underpasses from the database, classifying their edges
into interior, exterior, and shared types using parallel processing.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from os import environ
from pathlib import Path
import sys
import time
from typing import Dict, List

from psycopg import connect

from edge_classification.postgis import (
    classify_edges_from_db,
    get_unprocessed_underpass_ids,
    write_edges_to_db,
)


ENV_PATH = Path(".env")
EDGES_TABLE = "underpasses.edges"
GEOMETRIES_TABLE = "underpasses.geometries"
BAG_BGT_JOIN_TABLE = "underpasses.bag_bgt_join"
BAG_ADJACENCY_TABLE = "building_types.bag_adjacency_4"
BAG_TABLE = "lvbag.pandactueelbestaand"
CHUNK_SIZE = 100  # Process 100 underpasses per chunk


def _load_dotenv(path: Path) -> None:
    """Load environment variables from .env file if it exists."""
    if not path.exists():
        return
    
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                environ.setdefault(key.strip(), value.strip())


def _require_env(key: str) -> str:
    """Get required environment variable or raise error."""
    value = environ.get(key)
    if not value:
        raise ValueError(f"{key} environment variable must be set")
    return value


def setup_edges_table(db_params: Dict[str, str]) -> None:
    """Create the edges table if it doesn't exist."""
    with connect(**db_params) as conn:
        # Check if table exists
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'underpasses' 
                    AND table_name = 'edges'
                )
            """)
            table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("Creating edges table...")
            write_edges_to_db(conn, [], edges_table=EDGES_TABLE, create_table=True)
            print("✓ Table created")


def get_underpass_chunks(db_params: Dict[str, str]) -> List[List[int]]:
    """Get chunks of unprocessed underpass IDs."""
    with connect(**db_params) as conn:
        underpass_ids = get_unprocessed_underpass_ids(
            conn,
            geometries_table=GEOMETRIES_TABLE,
            edges_table=EDGES_TABLE,
        )
    
    if not underpass_ids:
        return []
    
    # Split into chunks
    chunks = []
    for i in range(0, len(underpass_ids), CHUNK_SIZE):
        chunks.append(underpass_ids[i:i + CHUNK_SIZE])
    
    return chunks


def process_chunk(
    chunk: List[int],
    chunk_num: int,
    grid_size: float,
    snap_tolerance: float,
    db_params: Dict[str, str],
) -> Dict[str, int]:
    """
    Process a chunk of underpasses.
    
    Args:
        chunk: List of underpass IDs to process
        chunk_num: Chunk number for logging
        grid_size: Grid size for snapping
        snap_tolerance: Tolerance for snapping adjacent geometries
        db_params: Database connection parameters
        
    Returns:
        Dictionary with processing statistics
    """
    successful = 0
    failed = 0
    failed_ids = []
    
    with connect(**db_params) as conn:
        for underpass_id in chunk:
            try:
                # Classify edges for this underpass
                edges = classify_edges_from_db(
                    connection=conn,
                    underpass_id=underpass_id,
                    grid_size=grid_size,
                    snap_tolerance=snap_tolerance,
                    geometries_table=GEOMETRIES_TABLE,
                    bag_bgt_join_table=BAG_BGT_JOIN_TABLE,
                    bag_adjacency_table=BAG_ADJACENCY_TABLE,
                    bag_table=BAG_TABLE,
                )
                
                # Write to database
                write_edges_to_db(conn, edges, edges_table=EDGES_TABLE)
                
                successful += 1
                
            except Exception as e:
                failed += 1
                failed_ids.append(underpass_id)
                print(f"  ✗ Chunk {chunk_num}: Failed underpass {underpass_id}: {e}")
    
    return {
        'successful': successful,
        'failed': failed,
        'failed_ids': failed_ids,
    }


def main() -> int:
    """Main entry point."""
    _load_dotenv(ENV_PATH)
    
    # Get configuration
    grid_size = float(environ.get("EDGE_CLASSIFICATION_SNAP_TOLERANCE", "0.001"))
    snap_tolerance = float(environ.get("EDGE_CLASSIFICATION_SNAP_ADJACENT_TOLERANCE", "0.1"))
    max_workers = int(environ.get("EDGE_CLASSIFICATION_MAX_WORKERS", "4"))
    
    # Database connection parameters
    db_params = {
        "host": _require_env("EDGE_CLASSIFICATION_DB_HOST"),
        "port": int(_require_env("EDGE_CLASSIFICATION_DB_PORT")),
        "dbname": _require_env("EDGE_CLASSIFICATION_DB_NAME"),
        "user": _require_env("EDGE_CLASSIFICATION_DB_USER"),
        "password": environ.get("EDGE_CLASSIFICATION_DB_PASSWORD", ""),
    }
    
    print("=" * 80)
    print("Edge Classification for Underpass Detection")
    print("=" * 80)
    print(f"Grid size (snap tolerance): {grid_size}")
    print(f"Adjacent snap tolerance: {snap_tolerance}")
    print(f"Max workers: {max_workers}")
    print()
    
    # Setup database
    setup_edges_table(db_params)
    
    # Get chunks to process
    underpass_chunks = get_underpass_chunks(db_params)
    
    if not underpass_chunks:
        print("✓ All underpasses have been processed!")
        return 0
    
    total_underpasses = sum(len(chunk) for chunk in underpass_chunks)
    print(f"Found {total_underpasses} unprocessed underpasses in {len(underpass_chunks)} chunks")
    print(f"Using {max_workers} parallel workers")
    print()
    
    # Process chunks in parallel
    start_time = time.time()
    total_successful = 0
    total_failed = 0
    all_failed_ids = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_chunk = {
            executor.submit(
                process_chunk,
                chunk,
                chunk_num + 1,
                grid_size,
                snap_tolerance,
                db_params,
            ): (chunk, chunk_num + 1)
            for chunk_num, chunk in enumerate(underpass_chunks)
        }
        
        # Process completed chunks
        completed_chunks = 0
        for future in as_completed(future_to_chunk):
            chunk, chunk_num = future_to_chunk[future]
            
            try:
                result = future.result()
                total_successful += result['successful']
                total_failed += result['failed']
                all_failed_ids.extend(result['failed_ids'])
                
                completed_chunks += 1
                percent = (completed_chunks / len(underpass_chunks)) * 100
                
                print(
                    f"✓ Chunk {chunk_num}/{len(underpass_chunks)} ({percent:.1f}%): "
                    f"{result['successful']} successful, {result['failed']} failed"
                )
                
            except Exception as e:
                print(f"✗ Chunk {chunk_num} failed completely: {e}")
                total_failed += len(chunk)
    
    # Print summary
    elapsed = time.time() - start_time
    print()
    print("=" * 80)
    print("Processing Complete")
    print("=" * 80)
    print(f"Total underpasses processed: {total_successful + total_failed}")
    print(f"Successful: {total_successful}")
    print(f"Failed: {total_failed}")
    print(f"Time elapsed: {elapsed:.2f} seconds")
    print(f"Average time per underpass: {elapsed / (total_successful + total_failed):.3f} seconds")
    
    if all_failed_ids:
        print()
        print(f"Failed underpass IDs: {all_failed_ids[:20]}")
        if len(all_failed_ids) > 20:
            print(f"... and {len(all_failed_ids) - 20} more")
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
