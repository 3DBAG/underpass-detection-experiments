"""Geometry operations for edge classification."""

from typing import List, Union

from shapely import set_precision
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
)
from shapely.ops import linemerge, snap, unary_union


def snap_to_grid(geom: Union[Polygon, LineString, MultiLineString, MultiPolygon], 
                 grid_size: float = 0.001) -> Union[Polygon, LineString, MultiLineString, MultiPolygon]:
    """
    Snap geometry coordinates to a grid with the given grid size.
    
    Uses Shapely's set_precision() for efficient coordinate snapping.
    
    Args:
        geom: Input geometry
        grid_size: Grid size for snapping (default: 0.001)
        
    Returns:
        Snapped geometry
    """
    if geom is None or geom.is_empty:
        return geom
    
    return set_precision(geom, grid_size=grid_size)


def extract_exterior_rings(geom: Union[Polygon, MultiPolygon], 
                          grid_size: float = 0.001) -> MultiLineString:
    """
    Extract exterior rings from a polygon or multipolygon.
    
    Args:
        geom: Input polygon or multipolygon
        grid_size: Grid size for snapping (default: 0.001)
        
    Returns:
        MultiLineString of exterior rings
    """
    if geom is None or geom.is_empty:
        return MultiLineString([])
    
    snapped = snap_to_grid(geom, grid_size)
    
    if isinstance(snapped, Polygon):
        return MultiLineString([snapped.exterior])
    elif isinstance(snapped, MultiPolygon):
        rings = [poly.exterior for poly in snapped.geoms]
        return MultiLineString(rings)
    else:
        return MultiLineString([])


def safe_difference(geom1: Union[LineString, MultiLineString], 
                   geom2: Union[LineString, MultiLineString],
                   grid_size: float = 0.001) -> MultiLineString:
    """
    Compute the difference between two line geometries with line merging.
    
    Args:
        geom1: First geometry
        geom2: Second geometry
        grid_size: Grid size for precision (default: 0.001)
        
    Returns:
        Difference as MultiLineString
    """
    if geom1 is None or geom1.is_empty:
        return MultiLineString([])
    if geom2 is None or geom2.is_empty:
        return MultiLineString([geom1] if isinstance(geom1, LineString) else list(geom1.geoms))
    
    try:
        # Use grid_size parameter for difference operation
        diff = set_precision(geom1, grid_size=grid_size).difference(
            set_precision(geom2, grid_size=grid_size)
        )
        merged = linemerge(diff)
        
        if isinstance(merged, LineString):
            return MultiLineString([merged])
        elif isinstance(merged, MultiLineString):
            return merged
        else:
            # Handle empty or other geometry types
            return MultiLineString([])
    except Exception:Polygon, MultiPolygon, LineString, MultiLineString],
                     snap_tolerance: float = 0.1,
                     grid_size: float = 0.001) -> MultiLineString:
    """
    Compute the intersection between line geometries with snapping and line merging.
    
    Mimics PostGIS ST_Snap behavior: snaps geom2 to geom1, then computes intersection.
    
    Args:
        geom1: First geometry (typically exterior edges)
        geom2: Second geometry (typically adjacent building geometry or exterior rings)
        snap_tolerance: Tolerance for snapping geom2 to geom1 (default: 0.1)
        grid_size: Grid size for precision (default: 0.001)
        
    Returns:
        Intersection as MultiLineString
    """
    if geom1 is None or geom1.is_empty or geom2 is None or geom2.is_empty:
        return MultiLineString([])
    
    try:
        # Snap geom2 to geom1 (mimics ST_Snap in PostGIS)
        snapped_geom2 = snap(geom2, geom1, snap_tolerance)
        
        # Extract exterior rings if it's a polygon
        if isinstance(snapped_geom2, (Polygon, MultiPolygon)):
            snapped_geom2 = extract_exterior_rings(snapped_geom2, grid_size)
        
        # Compute intersection with precision
        g1_precision = set_precision(geom1, grid_size=grid_size)
        g2_precision = set_precision(snapped_geom2, grid_size=grid_size)
        
        intersection = g1_precision.intersection(g2_precision
    try:
        # Snap geom2 to geom1 to ensure touching edges intersect
        snapped_geom2 = geom2.buffer(snap_tolerance).intersection(geom1.buffer(snap_tolerance))
        
        intersection = geom1.intersection(snapped_geom2)
        merged = linemerge(intersection)
        
        if isinstance(merged, LineString):
            return MultiLineString([merged])
        elif isinstance(merged, MultiLineString):
            return merged
        else:
            return MultiLineString([])
    except Exception:
        return MultiLineString([])


def union_geometries(geoms: List[Union[LineString, MultiLineString]]) -> Union[MultiLineString, None]:
    """
    Union multiple line geometries.
    
    Args:
        geoms: List of line geometries
        
    Returns:
        Unioned geometry as MultiLineString or None if empty
    """
    valid_geoms = [g for g in geoms if g is not None and not g.is_empty]
    
    if not valid_geoms:
        return None
    
    try:
        unioned = unary_union(valid_geoms)
        merged = linemerge(unioned)
        
        if isinstance(merged, LineString):
            return MultiLineString([merged])
        elif isinstance(merged, MultiLineString):
            return merged
        else:
            return None
    except Exception:
        return None


def dump_multilinestring(geom: MultiLineString) -> List[LineString]:
    """
    Convert a MultiLineString to a list of LineStrings.
    
    Args:
        geom: Input MultiLineString
        
    Returns:
        List of LineStrings
    """
    if geom is None or geom.is_empty:
        return []
    
    if isinstance(geom, LineString):
        return [geom]
    elif isinstance(geom, MultiLineString):
        return list(geom.geoms)
    else:
        return []
