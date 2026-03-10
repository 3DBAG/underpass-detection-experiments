import geopandas as gpd
import pandas as pd
from shapely.ops import transform
import matplotlib.pyplot as plt
import numpy as np
import shapely
from shapely.geometry import Polygon
import pyvista as pv


def load_input_data(camera_parameters_path, image_footprints_path, underpasses_path):
    
    # Load camera parameters
    df_camera_parameters = pd.read_csv(camera_parameters_path, sep='\s+', dtype={'img_id': str})

    # Load image footprints. Add camera center per footprint
    gdf_image_footprints = gpd.read_file(image_footprints_path)
    gdf_image_footprints = gdf_image_footprints.set_crs("EPSG:7415", allow_override=True)
    gdf_image_footprints = gdf_image_footprints.merge(df_camera_parameters, left_on='image_id', right_on='img_id', how='left')
    gdf_image_footprints = gdf_image_footprints[['image_id', 'geometry', 'X', 'Y', 'Z']].rename(columns={'X': 'camera_x', 'Y': 'camera_y', 'Z': 'camera_z'})

    # Load underpass polygons
    gdf_underpass_polygons = gpd.read_file(underpasses_path)
    gdf_underpass_polygons = gdf_underpass_polygons.set_crs("EPSG:7415", allow_override=True)
    gdf_underpass_polygons = gdf_underpass_polygons.explode(index_parts=False).reset_index(drop=True)
    gdf_underpass_polygons['underpass_id'] = gdf_underpass_polygons.index + 1
    gdf_underpass_polygons = gdf_underpass_polygons.rename(columns={'identificatie': 'building_id'})
    gdf_underpass_polygons = gdf_underpass_polygons[['underpass_id', 'building_id', 'geometry']]
    
    # Create a column for underpass height in the underpass GeoDataFrame, to be filled later
    gdf_underpass_polygons["observed_heights"] = [[] for _ in range(len(gdf_underpass_polygons))]

    return df_camera_parameters, gdf_image_footprints, gdf_underpass_polygons


def load_tile_data(tile_path):

    # Read lod-0 geometries into geodata frame
    gdf_building_footprints = gpd.read_file(tile_path, layer="pand")
    gdf_building_footprints['geometry'] = gdf_building_footprints.geometry.apply(lambda geom: transform(lambda x, y, z=None: (x, y), geom))
    gdf_building_footprints = gdf_building_footprints.rename(columns={'identificatie': 'building_id'})
    gdf_building_footprints = gdf_building_footprints[['building_id', 'geometry']]

    # Read lod-22 geometries into geodata frame
    # Read buildings in 3d
    gdf_building_3d = gpd.read_file(tile_path, layer="lod22_3d")
    gdf_building_3d = gdf_building_3d.rename(columns={'identificatie': 'building_id'})
    gdf_building_3d = gdf_building_3d[['building_id', 'geometry']]

    return gdf_building_footprints, gdf_building_3d


def find_critical_segments(gdf_underpass_polygons, gdf_building_footprints, buf_tol, simpl_tol, min_length):
    """Find critical segments of underpass polygons that intersect with building footprints.

    Args:
        gdf_underpass_polygons (GeoDataFrame): GeoDataFrame containing underpass polygons with columns 'underpass_id', 'building_id', and 'geometry'.
        gdf_building_footprints (GeoDataFrame): GeoDataFrame containing building footprints with columns 'building_id' and 'geometry'.
        buf_tol (float): Buffer tolerance for the intersection of underpass polygons with building fottprints.
        simpl_tol (float): Simplification tolerance for underpass polygons to reduce the number of points in the extracted segments.
        min_length (float): Minimum length of segments to be considered as critical.

    Returns:
        GeoDataFrame: A GeoDataFrame containing critical segments with columns 'segment_id', 'geometry', 'underpass_id', and 'building_id'.
    """

    # Intersect buildings with underpass polygons
    gdf_building_footprints = gdf_building_footprints.to_crs(gdf_underpass_polygons.crs)
    gdf_underpass_intersected = gpd.sjoin(gdf_underpass_polygons, gdf_building_footprints, how='inner', predicate='intersects')
    gdf_underpass_intersected = gdf_underpass_intersected[['underpass_id', 'building_id_left', 'geometry']].rename(columns={'building_id_left': 'building_id'})

    # Extract segments from intersected underpass polygons
    segment_records = []
    segment_id = 1
    for _, row in gdf_underpass_intersected.iterrows():
        underpass_id = row['underpass_id']
        building_id = row['building_id']

        # Simplify polygon to reduce the amount of points in the exracted segment
        poly = row['geometry'].simplify(tolerance=simpl_tol, preserve_topology=True)
        coords = list(poly.exterior.coords)

        building_geom = gdf_building_footprints.loc[gdf_building_footprints.building_id == building_id, 'geometry'].iloc[0]
        building_boundary_buffered = building_geom.boundary.buffer(buf_tol)

        for i in range(len(coords) - 1):
            candidate_segment = shapely.geometry.LineString([coords[i], coords[i+1]])
            # Intersect segment with buidling ID, if True, label as critical segment
            if candidate_segment.length < min_length:
                continue
            if candidate_segment.intersects(building_boundary_buffered):
                segment_records.append({'segment_id': segment_id, 'geometry': candidate_segment, 'underpass_id': underpass_id, 'building_id': building_id})
                segment_id += 1

    gdf_critical_segments = gpd.GeoDataFrame(segment_records, crs=gdf_underpass_polygons.crs)

    return gdf_underpass_intersected, gdf_critical_segments


