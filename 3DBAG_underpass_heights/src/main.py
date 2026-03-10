import os
import cv2
import numpy as np
from statistics import mean

import data_preprocessing
import perspective_projection
import facade_extraction
import height_estimation

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# ----------------------------------
# 1. DEFINE INPUT DATA
# ----------------------------------
# Select height estimation method
height_estimation_method = "cc_method" # "cc_method", "depth_method", "unet_method"

# Load model if needed
if height_estimation_method == "depth_method":
    depth_map_model = height_estimation.load_depth_map_model()
elif height_estimation_method == "unet_method":
    unet_device, unet_model = height_estimation.load_unet_model()

# Define output file according to selected method
if height_estimation_method == "cc_method":
    output_path = os.path.join(PROJECT_ROOT, 'output/underpass_heights_ccmethod.geojson')
elif height_estimation_method == "depth_method":
    output_path = os.path.join(PROJECT_ROOT, 'output/underpass_heights_depthmethod.geojson')
elif height_estimation_method == "unet_method":
    output_path = os.path.join(PROJECT_ROOT, 'output/underpass_heights_unetmethod.geojson')

tiles_directory = os.path.join(PROJECT_ROOT, 'data/3dbag_tiles')
images_directory = os.path.join(PROJECT_ROOT, 'data/oblique_images')
underpasses_directory = os.path.join(PROJECT_ROOT, 'data/underpass_polygons')

camera_parameters_path = os.path.join(images_directory, 'camera_parameters.txt')
image_footprints_path = os.path.join(images_directory, 'image_footprints.geojson')
underpasses_path = os.path.join(underpasses_directory, 'underpasses.geojson')

# ----------------------------------
# 2. LOAD INPUT DATA IN GEOPANDAS DATAFRAMES
# ----------------------------------
df_camera_parameters, gdf_image_footprints, gdf_underpass_polygons = data_preprocessing.load_input_data(camera_parameters_path, 
                                                                                                  image_footprints_path, 
                                                                                                  underpasses_path)
# print("Camera parameters table: \n", df_camera_parameters.head(), "\n")
# print("Image footprints table: \n", gdf_image_footprints.head(), "\n")
# print("Underpasses table: \n", gdf_underpass_polygons.head(), "\n")

