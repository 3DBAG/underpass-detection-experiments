import os
import time
import cv2
from statistics import mean
from tqdm import tqdm
import gc

import data_preprocessing
import perspective_projection
import facade_extraction
import height_estimation

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Measure total script runtime
run_start = time.perf_counter()


# 1. DEFINE INPUT DATA
# --------------------
# Select height estimation method
height_estimation_method = "unet_method" # "cc_method", "depth_method", "unet_method"

# Define input directories and files
tiles_directory = os.path.join(PROJECT_ROOT, 'data/3dbag_tiles')
images_directory = os.path.join(PROJECT_ROOT, 'data/oblique_images')
underpasses_directory = os.path.join(PROJECT_ROOT, 'data/underpass_polygons')
depth_model_directory = os.path.join(PROJECT_ROOT, 'src/Depth-Anything-V2')
unet_model_directory = os.path.join(PROJECT_ROOT, 'src/u-net_model')

camera_parameters_path = os.path.join(images_directory, 'camera_parameters.txt')
image_footprints_path = os.path.join(images_directory, 'image_footprints.geojson')
underpasses_path = os.path.join(underpasses_directory, 'underpasses.geojson')
# Inpute None if underpass edges are not provided, otherwise provide path to underpass edges geojson
underpass_edges_path = os.path.join(underpasses_directory, 'underpass_edges.geojson')

# Load model if needed
if height_estimation_method == "depth_method":
    depth_map_model = height_estimation.load_depth_map_model(depth_model_directory)
elif height_estimation_method == "unet_method":
    unet_device, unet_model = height_estimation.load_unet_model(unet_model_directory)

# Define output file according to selected method
if height_estimation_method == "cc_method":
    output_path = os.path.join(PROJECT_ROOT, 'output/underpass_heights_ccmethod.geojson')
elif height_estimation_method == "depth_method":
    output_path = os.path.join(PROJECT_ROOT, 'output/underpass_heights_depthmethod.geojson')
elif height_estimation_method == "unet_method":
    output_path = os.path.join(PROJECT_ROOT, 'output/underpass_heights_unetmethod.geojson')


# 2. LOAD INPUT DATA IN GEOPANDAS DATAFRAMES
# ------------------------------------------
df_camera_parameters, gdf_image_footprints, gdf_underpass_polygons, gdf_underpass_edges = data_preprocessing.load_input_data(camera_parameters_path, image_footprints_path, 
                                                                                                                            underpasses_path,underpass_edges_path, min_length=2)


