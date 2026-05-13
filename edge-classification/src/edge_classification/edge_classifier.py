"""Core edge classification logic for underpass geometries."""

from dataclasses import dataclass
from typing import Dict, List, Tuple

from shapely.geometry import LineString, MultiLineString, Polygon

from edge_classification.geometry_ops import (
    dump_multilinestring,
    extract_exterior_rings,
    safe_difference,
    safe_intersection,
    snap_to_grid,
    union_geometries,
)


@dataclass
class ClassifiedEdges:
    """Result of edge classification for a single underpass."""
    
    underpass_id: int
    identificatie: str
    interior_edges: List[LineString]
    exterior_edges: List[LineString]
    shared_edges: List[LineString]


def classify_edges_for_underpass(
    underpass_id: int,
    identificatie: str,
    underpass_geom: Polygon,
    bgt_geom: Polygon,
    adjacent_geoms: List[Polygon],
    grid_size: float = 0.001,
    snap_tolerance: float = 0.1,
) -> ClassifiedEdges:
    """
    Classify edges of an underpass polygon into interior, exterior, and shared edges.
    
    This implements the SQL logic from edges.sql:
    1. Snap geometries to grid
    2. Compute exterior edges (parts of ring NOT intersecting with BGT)
    3. Derive interior edges as everything that's NOT exterior (full ring - exterior edges)
    4. Add interior rings as interior edges
    5. Find intersections with adjacent buildings to identify shared edges
    6. Separate shared edges from exterior edges
    
    Args:
        underpass_id: Unique identifier for the underpass
        identificatie: BAG building identifier
        underpass_geom: The underpass polygon geometry
        bgt_geom: The BGT geometry for this building
        adjacent_geoms: List of adjacent building geometries
        grid_size: Grid size for snapping (default: 0.001)
        snap_tolerance: Tolerance for snapping adjacent geometries (default: 0.1)
        
    Returns:
        ClassifiedEdges object containing the classified edge lists
    """
    # Step 1: Snap underpass and BGT geometries to grid
    snapped_underpass = snap_to_grid(underpass_geom, grid_size)
    snapped_bgt = snap_to_grid(bgt_geom, grid_size)
    
    # Step 2: Get the full exterior ring
    full_ring = LineString(snapped_underpass.exterior.coords)
    
    # Step 3: Get BGT exterior rings (handles both Polygon and MultiPolygon)
    bgt_exterior = extract_exterior_rings(snapped_bgt, grid_size)
    
    # Step 4: Compute exterior edges (parts NOT intersecting with BGT)
    exterior_edges_geom = safe_difference(full_ring, bgt_exterior, grid_size)
    
    # Step 5: Compute interior edges from exterior ring (full ring - exterior edges)
    if exterior_edges_geom and not exterior_edges_geom.is_empty:
        interior_edges_from_exterior = safe_difference(full_ring, exterior_edges_geom, grid_size)
    else:
        # If no exterior edges, entire ring is interior
        interior_edges_from_exterior = MultiLineString([full_ring])
    
    # Step 6: Add interior rings as interior edges
    interior_edges_from_rings = []
    for interior_ring in snapped_underpass.interiors:
        interior_edges_from_rings.append(LineString(interior_ring.coords))
    
    # Combine all interior edges
    all_interior_geoms = [interior_edges_from_exterior]
    if interior_edges_from_rings:
        all_interior_geoms.append(MultiLineString(interior_edges_from_rings))
    
    combined_interior = union_geometries(all_interior_geoms)
    
    # Step 7: Find shared edges (intersection with adjacent building exteriors)
    # This follows the SQL: snap adjacent_geom to exterior_edges, then extract exterior ring, then intersect
    shared_edge_parts = []
    
    if not exterior_edges_geom.is_empty and adjacent_geoms:
        for adjacent_geom in adjacent_geoms:
            if adjacent_geom is None or adjacent_geom.is_empty:
                continue
            
            # Snap adjacent geometry to grid first
            snapped_adjacent = snap_to_grid(adjacent_geom, grid_size)
            
            # Compute intersection (this handles the snap operation internally)
            intersection = safe_intersection(
                exterior_edges_geom, 
                snapped_adjacent,
                snap_tolerance=snap_tolerance,
                grid_size=grid_size
            )
            
            if intersection and not intersection.is_empty:
                shared_edge_parts.append(intersection)
    
    # Step 8: Union all shared edge parts
    shared_edges_geom = union_geometries(shared_edge_parts) if shared_edge_parts else None
    
    # Step 9: Remove shared edges from exterior edges to get final exterior edges
    if shared_edges_geom and not shared_edges_geom.is_empty:
        final_exterior_edges = safe_difference(exterior_edges_geom, shared_edges_geom, grid_size)
    else:
        final_exterior_edges = exterior_edges_geom
    
    # Step 10: Convert to lists of LineStrings
    interior_list = dump_multilinestring(combined_interior) if combined_interior else []
    exterior_list = dump_multilinestring(final_exterior_edges) if final_exterior_edges else []
    shared_list = dump_multilinestring(shared_edges_geom) if shared_edges_geom else []
    
    return ClassifiedEdges(
        underpass_id=underpass_id,
        identificatie=identificatie,
        interior_edges=interior_list,
        exterior_edges=exterior_list,
        shared_edges=shared_list,
    )


def classify_edges_for_underpass_batch(
    underpass_data: List[Tuple[int, str, Polygon, Polygon, List[Polygon]]],
    grid_size: float = 0.001,
    snap_tolerance: float = 0.1,
) -> List[ClassifiedEdges]:
    """
    Classify edges for multiple underpasses.
    
    Args:
        underpass_data: List of tuples (underpass_id, identificatie, underpass_geom, 
                        bgt_geom, adjacent_geoms)
        grid_size: Grid size for snapping (default: 0.001)
        snap_tolerance: Tolerance for snapping adjacent geometries (default: 0.1)
        
    Returns:
        List of ClassifiedEdges objects
    """
    results = []
    
    for underpass_id, identificatie, underpass_geom, bgt_geom, adjacent_geoms in underpass_data:
        try:
            classified = classify_edges_for_underpass(
                underpass_id=underpass_id,
                identificatie=identificatie,
                underpass_geom=underpass_geom,
                bgt_geom=bgt_geom,
                adjacent_geoms=adjacent_geoms,
                grid_size=grid_size,
                snap_tolerance=snap_tolerance,
            )
            results.append(classified)
        except Exception as e:
            # Log error but continue processing
            print(f"Error processing underpass {underpass_id} ({identificatie}): {e}")
            continue
    
    return results