# ----------------------------------
# 3. ITERATE OVER EACH 3D BAG TILE (GEOJSON)
# ----------------------------------
img_number = 1 # For saving the dataset
for filename in os.listdir(tiles_directory):

    # Load building lod-0 and lod-22 geometries
    tile = os.path.join(tiles_directory, filename)
    gdf_building_footprints, gdf_building_3d = data_preprocessing.load_tile_data(tile)

    # print("Building footprints table: \n", gdf_building_footprints.head(), "\n")
    # print("Building 3D table: \n", gdf_building_3d.head(), "\n")

    # ----------------------------------
    # 4. FIND CRITICAL SEGMENTS (INTERSECTION OF BUILDING FOOTPRINTS WITH UNDERPASSES)
    # ----------------------------------
    gdf_underpass_intersected, gdf_critical_segments = data_preprocessing.find_critical_segments(gdf_underpass_polygons, 
                                                                      gdf_building_footprints,
                                                                      buf_tol=0.1,
                                                                      simpl_tol=0.2,
                                                                      min_length=2)
    
    # print("Critical segments table: \n", gdf_critical_segments.head(), "\n")
    # Visualize critical segments
    # data_preprocessing.visualize_critical_segments(gdf_underpass_intersected, gdf_critical_segments)

    # ----------------------------------
    # 5. FIND CRITICAL WALLS (EXTRUDE CRITICAL SEGMENTS TO 3D)
    # ----------------------------------
    gdf_critical_walls = data_preprocessing.find_critical_walls(gdf_critical_segments, 
                                                                gdf_building_3d, 
                                                                buf_tol=0.5,
                                                                extend_length=1)
    
    # print("Critical walls table: \n", gdf_critical_walls.head(), "\n")
    # Visualize critical walls in 3d
    # data_preprocessing.visualize_critical_walls(gdf_critical_walls)

    # ----------------------------------
    # 6. CONSTRUCT IMAGE - WALL VISIBILITY TABLE (INTERSECTION OF CRITICAL WALLS WITH IMAGE FOOTPRINTS)
    # ----------------------------------
    gdf_image_visibility = data_preprocessing.infere_image_visibility(gdf_image_footprints, 
                                                                      gdf_critical_walls)

    print("Selected images table: \n", gdf_image_visibility.head(), "\n")

    # ----------------------------------
    # 7. PERFORM PERSPECTIVE PROJECTION OF CRITICAL WALLS ONTO OBLIQUE IMAGES
    # ----------------------------------
    for _, row in gdf_image_visibility.iterrows():

        image_id = row['image_id']
        # !!!Change for proper datasets (special case for Almere dataset)
        img_prefix = image_id[:3]  
        oblique_image_path = os.path.join(images_directory, f"{image_id}")                                                      
        oblique_image = cv2.imread(oblique_image_path)  
        wall_ids = row['visible_walls']

        if len(wall_ids) == 0:
            continue
        if oblique_image is None:
            continue  
        # !!!Change for proper datasets (special case for Almere dataset)
        if img_prefix == '403' or img_prefix == '405':
            continue                                   
        
        rectangles_2d = perspective_projection.project_walls_on_image(oblique_image, 
                                                      image_id, 
                                                      img_prefix,
                                                      wall_ids,
                                                      df_camera_parameters, 
                                                      gdf_critical_walls)
        # Visualize image with projected walls
        # perspective_projection.display_image(rectangles_2d, oblique_image)

        # ----------------------------------
        # 8. EXTRACT FACADE TEXTURE FROM EVERY PROJECTED WALL
        # ----------------------------------
        for wall_id, rect_2d in zip(wall_ids, rectangles_2d):
            
            facade_image = facade_extraction.extract_facade(rect_2d, oblique_image)

            # Display facade image
            facade_extraction.display_facade_image(facade_image)

            # ----------------------------------
            # 9. ESTIMATE UNDERPASS HEIGHT APPLYING SELECTED METHOD
            # ----------------------------------
            # Obtain real facade height
            facade_height = gdf_critical_walls[gdf_critical_walls['wall_id'] == wall_id]['wall_height'].iloc[0]

            if height_estimation_method == "cc_method":
                pixel_row, underpass_height = height_estimation.apply_cc_method(facade_image, 
                                                                                facade_height,
                                                                                min_height=2,
                                                                                ground_dist=100,
                                                                                top_dist=50,
                                                                                min_solidity=0.5)
            elif height_estimation_method == "depth_method":
                pixel_row, underpass_height = height_estimation.apply_depth_method(facade_image, 
                                                                                facade_height, 
                                                                                depth_map_model, 
                                                                                k=3)
            elif height_estimation_method == "unet_method":
                pixel_row, underpass_height = height_estimation.apply_unet_method(facade_image, 
                                                                                facade_height, 
                                                                                unet_model,
                                                                                unet_device)
                
            if underpass_height is not None:
                # print(f"    Facade height: {facade_height} m; Estimated underpass height: {underpass_height} m")
                # Visualize estimated underpass height image
                # height_estimation.display_image(facade_image, pixel_row)

                # Record observation in underpass GeoDataFrame
                height_estimation.record_observation(gdf_underpass_polygons, gdf_critical_walls, wall_id, underpass_height)
                
            else:
                # print(f"    Facade height: {facade_height} m; Estimated underpass height: Undetermined")
                # Skip to next wall if height estimation failed
                continue

    # ----------------------------------
    # 10. ESTIMATE HEIGHT OF UNDERPASSES FROM OBSERVATIONS
    # ----------------------------------
    # Method 1: Compute average height from observations for each underpass
    gdf_underpass_polygons['estimated_height'] = gdf_underpass_polygons['observed_heights'].apply(lambda x: mean(x) if len(x) > 0 else None)
    # Visualize updated underpass polygons
    updated_underpasses = gdf_underpass_polygons[gdf_underpass_polygons['estimated_height'].notna()]
    print("Updated underpass polygons with estimated heights: \n", updated_underpasses.head(), "\n")

# ----------------------------------
# 11. WRITE RESULTS TO GEOJSON
# ----------------------------------
gdf_output = gdf_underpass_polygons[['underpass_id', 'building_id', 'geometry', 'estimated_height']]
height_estimation.write_geojson(gdf_output, output_path)
    


