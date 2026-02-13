import cv2
import torch
import sys
import os
from matplotlib import pyplot as plt
import numpy as np
from functions import *
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
sys.path.append(os.path.join(PROJECT_ROOT, "Depth-Anything-V2"))

from depth_anything_v2.dpt import DepthAnythingV2

DEVICE = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'

model_configs = {
    'vits': {'encoder': 'vits', 'features': 64, 'out_channels': [48, 96, 192, 384]},
    'vitb': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
    'vitl': {'encoder': 'vitl', 'features': 256, 'out_channels': [256, 512, 1024, 1024]},
    'vitg': {'encoder': 'vitg', 'features': 384, 'out_channels': [1536, 1536, 1536, 1536]}
}

encoder = 'vitb' # or 'vits', 'vitb', 'vitg'

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

checkpoint_path = os.path.join(
    PROJECT_ROOT,
    "Depth-Anything-V2",
    "checkpoints",
    f"depth_anything_v2_{encoder}.pth"
)

model = DepthAnythingV2(**model_configs[encoder])
model.load_state_dict(torch.load(checkpoint_path, map_location="cpu"))
model = model.to(DEVICE).eval()

img_path = os.path.join(PROJECT_ROOT, 'data/height_estimation/403_0027_00133025/facade_2_rectified.png')
raw_img = cv2.imread(img_path)
start_time = time.time()
depth = model.infer_image(raw_img) # HxW raw depth map in numpy
end_time = time.time()  # End timer
elapsed = end_time - start_time
print(f"Execution time: {elapsed:.4f} seconds")

plt.imshow(depth)
plt.show()

# Normalize depth to 0–255
depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX)

# Convert to uint8
depth_uint8 = depth_norm.astype(np.uint8)

plt.imshow(depth_uint8, cmap='gray')
# plt.title("Normalized Depth")
# plt.show()

# Obtain real facade height
path = os.path.join(PROJECT_ROOT, f'data/height_estimation/403_0027_00133025', f'403_0027_00133025.off')
vertices = read_mesh_vertex(path)
facade_height = 0
for vertex in vertices:
    if vertex[2] > facade_height:
        facade_height = vertex[2]


# 1. Use depth clusters
image_height, image_width = depth.shape
depth_reshaped = depth.reshape(-1, 1)
# Convert to float32 for OpenCV
depth_reshaped = np.float32(depth_reshaped)
# Choose number of surfaces
K = 3
criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
_, labels, centers = cv2.kmeans(
    depth_reshaped,
    K,
    None,
    criteria,
    10,
    cv2.KMEANS_RANDOM_CENTERS
)
# Reshape labels back to image
segmented = labels.reshape(image_height, image_width)
plt.imshow(segmented)
plt.title("Depth Clusters")
plt.colorbar()
plt.show()

# Deepest cluster = cluster with largest center value
deepest_cluster_idx = np.argmin(centers)
print("Deepest cluster index:", deepest_cluster_idx)

# Create mask of deepest cluster
deepest_mask = (segmented == deepest_cluster_idx).astype(np.uint8) * 255

plt.imshow(deepest_mask, cmap='gray')
plt.title("Deepest Region")
plt.show()

# Find connected components to select only ground component
num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(deepest_mask)
bottoms = stats[:, cv2.CC_STAT_TOP] + stats[:, cv2.CC_STAT_HEIGHT]
deepest_component_idx = np.argmax(bottoms[1:]) + 1  # +1 because we skipped background
ground_region_mask = (labels == deepest_component_idx).astype(np.uint8) * 255

plt.imshow(ground_region_mask, cmap='gray')
plt.title("Ground Region of Deepest Cluster")
plt.show()

# Get coordinates of non-zero pixels
ys, xs = np.nonzero(ground_region_mask)
top_y = np.min(ys)
ceiling_row = top_y
ceiling_height = facade_height * (1 - ceiling_row / image_height)

print(f"    Facade height: {facade_height} m; Estimated underpass height: {ceiling_height} m")

# Draw estimated height line
img_vis = raw_img.copy()
cv2.line(
    img_vis,
    (0, ceiling_row),                     
    (img_vis.shape[1], ceiling_row),      
    (0, 0, 255), 3                                     
)
plt.imshow(img_vis)
plt.show()


# 2. Fit Hough transform lines
# 3. Extract connected components

# # 1. Applying Hough lines method
# grad_y = cv2.Sobel(depth_uint8, cv2.CV_64F, 0, 1, ksize=3)
# grad_y = np.absolute(grad_y)
# grad_y = np.uint8(255 * grad_y / np.max(grad_y))

# edges = cv2.Canny(grad_y, 30, 100)

# # Hough Lines
# lines = cv2.HoughLinesP(
#     edges,
#     rho=1,
#     theta=np.pi/180,
#     threshold=100,
#     minLineLength=100,
#     maxLineGap=10
# )

# # Draw lines
# output = cv2.cvtColor(depth_uint8, cv2.COLOR_GRAY2BGR)

# if lines is not None:
#     for line in lines:
#         x1, y1, x2, y2 = line[0]
#         cv2.line(output, (x1,y1), (x2,y2), (0,0,255), 2)

# plt.imshow(output)
# plt.show()

# # Generalize horizontal lines
# if lines is None:
#     print("No lines detected")
# else:
#     # Convert to simple list of tuples
#     lines_list = [l[0] for l in lines]

#     # Keep only near-horizontal lines
#     horizontal_lines = []
#     for x1, y1, x2, y2 in lines_list:
#         if abs(y2 - y1) < 10:  # horizontal tolerance
#             horizontal_lines.append([x1, y1, x2, y2])

#     # Sort by y coordinate
#     horizontal_lines.sort(key=lambda l: l[1])

#     merged_lines = []
#     used = [False] * len(horizontal_lines)

#     for i in range(len(horizontal_lines)):
#         if used[i]:
#             continue

#         x1, y1, x2, y2 = horizontal_lines[i]
#         min_x = min(x1, x2)
#         max_x = max(x1, x2)
#         avg_y = (y1 + y2) // 2

#         for j in range(i + 1, len(horizontal_lines)):
#             if used[j]:
#                 continue

#             ox1, oy1, ox2, oy2 = horizontal_lines[j]

#             # If close in vertical direction
#             if abs(avg_y - oy1) < 10:
#                 min_x = min(min_x, ox1, ox2)
#                 max_x = max(max_x, ox1, ox2)
#                 used[j] = True

#         merged_lines.append([min_x, avg_y, max_x, avg_y])
#         used[i] = True

#     # Draw results
#     output_generalized = output.copy()

#     for x1, y1, x2, y2 in merged_lines:
#         cv2.line(output_generalized, (x1, y1), (x2, y2), (0, 0, 255), 2)

#     plt.imshow(output_generalized)
#     plt.title("Merged Horizontal Lines")
#     plt.show()


        