def visualize_critical_segments(gdf_underpass_intersected, gdf_critical_segments):

    fig, ax = plt.subplots(figsize=(10, 10))

    gdf_critical_segments.plot(
        ax=ax,
        color="red",
        linewidth=3
    )
    gdf_underpass_intersected.plot(
        ax=ax,
        color="gray",
        linewidth=1
    )

    # ax.set_title("Critical Underpass Segments")
    ax.axis("off")
    ax.set_aspect("equal")
    plt.show()


def find_critical_walls(gdf_critical_segments, gdf_building_3d, buf_tol, extend_length):

    # Extract 3d wall polygons from buildings
    wall_polygon_records = []
    wall_polygon_id = 1
    for _, row in gdf_building_3d.iterrows():
        building_id = row['building_id']
        geom = row['geometry']
        if geom.geom_type == 'Polygon':
            wall_polygon_records.append({'wall_id': wall_polygon_id, 'geometry': geom, 'building_id': building_id})
            wall_polygon_id += 1
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                wall_polygon_records.append({'wall_id': wall_polygon_id, 'geometry': poly, 'building_id': building_id})
                wall_polygon_id += 1

    gdf_wall_polygons = gpd.GeoDataFrame(wall_polygon_records, crs=gdf_building_3d.crs)
    
    # Intersect 3d wall polygons with critical segments (buffered)
    gdf_critical_segments_buffered = gdf_critical_segments.copy()
    gdf_critical_segments_buffered['geometry'] = gdf_critical_segments_buffered.geometry.buffer(buf_tol)

    gdf_critical_segments_buffered = gdf_critical_segments_buffered.to_crs(gdf_wall_polygons.crs)
    gdf_walls_intersected = gpd.sjoin(gdf_wall_polygons, gdf_critical_segments_buffered, how='inner', predicate='intersects')
    gdf_walls_intersected = gdf_walls_intersected[['wall_id', 'geometry', 'segment_id', 'building_id_left', 'underpass_id']].rename(columns={'building_id_left': 'building_id'})

    # Create walls using the height of wall polygons and the segments
    wall_records = []
    wall_id = 1
    for segment_id, group in gdf_walls_intersected.groupby('segment_id'):
        # Find the maximum and minimum height of the wall polygons which belong to a segment
        max_z = -float('inf')
        min_z = float('inf')
        for geom in group['geometry']:
            for x, y, z in geom.exterior.coords:
                if z > max_z:
                    max_z = z
                elif z < min_z:
                    min_z = z
        # Find the geometry of the segment
        segment_geom = gdf_critical_segments[gdf_critical_segments['segment_id'] == segment_id]['geometry'].iloc[0]
        # bottom2d = list(segment_geom.coords)
        p1 = np.array(segment_geom.coords[0])
        p2 = np.array(segment_geom.coords[1])
        direction = p2 - p1
        length = np.linalg.norm(direction)
        if length == 0:
            continue
        direction_unit = direction / length
        # Extend walls on both sides (create wider walls)
        new_p1 = p1 - direction_unit * extend_length
        new_p2 = p2 + direction_unit * extend_length
        bottom2d = [tuple(new_p1), tuple(new_p2)]

        bottom3d = [(x, y, min_z) for x, y in bottom2d]
        upper3d = [(x, y, max_z) for x, y in reversed(bottom2d)]

        wall_coords = bottom3d + upper3d
        
        # Build the wall geometry
        wall_geom = shapely.geometry.polygon.orient(Polygon(wall_coords), sign=1.0)
        # Build wall records
        underpass_id = group['underpass_id'].iloc[0]
        wall_records.append({
            'wall_id': wall_id,
            'geometry': wall_geom,
            'wall_height': max_z - min_z,
            'underpass_id': underpass_id,
            'segment_id': segment_id,
            'building_id': group['building_id'].iloc[0]
        })
        wall_id += 1

    gdf_critical_walls = gpd.GeoDataFrame(wall_records, crs=gdf_wall_polygons.crs)

    return gdf_critical_walls


