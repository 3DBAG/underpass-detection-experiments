"""
Finds corresponding 3D points --> 2D points and draws building facades on image
"""

import os
import cv2
from functions import *

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Load resources and name variables (image_id, mesh file path, camera parameters file path)
img_id = '402_0030_00131343.tif'
mesh_path = os.path.join(PROJECT_ROOT, 'data/perspective_projection', '402_0030_00131343.off')
camera_parameters_path = os.path.join(PROJECT_ROOT, 'data/perspective_projection', 'camera_parameters.txt')


# 1. Read points in world coordinates (pw) and rectangles (facades) 
# Read mesh vertices (in world coordinates)
pw = read_mesh_vertex(mesh_path)
# Read mesh faces
faces, colors = read_mesh_faces(mesh_path)
# Filter surfaces: keep only walls
wallsurface, new_color_list1 = wallsurface_filter_bynormal(faces, colors, pw)
# Group faces by color (same facade)
grouped_faces, new_color_list = merge_surface(faces, colors, pw)
# Retrieve rectangles representing facades
rectangles, else_polygon = get_off_3Dfootprint(grouped_faces, pw)
rectangles_3d = rectangles.copy()


# 2. Project facades (rectangles) on 2D image
facades_2d = []
for rect_3d in rectangles_3d:
    rect_2d = project_3d_2d(rect_3d, img_id, camera_parameters_path)
    # rect_2d = projection(img_id, rect_3d)
    facade_2d = np.array(rect_2d, dtype=np.int32)
    facades_2d.append(facade_2d)

image = cv2.imread(os.path.join(PROJECT_ROOT, 'data/perspective_projection', img_id))
for facade_2d in facades_2d:
    cv2.polylines(image, [facade_2d], True, (0, 0, 255), 10)

output_image = os.path.join(PROJECT_ROOT, 'output/perspective_projection', 'projected_facades.jpg')
os.makedirs(os.path.dirname(output_image), exist_ok=True)
cv2.imwrite(output_image, image)


# 3. Extract facade textures
for index, facade_2d in enumerate(facades_2d):
    # Read image with projected facades
    img = cv2.imread(output_image)
    # Load projected rectangle
    rectangle = np.array(facade_2d, dtype="float32")

    # Compute output size
    width = int(np.sqrt(((rectangle[0][0] - rectangle[3][0]) ** 2) + ((rectangle[0][1] - rectangle[3][1]) ** 2)))
    width2 = int(np.sqrt(((rectangle[1][0] - rectangle[2][0]) ** 2) + ((rectangle[1][1] - rectangle[2][1]) ** 2)))
    width = max(width, width2)

    height = int(np.sqrt(((rectangle[0][0] - rectangle[1][0]) ** 2) + ((rectangle[0][1] - rectangle[1][1]) ** 2)))
    height2 = int(np.sqrt(((rectangle[2][0] - rectangle[3][0]) ** 2) + ((rectangle[2][1] - rectangle[3][1]) ** 2)))
    height = max(height, height2)

    # Destination rectangle
    output_rectangle = np.array([
        [0, 0],
        [0, height-1],
        [width-1, height-1],
        [width-1, 0]
    ], dtype="float32")

    # Perspective transform
    M = cv2.getPerspectiveTransform(rectangle, output_rectangle)
    warped = cv2.warpPerspective(img, M, (width, height), flags=cv2.INTER_LINEAR)
    cv2.imwrite(os.path.join('output/perspective_projection', f"facade_{index+1}_rectified.png"), warped)



