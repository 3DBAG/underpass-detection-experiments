import os
import geopandas as gpd
import pandas as pd
import duckdb
import itertools
from shapely import wkb
from shapely import wkt
import shapely
from shapely.ops import unary_union
import trimesh
import numpy as np

# import image_matching.image_matching

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Input 3DBAG tiles directory. Contains geopckg files
tiles_directory = os.path.join(PROJECT_ROOT, 'data/main/3dbag_tiles')
# Input images directory. Contains image rasters, camera_parameters.txt and image_footprints.geojson
images_directory = os.path.join(PROJECT_ROOT, 'data/main/oblique_images')
# Input underpasses directory. Contains a geojson file
underpasses_directory = os.path.join(PROJECT_ROOT, 'data/main/underpass_polygons')
# Input database file
database_path = os.path.join(PROJECT_ROOT, 'data/main/underpasses_database.db')
# Create connection to database
con = duckdb.connect(database=database_path)
con.execute("INSTALL spatial;")
con.execute("LOAD spatial;")

# Camera parameters file
camera_parameters_path = os.path.join(images_directory, 'camera_parameters.txt')
# Image footprints file
image_footprints_path = os.path.join(images_directory, 'image_footprints.geojson')


# Iterate over each tile for height calculation
for filename in os.listdir(tiles_directory):

    # Make sure that there is no buildings table
    con.execute('DROP TABLE IF EXISTS buildings')
    con.execute("DROP TABLE IF EXISTS walls")
    con.execute("DROP TABLE IF EXISTS merged_walls")
    
    # Read geopckg file lod_22 geometries into geodata frame
    tile = os.path.join(tiles_directory, filename)
    buildings_gdf = gpd.read_file(tile, layer="lod22_3d")
    # Convert geometry column to wkt so duckdb can read it
    buildings_gdf["lod22_geom"] = buildings_gdf.geometry.apply(lambda g: g.wkt)
    buildings_gdf = buildings_gdf.drop(columns="geometry")

    # Create empty table for buildings
    con.execute("""
        CREATE TABLE IF NOT EXISTS buildings (
                building_id VARCHAR,
                b3_pand_deel_id INTEGER,
                labels VARCHAR,
                lod22_geom VARCHAR
        )""")

    # Add geodata frame to database
    con.register("buildings_gdf", buildings_gdf)
    con.execute("INSERT INTO buildings SELECT * FROM buildings_gdf")

    # Select buildings which have underpasses (spatial intersection underpass polygons-buildings)
    # Create temporal tables with intersecting buildings
    con.execute("""
        CREATE TABLE IF NOT EXISTS buildings_intersecting AS
        SELECT b.*
        FROM buildings b
        JOIN underpasses u
        ON ST_Intersects(ST_GeomFromText(b.lod22_geom), ST_GeomFromText(u.geometry_wkt))
    """)
    
    # Drop current building table and rename buildings_intersecting into buildings
    con.execute("DROP TABLE buildings")
    con.execute("ALTER TABLE buildings_intersecting RENAME TO buildings")

    # Get building walls that intersect with underpasses and create new table walls    
    wall_records = []
    wall_counter = itertools.count(1)

    df_buildings = con.execute("SELECT * FROM buildings").fetchdf()
    df_underpasses = con.execute("SELECT * FROM underpasses").fetchdf()

    for index, building in df_buildings.iterrows():

        # Retrieve building geometry as bytes and convert to shapely geometry
        building_geom = shapely.from_wkt(building["lod22_geom"])
        # Parse labels. Label 2 describes a wall surface
        count, values = building['labels'].strip("()").split(":")
        labels = list(map(int, values.split(",")))
        # Extract walls
        walls = []
        if building_geom.geom_type == "Polygon":
            building_geom = [building_geom]
        elif building_geom.geom_type == "MultiPolygon":
            building_geom = building_geom.geoms

        for i, polygon in enumerate(building_geom):
            if labels[i] == 2:
                walls.append(polygon)

        # Merge walls to aggregate touching polygons
        merged_walls = unary_union(walls)

        # Check intersection of walls with underpasses. Create new wall entry if intersects an underpass
        for wall in walls:
            for index, underpass in df_underpasses.iterrows():
                underpass_geom = shapely.from_wkt(underpass['geometry_wkt'])
                if wall.intersects(underpass_geom):
                    wall_id = next(wall_counter)
                    wall_records.append({
                        "wall_id": wall_id,
                        "geom": wall.wkt,
                        "underpass_id": underpass["identificatie"]
                    })

    wall_df = pd.DataFrame(wall_records)

    # Collect all wall meshes
    wall_meshes = []

    for _, row in wall_df.iterrows():
        geom = shapely.from_wkt(row["geom"])  # convert WKT back to shapely
        if geom.geom_type == "Polygon":
            polys = [geom]
        elif geom.geom_type == "MultiPolygon":
            polys = geom.geoms
        else:
            continue

        for poly in polys:
            # Extract exterior coordinates (ignore holes for now)
            coords = poly.exterior.coords
            # Convert to numpy array
            vertices = np.array(coords)
            # Create faces: connect consecutive vertices into a loop
            faces = [[i, (i + 1) % len(vertices), (i + 1) % len(vertices)] for i in range(len(vertices)-1)]
            # Create trimesh object
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            wall_meshes.append(mesh)

    # Merge all walls into a single mesh
    scene = trimesh.util.concatenate(wall_meshes)

    # Export to OBJ
    scene.export("walls.obj")
    
    # Create table for walls. Create empty table and insert data from wall dataframe
    con.execute("""
        CREATE TABLE IF NOT EXISTS walls (
                wall_id INTEGER PRIMARY KEY,
                geom VARCHAR,
                underpass_id VARCHAR
        )""")
    con.register("wall_df", wall_df)
    con.execute("INSERT INTO walls SELECT * FROM wall_df")

    df_footprints = con.execute("SELECT * FROM image_footprints").fetch_df()
    print("Image footprints table: \n", df_footprints.head())

    df_underpasses = con.execute("SELECT * FROM underpasses").fetch_df()
    print("Underpasses table: \n", df_underpasses.head())
    
    df_buildings = con.execute("SELECT * FROM buildings").fetch_df()
    print("Buildings table: \n", df_buildings.head())


    # Drop table for next iteration
    con.execute("DROP TABLE IF EXISTS buildings")
    con.execute("DROP TABLE IF EXISTS walls")
    con.execute("DROP TABLE IF EXISTS merged_walls")

    break 
    
    


