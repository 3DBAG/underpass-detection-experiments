"""Database operations for edge classification."""

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from psycopg import Connection
from psycopg.sql import SQL, Identifier
from shapely import from_wkb, to_wkb
from shapely.geometry import LineString, Polygon

from edge_classification.edge_classifier import classify_edges_for_underpass


@dataclass
class EdgeClassificationResult:
    """Result of edge classification with edge geometries."""
    
    underpass_id: int
    identificatie: str
    edge_type: str  # 'interior', 'exterior', or 'shared'
    geom: LineString


def load_underpass_data_from_db(
    connection: Connection[Any],
    underpass_id: int,
    geometries_table: str = "underpasses.geometries",
    bag_bgt_join_table: str = "underpasses.bag_bgt_join",
    bag_adjacency_table: str = "building_types.bag_adjacency_4",
    bag_table: str = "lvbag.pandactueelbestaand",
) -> Tuple[str, Polygon, Polygon, List[Polygon]]:
    """
    Load underpass data from the database for a single underpass.
    
    Args:
        connection: Database connection
        underpass_id: ID of the underpass to process
        geometries_table: Name of the geometries table
        bag_bgt_join_table: Name of the BAG-BGT join table
        bag_adjacency_table: Name of the adjacency table
        bag_table: Name of the BAG building table
        
    Returns:
        Tuple of (identificatie, underpass_geom, bgt_geom, adjacent_geoms)
    """
    # Query for underpass and BGT geometries
    query = SQL("""
        SELECT
            un.identificatie::text,
            ST_AsBinary(un.geom) AS underpass_wkb,
            ST_AsBinary(bbj.bgt_geometrie) AS bgt_wkb
        FROM {geometries_table} un
        JOIN {bag_bgt_join_table} bbj
            ON un.identificatie = bbj.identificatie
        WHERE un.underpass_id = %s
            AND NOT ST_IsEmpty(un.geom)
    """).format(
        geometries_table=Identifier(*geometries_table.split('.')),
        bag_bgt_join_table=Identifier(*bag_bgt_join_table.split('.')),
    )
    
    with connection.cursor() as cursor:
        cursor.execute(query, (underpass_id,))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"No data found for underpass_id {underpass_id}")
        
        identificatie, underpass_wkb, bgt_wkb = row
        underpass_geom = from_wkb(underpass_wkb)
        bgt_geom = from_wkb(bgt_wkb)
    
    # Query for adjacent geometries
    adjacency_query = SQL("""
        SELECT DISTINCT
            ST_AsBinary(bag.geometrie) AS adjacent_wkb
        FROM {bag_adjacency_table} ba
        JOIN {bag_table} bag
            ON bag.identificatie = ba.adjacent_identificatie
        WHERE ba.identificatie = %s
            AND NOT ST_IsEmpty(bag.geometrie)
    """).format(
        bag_adjacency_table=Identifier(*bag_adjacency_table.split('.')),
        bag_table=Identifier(*bag_table.split('.')),
    )
    
    adjacent_geoms = []
    with connection.cursor() as cursor:
        cursor.execute(adjacency_query, (identificatie,))
        for (adjacent_wkb,) in cursor.fetchall():
            adjacent_geoms.append(from_wkb(adjacent_wkb))
    
    return identificatie, underpass_geom, bgt_geom, adjacent_geoms


def classify_edges_from_db(
    connection: Connection[Any],
    underpass_id: int,
    grid_size: float = 0.001,
    snap_tolerance: float = 0.1,
    geometries_table: str = "underpasses.geometries",
    bag_bgt_join_table: str = "underpasses.bag_bgt_join",
    bag_adjacency_table: str = "building_types.bag_adjacency_4",
    bag_table: str = "lvbag.pandactueelbestaand",
) -> List[EdgeClassificationResult]:
    """
    Classify edges for a single underpass by loading data from the database.
    
    Args:
        connection: Database connection
        underpass_id: ID of the underpass to process
        grid_size: Grid size for snapping (default: 0.001)
        snap_tolerance: Tolerance for snapping adjacent geometries (default: 0.1)
        geometries_table: Name of the geometries table
        bag_bgt_join_table: Name of the BAG-BGT join table
        bag_adjacency_table: Name of the adjacency table
        bag_table: Name of the BAG building table
        
    Returns:
        List of EdgeClassificationResult objects
    """
    # Load data from database
    identificatie, underpass_geom, bgt_geom, adjacent_geoms = load_underpass_data_from_db(
        connection=connection,
        underpass_id=underpass_id,
        geometries_table=geometries_table,
        bag_bgt_join_table=bag_bgt_join_table,
        bag_adjacency_table=bag_adjacency_table,
        bag_table=bag_table,
    )
    
    # Classify edges
    classified = classify_edges_for_underpass(
        underpass_id=underpass_id,
        identificatie=identificatie,
        underpass_geom=underpass_geom,
        bgt_geom=bgt_geom,
        adjacent_geoms=adjacent_geoms,
        grid_size=grid_size,
        snap_tolerance=snap_tolerance,
    )
    
    # Convert to result format
    results = []
    
    for edge in classified.interior_edges:
        results.append(EdgeClassificationResult(
            underpass_id=underpass_id,
            identificatie=identificatie,
            edge_type='interior',
            geom=edge,
        ))
    
    for edge in classified.exterior_edges:
        results.append(EdgeClassificationResult(
            underpass_id=underpass_id,
            identificatie=identificatie,
            edge_type='exterior',
            geom=edge,
        ))
    
    for edge in classified.shared_edges:
        results.append(EdgeClassificationResult(
            underpass_id=underpass_id,
            identificatie=identificatie,
            edge_type='shared',
            geom=edge,
        ))
    
    return results


