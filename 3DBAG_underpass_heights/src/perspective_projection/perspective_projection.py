"""
Finds corresponding 3D points --> 2D points and draws building facades on image
"""

import os
import cv2
from functions import *

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# 1. Read points in world coordinates (pw), and rectangles (facades) for projection
off_file_path = os.path.join(PROJECT_ROOT, 'data/perspective_projection', 'LOD22_walls.off')
print("Input mesh: ", off_file_path)

# Read mesh vertices (in world coordinates)
pw = read_mesh_vertex(off_file_path)

# 2. Translate points to camera coodinates system (pc)
extrinsic_params = os.path.join(PROJECT_ROOT, 'data/perspective_projection', 'calibrated_external_camera_parameters.txt')
img_id = '404_0029_00131853.tif'

# Get camera center c and rotation matrix r
camera_origin, r = get_extrinsic_params(extrinsic_params, img_id)
# Transform world coordinate points (pw) to camera coordinate points (pc)
pc = get_camera_coordinates(pw, camera_origin, r)

# Read mesh faces
faces, colors = read_mesh_faces(off_file_path)
# Filter surfaces: keep only walls
wallsurface, new_color_list1 = wallsurface_filter_bynormal(faces, colors, pc)
# Group faces by color (same facade)
grouped_faces, new_color_list = merge_surface(faces, colors, pc)
# Retrieve rectangles representing facades
rectangles, else_polygon = get_off_3Dfootprint(grouped_faces, pc)
rectangles_3d = rectangles.copy()

# 3. Project 3D rectangles (facades) to 2D image coordinates
# Get camera intrinsic parameters
intrinsic_params = os.path.join(PROJECT_ROOT, 'data/perspective_projection', 'calibrated_camera_parameters.txt')
c, f = get_intrinsic_params(intrinsic_params, img_id)

# Load source image
image = cv2.imread(os.path.join(PROJECT_ROOT, 'data/perspective_projection', img_id))


def reorder_rectangle_points(rect):
    rect = [list(p) for p in rect]  # ensure list, not np array

    # Split by depth (Z)
    near = sorted(rect, key=lambda p: p[2], reverse=True)[:2]
    far  = sorted(rect, key=lambda p: p[2])[:2]

    # Sort by vertical axis (Y)
    near = sorted(near, key=lambda p: p[1])  # bottom → top
    far  = sorted(far,  key=lambda p: p[1])  # bottom → top

    # CCW order
    return [
        near[0],  # bottom-near
        far[0],   # bottom-far
        far[1],   # top-far
        near[1]   # top-near
    ]

# Project each facade on image
for rect_3d in rectangles_3d:
    # Re-order rectangle points to have correct drawing order
    rect_3d = reorder_rectangle_points(rect_3d)
    # Project 3D rectangle corners to 2D image coordinates
    rect_2d = project_3d_2d(rect_3d, c, f)
    rect_2d = np.array(rect_2d, dtype=np.int32)
    # Draw projected rectangle on image
    cv2.polylines(image, [rect_2d], True, (0, 0, 255), 10)
    
    

# Save output image with projected facades
output_image = os.path.join(PROJECT_ROOT, 'output/perspective_projection', 'projected_facades.jpg')
os.makedirs(os.path.dirname(output_image), exist_ok=True)
cv2.imwrite(output_image, image)

# Email Xia
# Execute her code to get an idea of what the output should look like: figure out differences
# Make the code work with the simplest case: project a point onto the image
# Input Rotterdam data in Xia's code

