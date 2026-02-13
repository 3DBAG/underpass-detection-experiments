import numpy as np
import os
import json
from functions import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Translate camera parameters to one file
external_params_path = os.path.join(PROJECT_ROOT, 'data/image_footprints/calibrated_external_camera_parameters.txt')
internal_params_path = os.path.join(PROJECT_ROOT, 'data/image_footprints/calibrated_camera_parameters.txt')
camera_params_path = os.path.join(PROJECT_ROOT, 'data/image_footprints/camera_parameters.txt')

# Translate camera parameters to one file
# with open(internal_params_path, 'r') as f:
#     lines = f.readlines()
#     i = 8
#     while i < len(lines):

#         line1 = lines[i].split()
#         img_id = line1[0]

#         img_width = line1[1]
#         img_height = line1[2]
        
#         line2 = lines[i+1].split()
#         fx = line2[0]
#         cx = line2[2]
        
#         line3 = lines[i+2].split()
#         fy = line3[1]
#         cy = line3[2]
        
#         i += 10

#         with open(external_params_path, 'r') as f:
#             external_lines = f.readlines()
#             for external_line in external_lines:
#                 external_params = external_line.split()
#                 if external_params[0] == img_id:
#                     x = external_params[1]
#                     y = external_params[2]
#                     z = external_params[3]
#                     omega = external_params[4]
#                     phi = external_params[5]
#                     kappa = external_params[6]
#                     break
        
#         with open(camera_params_path, 'a') as f:
#             f.write(f"{img_id} {img_width} {img_height} {x} {y} {z} {omega} {phi} {kappa} {fx} {fy} {cx} {cy}\n")
            
img_ids = []
with open(camera_params_path, 'r') as f:
    lines = f.readlines()
    i = 1
    while i < len(lines):
        params = lines[i].split()
        img_ids.append(params[0])
        i += 1

# Calculate image footprint for each image id 
image_footprints = []
for img_id in img_ids:

    with open(camera_params_path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            params = line.split()

            if params[0] != img_id:
                continue

            img = True
            # Image dimensions
            width = int(params[1])
            height = int(params[2])
            # Camera center coordinates
            x = float(params[3])
            y = float(params[4])
            z = float(params[5])
            # Camera rotation
            omega = np.deg2rad(float(params[6]))
            phi = np.deg2rad(float(params[7]))
            kappa = np.deg2rad(float(params[8]))
            # Focal length
            fx = float(params[9])
            fy = float(params[10])
            # Principal point
            cx = float(params[11])
            cy = float(params[12])

            break

        if not img:
            raise ValueError(f"Image ID {img_id} not found in parameters file.")
    

    # Compute camera matrix
    k = np.array([[fx, 0, cx],
                [0, fy, cy],
                [0, 0, 1]]).astype(np.float32)
    
    # Compute rotation matrix
    r = compute_r_matrix(omega, phi, kappa)

    # Compute translation vector
    t = -r @ np.array([[x], [y], [z]]).astype(np.float32).reshape(3, 1)

    image_footprint = compute_image_footprint(k, r, t, width, height, Z_ground=0)

    image_footprints.append(image_footprint)


# Save to geojson
json_output_path = os.path.join(PROJECT_ROOT, 'output/image_footprints/footprint.geojson')
os.makedirs(os.path.dirname(json_output_path), exist_ok=True)

features = []

for img_id, image_footprint in zip(img_ids, image_footprints):
    print(img_id)

    # Remove Z
    coords_2d = image_footprint[:, :2].tolist()

    # Close polygon
    coords_2d.append(coords_2d[0])

    feature = {
        "type": "Feature",
        "properties": {
            "image_id": img_id
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords_2d]
        }
    }

    features.append(feature)

geojson_dict = {
    "type": "FeatureCollection",
    "features": features
}

with open(json_output_path, "w") as f:
    json.dump(geojson_dict, f, indent=4)