def visualize_critical_walls(gdf_critical_walls):

    plotter = pv.Plotter()
    for geom in gdf_critical_walls.geometry:
        if geom.geom_type == "Polygon":
            coords = np.array(geom.exterior.coords)
            poly = pv.PolyData(coords)
            poly.faces = np.hstack([[len(coords)], np.arange(len(coords))])
            plotter.add_mesh(poly, color="lightblue", show_edges=True)

    plotter.show()


def infere_image_visibility(gdf_image_footprints, gdf_critical_walls):

   # Intersect image footprints with critical walls
    gdf_image_footprints = gdf_image_footprints.to_crs(gdf_critical_walls.crs)
    gdf_image_visibility = gpd.sjoin(gdf_image_footprints, gdf_critical_walls, how='inner', predicate='intersects')

    gdf_image_visibility = (
        gdf_image_visibility
        .groupby("image_id", as_index=False)
        .agg({
            "wall_id": list,      
            "camera_x": "first",        
            "camera_y": "first",
            "camera_z": "first"        
        })
    )

    gdf_image_visibility = gdf_image_visibility[['image_id', 'wall_id', 'camera_x', 'camera_y', 'camera_z']].rename(columns={'wall_id': 'visible_walls'})

    # Check for the visibility of the walls, remove if not visible. One criterion: wall plane normal points towards camera plane
    # Other criteria to explore: angle bteween camera plane and facade less than a threshold; occlusion by other buildings
    # Create a column to store cosine between facade and camera plane. Later used for height correction.
    gdf_image_visibility['cos_theta'] = None
    for idx, row in gdf_image_visibility.iterrows():

        wall_ids = row['visible_walls']
        camera_x = row['camera_x']
        camera_y = row['camera_y']
        camera_z = row['camera_z']

        filtered_walls = []
        cos_theta_list = []
        for wall_id in wall_ids:
            # Get 3D geometry of the wall to calculate normal
            wall_geom_3d = gdf_critical_walls[gdf_critical_walls['wall_id'] == wall_id]['geometry'].iloc[0]
            coords = list(wall_geom_3d.exterior.coords)

            x1, y1, z1 = coords[0]
            x2, y2, z2 = coords[3]
            horiz_v = np.array([x2 - x1, y2 - y1, z2 - z1])

            x3, y3, z3 = coords[1]
            vert_v =np.array([x3-x1, y3-y1, z3-z1])

            # Compute and normalize wall normal
            wall_normal = np.cross(horiz_v, vert_v)
            wall_normal_norm = np.linalg.norm(wall_normal)
            if wall_normal_norm != 0:
                wall_normal = wall_normal / wall_normal_norm

            # Calculate center of the wall
            wall_center_x = (x1 + x2) / 2
            wall_center_y = (y1 + y2) / 2
            wall_center_z = (z1 + z2) / 2

            # Compute vector wall center - camera
            v = np.array([camera_x - wall_center_x, camera_y - wall_center_y, camera_z - wall_center_z], dtype=float)
            v_norm = np.linalg.norm(v)
            if v_norm != 0:
                v = v / v_norm

            cos_horizontal_angle = np.abs(np.dot(wall_normal, v))

            # Compute wall vertical direction
            bottom = np.array(coords[0])
            top = np.array(coords[1])
            wall_vertical = top - bottom
            wall_vertical_norm = np.linalg.norm(wall_vertical)
            if wall_vertical_norm != 0:
                wall_vertical = wall_vertical / wall_vertical_norm

            cos_vertical_angle = np.abs(np.dot(wall_vertical, v))

            cos_theta = cos_horizontal_angle * cos_vertical_angle

            # Perform dot product test. Remove if wall faces away the camera (<= 0)
            dot_product = np.dot(wall_normal, v)
            if dot_product < 0:
                filtered_walls.append(wall_id)
                cos_theta_list.append(cos_vertical_angle)

        gdf_image_visibility.at[idx, 'visible_walls'] = filtered_walls
        gdf_image_visibility.at[idx, 'cos_theta'] = cos_theta_list

    return gdf_image_visibility
    