def write_edges_to_db(
    connection: Connection[Any],
    edges: List[EdgeClassificationResult],
    edges_table: str = "underpasses.edges",
    create_table: bool = False,
) -> None:
    """
    Write classified edges to the database.
    
    Args:
        connection: Database connection
        edges: List of EdgeClassificationResult objects to write
        edges_table: Name of the output table
        create_table: Whether to create/recreate the table
    """
    if create_table:
        # Create table if requested
        create_query = SQL("""
            DROP TABLE IF EXISTS {edges_table} CASCADE;
            
            CREATE TABLE {edges_table} (
                edge_id SERIAL PRIMARY KEY,
                underpass_id INTEGER NOT NULL,
                identificatie TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                geom GEOMETRY(LineString, 28992)
            );
            
            CREATE INDEX IF NOT EXISTS idx_edges_underpass_id
                ON {edges_table} (underpass_id);
            
            CREATE INDEX IF NOT EXISTS idx_edges_identificatie
                ON {edges_table} (identificatie);
            
            CREATE INDEX IF NOT EXISTS idx_edges_edge_type
                ON {edges_table} (edge_type);
            
            CREATE INDEX IF NOT EXISTS idx_edges_geom
                ON {edges_table} USING GIST (geom);
        """).format(edges_table=Identifier(*edges_table.split('.')))
        
        with connection.cursor() as cursor:
            cursor.execute(create_query)
        connection.commit()
    
    # Insert edges
    if edges:
        insert_query = SQL("""
            INSERT INTO {edges_table} (underpass_id, identificatie, edge_type, geom)
            VALUES (%s, %s, %s, ST_GeomFromWKB(%s, 28992))
        """).format(edges_table=Identifier(*edges_table.split('.')))
        
        with connection.cursor() as cursor:
            for edge in edges:
                cursor.execute(
                    insert_query,
                    (edge.underpass_id, edge.identificatie, edge.edge_type, to_wkb(edge.geom)),
                )
        connection.commit()


def get_all_underpass_ids(
    connection: Connection[Any],
    geometries_table: str = "underpasses.geometries",
) -> List[int]:
    """
    Get all underpass IDs from the database.
    
    Args:
        connection: Database connection
        geometries_table: Name of the geometries table
        
    Returns:
        List of underpass IDs
    """
    query = SQL("""
        SELECT DISTINCT underpass_id
        FROM {geometries_table}
        WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
        ORDER BY underpass_id
    """).format(geometries_table=Identifier(*geometries_table.split('.')))
    
    with connection.cursor() as cursor:
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall()]


def get_unprocessed_underpass_ids(
    connection: Connection[Any],
    geometries_table: str = "underpasses.geometries",
    edges_table: str = "underpasses.edges",
) -> List[int]:
    """
    Get underpass IDs that haven't been processed yet.
    
    Args:
        connection: Database connection
        geometries_table: Name of the geometries table
        edges_table: Name of the edges table
        
    Returns:
        List of unprocessed underpass IDs
    """
    query = SQL("""
        SELECT DISTINCT un.underpass_id
        FROM {geometries_table} un
        LEFT JOIN {edges_table} e
            ON un.underpass_id = e.underpass_id
        WHERE un.geom IS NOT NULL 
            AND NOT ST_IsEmpty(un.geom)
            AND e.underpass_id IS NULL
        ORDER BY un.underpass_id
    """).format(
        geometries_table=Identifier(*geometries_table.split('.')),
        edges_table=Identifier(*edges_table.split('.')),
    )
    
    with connection.cursor() as cursor:
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall()]