# 3. ITERATE OVER EACH 3D BAG TILE (GEOJSON)
# ------------------------------------------
for filename in tqdm(os.listdir(tiles_directory), desc="Processed tiles", unit="tile"):

    # Load building footprints and 3D geometries
    tile = os.path.join(tiles_directory, filename)
    gdf_building_footprints, gdf_building_3d = data_preprocessing.load_tile_data(tile)


    # 4. FIND CRITICAL EDGES (INTERSECTION OF BUILDING FOOTPRINTS WITH UNDERPASSES) 
    # (ONLY IF underpass edges are not provided)
    # -----------------------------------------------------------------------------
    gdf_critical_edges = None
    if gdf_underpass_edges is None:
        gdf_underpass_intersected, gdf_critical_edges = data_preprocessing.find_critical_edges(gdf_underpass_polygons, gdf_building_footprints, buf_tol=0.1,
                                                                                                simpl_tol=0.2, min_length=2)
        # Visualize critical edges
        # data_preprocessing.visualize_critical_edges(gdf_underpass_intersected, gdf_critical_edges)


    # 5. FIND CRITICAL WALLS (EXTRUDE CRITICAL EDGES TO 3D)
    # -----------------------------------------------------
    gdf_critical_walls = data_preprocessing.find_critical_walls(gdf_critical_edges, gdf_underpass_edges, gdf_building_3d, 
                                                                buf_tol=0.5, extend_length=0)
    # Visualize critical walls in 3d
    # data_preprocessing.visualize_critical_walls(gdf_critical_walls)


    # 6. CONSTRUCT IMAGE - WALL VISIBILITY TABLE (INTERSECTION OF CRITICAL WALLS WITH IMAGE FOOTPRINTS)
    # -------------------------------------------------------------------------------------------------
    gdf_image_visibility = data_preprocessing.infere_image_visibility(gdf_image_footprints, gdf_critical_walls, theta=60)


    # 7. PERFORM PERSPECTIVE PROJECTION OF CRITICAL WALLS ONTO OBLIQUE IMAGES
    # -----------------------------------------------------------------------
    for _, row in tqdm(gdf_image_visibility.iterrows(), total=len(gdf_image_visibility), desc=f"Processing images for tile {filename}", unit="image", leave=False):

        wall_ids = row['visible_walls']
        if len(wall_ids) == 0:
            continue
    
        image_id = row['image_id']
        oblique_image_path = os.path.join(images_directory, f"{image_id}")                                                      
        oblique_image = cv2.imread(oblique_image_path)  

        if oblique_image is None:
            continue                                  
        
        rectangles_2d = perspective_projection.project_walls_on_image(image_id, wall_ids, df_camera_parameters, gdf_critical_walls)
        
        if len(rectangles_2d) == 0:
            continue

        # Visualize image with projected walls
        # perspective_projection.display_image(rectangles_2d, oblique_image, limit_width = 1920, limit_height = 1080, linewidth = 10)


        # 8. EXTRACT FACADE TEXTURE FROM EVERY PROJECTED WALL
        # ---------------------------------------------------
        for wall_id, rect_2d in zip(wall_ids, rectangles_2d):

            # Skip if projection was invalid
            if rect_2d is None:
                continue
            
            facade_image = facade_extraction.extract_facade(rect_2d, oblique_image)

            if facade_image is None:
                continue

            # Display facade image
            # facade_extraction.display_facade_image(facade_image)


            # 9. ESTIMATE UNDERPASS HEIGHT APPLYING SELECTED METHOD
            # -----------------------------------------------------
            # Obtain real facade height
            facade_height = gdf_critical_walls[gdf_critical_walls['wall_id'] == wall_id]['wall_height'].iloc[0]

            # Apply selected height estimation method
            try:
                if height_estimation_method == "cc_method":
                    pixel_row, underpass_height = height_estimation.apply_cc_method(facade_image, facade_height, min_height=2, ground_dist=100, top_dist=50, min_solidity=0.5)
            
                elif height_estimation_method == "depth_method":
                    pixel_row, underpass_height = height_estimation.apply_depth_method(facade_image, facade_height, depth_map_model, k=3)

                elif height_estimation_method == "unet_method":
                    pixel_row, underpass_height = height_estimation.apply_unet_method(facade_image, facade_height, unet_model, unet_device)
                
            except RuntimeError as e:
                if "out of memory" in str(e):
                    print(f"Out of Memory on wall_id {wall_id}, skipping this image.")
                    torch.cuda.empty_cache()
                    gc.collect()
                    continue
                else:
                    raise e  
                

            if underpass_height is not None:

                # Visualize estimated underpass height image
                # height_estimation.display_image(facade_image, pixel_row)

                # Record observation in underpass GeoDataFrame
                height_estimation.record_observation(gdf_underpass_polygons, gdf_critical_walls, wall_id, underpass_height)
                
            else:

                # Skip to next wall if height estimation failed
                continue
            
            # Release memory    
            del facade_image
            torch.cuda.empty_cache()
            gc.collect()


    # 10. ESTIMATE HEIGHT OF UNDERPASSES FROM OBSERVATIONS
    # ----------------------------------------------------
    # Method 1: Compute average height from observations for each underpass
    gdf_underpass_polygons['estimated_height'] = gdf_underpass_polygons['observed_heights'].apply(lambda x: mean(x) if len(x) > 0 else None)


# 11. WRITE RESULTS TO GEOJSON
# ----------------------------
gdf_output = gdf_underpass_polygons[['underpass_id', 'building_id', 'geometry', 'estimated_height']]
height_estimation.write_geojson(gdf_output, output_path)

elapsed_seconds = time.perf_counter() - run_start
print(f"Total runtime for {height_estimation_method}: {elapsed_seconds:.2f} s ({elapsed_seconds / 60:.2f} min)")
    


