# Edge Classification for Underpass Detection

This package classifies building polygon edges into three types for underpass detection:
- **Interior edges**: Edges shared with BGT geometry or from interior rings
- **Exterior edges**: Building edges not touching adjacent buildings or BGT
- **Shared edges**: Building edges shared with adjacent buildings

This is a Python implementation of the SQL logic from [`detection_2d/sql/edges.sql`](../detection_2d/sql/edges.sql), designed for parallel processing of all underpasses.

## Features

- **Parallel processing**: Process multiple underpasses simultaneously using multiprocessing
- **Shapely 2.0+ optimizations**: Uses `set_precision()` for efficient geometry operations
- **Incremental processing**: Tracks progress and can resume from where it left off
- **Database-backed**: Reads from and writes to PostgreSQL/PostGIS database

## Installation

```bash
# Install dependencies (requires Python 3.12+)
pip install -e .

# Or with uv
uv pip install -e .
```

## Configuration

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` with your database credentials and settings:

```bash
# Database connection
EDGE_CLASSIFICATION_DB_HOST=localhost
EDGE_CLASSIFICATION_DB_PORT=5432
EDGE_CLASSIFICATION_DB_NAME=your_database
EDGE_CLASSIFICATION_DB_USER=your_user
EDGE_CLASSIFICATION_DB_PASSWORD=your_password

# Processing settings
EDGE_CLASSIFICATION_MAX_WORKERS=4                      # Number of parallel workers
EDGE_CLASSIFICATION_GRID_PRECISION=0.001
EDGE_CLASSIFICATION_SNAP_TOLERANCE=0.03      # Tolerance for snapping adjacent buildings (ST_Snap)```

## Usage

### Process All Underpasses in Parallel

```bash
python scripts/classify_all_edges.py
```

This script will:
1. Create the `underpasses.edges` table if it doesn't exist
2. Find all unprocessed underpasses
3. Process them in parallel using the configured number of workers
4. Write classified edges to the database
5. Show progress and statistics

### Programmatic Usage

```python
from psycopg import connect
from edge_classification import classify_edges_from_db

# Connect to database
db_params = {
    "host": "localhost",
    "port": 5432,
    "dbname": "your_database",
    "user": "your_user",
    "password": "your_password",
}

with connect(**db_params) as conn:
    # Classify edges for a specific underpass
    edges = classify_edges_from_db(
        connection=conn,
        underpass_id=123,
        grid_size=0.001,
        snap_tolerance=0.1,
    )
    
    # Process results
    for edge in edges:
        print(f"Underpass {edge.underpass_id}: {edge.edge_type} edge with {len(edge.geom.coords)} points")
```

## Database Schema

### Required Input Tables

- `underpasses.geometries`: Underpass polygon geometries
  - `underpass_id`: Unique identifier
  - `identificatie`: BAG building identifier
  - `geom`: Polygon geometry

- `underpasses.bag_bgt_join`: BAG-BGT join data
  - `identificatie`: BAG building identifier
  - `bgt_geometrie`: BGT geometry (Polygon or MultiPolygon)

- `building_types.bag_adjacency_4`: Adjacent buildings
  - `identificatie`: BAG building identifier
  - `adjacent_identificatie`: Adjacent building identifier

- `lvbag.pandactueelbestaand`: BAG building data
  - `identificatie`: Building identifier
  - `geometrie`: Building geometry

### Output Table

The script creates `underpasses.edges` with the following schema:

```sql
CREATE TABLE underpasses.edges (
    edge_id SERIAL PRIMARY KEY,
    underpass_id INTEGER NOT NULL,
    identificatie TEXT NOT NULL,
    edge_type TEXT NOT NULL,  -- 'interior', 'exterior', or 'shared'
    geom GEOMETRY(LineString, 28992)
);
```

Indexes are automatically created on:
- `underpass_id`
- `identificatie`
- `edge_type`
- `geom` (spatial index)

## Algorithm

The edge classification follows this logic (matching the SQL implementation):

1. **Snap geometries to grid**: Use `set_precision()` with 0.001m grid size
2. **Compute exterior edges**: 
   - Extract exterior ring from underpass polygon
   - Extract exterior rings from BGT geometry
   - Compute difference: `exterior_edges = underpass_ring - bgt_rings`
3. **Compute interior edges**:
   - From exterior ring: `interior_edges = underpass_ring - exterior_edges`
   - Add all interior rings as interior edges
4. **Find shared edges**:
   - For each adjacent building:
     - Snap adjacent geometry to exterior edges (0.1m tolerance)
     - Extract exterior ring
     - Compute intersection with exterior edges
   - Union all intersections
5. **Final classification**:
   - `shared_edges`: Union of all intersections with adjacent buildings
   - `exterior_edges`: Original exterior edges minus shared edges
   - `interior_edges`: Computed interior edges

## Project Structure

```
edge-classification/
├── src/edge_classification/
│   ├── __init__.py              # Package exports
│   ├── edge_classifier.py       # Core classification logic
│   ├── geometry_ops.py          # Geometry helper functions
│   └── postgis.py               # Database operations
├── scripts/
│   └── classify_all_edges.py    # Parallel processing script
├── tests/                        # Unit tests (TODO)
├── output/                       # Output directory
├── pyproject.toml               # Package configuration
├── .env.example                 # Example environment variables
└── README.md                    # This file
```

## Development

Run tests (TODO):
```bash
pytest
```

Format code with ruff:
```bash
ruff format .
```

Lint code:
```bash
ruff check .
```

## Differences from SQL Implementation

The Python implementation is functionally equivalent to the SQL but with some optimizations:

1. **`set_precision()` instead of `ST_SnapToGrid`**: Shapely 2.0's `set_precision()` is more efficient than manual coordinate rounding
2. **`snap()` for adjacent geometries**: Uses `shapely.ops.snap()` to mimic PostGIS `ST_Snap` behavior
3. **Parallel processing**: Processes multiple underpasses simultaneously instead of sequential SQL execution
4. **Incremental processing**: Can resume from where it left off by tracking processed underpasses

## Performance

Processing time depends on:
- Number of underpasses
- Complexity of geometries
- Number of adjacent buildings per underpass
- Database connection speed
- Number of parallel workers

Typical performance: ~0.1-0.5 seconds per underpass on 4 workers.

## License

[Add your license information here]
