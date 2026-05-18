"""edge_classification package."""

from edge_classification.edge_classifier import classify_edges_for_underpass
from edge_classification.postgis import EdgeClassificationResult
from edge_classification.postgis import classify_edges_from_db
from edge_classification.postgis import create_adjacency_cache_table
from edge_classification.postgis import create_geometries_cache_table
from edge_classification.postgis import drop_adjacency_cache_table
from edge_classification.postgis import drop_geometries_cache_table
from edge_classification.postgis import load_all_underpass_data_for_chunk

__all__ = [
    "classify_edges_for_underpass",
    "classify_edges_from_db",
    "create_adjacency_cache_table",
    "create_geometries_cache_table",
    "drop_adjacency_cache_table",
    "drop_geometries_cache_table",
    "load_all_underpass_data_for_chunk",
    "EdgeClassificationResult",
]
