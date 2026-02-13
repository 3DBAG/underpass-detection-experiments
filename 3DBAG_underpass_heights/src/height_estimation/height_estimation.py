import os
import cv2
from matplotlib import pyplot as plt
from functions import *

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Define list of image IDs for height estimation
img_ids = ['402_0030_00131343', '403_0027_00133025']

for img_id in img_ids:
    print(f"Estimating height for {img_id}")
    facade_nr = 1
    while True:
        try:
            # Load image
            facade_path = os.path.join(PROJECT_ROOT, f'data/height_estimation/{img_id}', f'facade_{facade_nr}_rectified.png')
            image = cv2.imread(facade_path)

            # Obtain real facade height
            path = os.path.join(PROJECT_ROOT, f'data/height_estimation/{img_id}', f'{img_id}.off')
            vertices = read_mesh_vertex(path)
            facade_height = 0
            for vertex in vertices:
                if vertex[2] > facade_height:
                    facade_height = vertex[2]

            # 1. Connected components method 
            # Apply Canny filter to image
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3,3), 0)
            edges = cv2.Canny(gray, 30, 100)
            plt.imshow(edges)
            plt.show()
            # Apply morphology
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            plt.imshow(edges)
            plt.show()
            # Detect lines 

            # Apply connected cmponents 
            blur = cv2.GaussianBlur(edges, (3,3), 0)
            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            # plt.imshow(thresh)
            # plt.show()
            n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=4)
            # Create false color image with black background and colored objects
            colors = np.random.randint(0, 255, size=(n_labels, 3), dtype=np.uint8)
            colors[0] = [0, 0, 0]
            false_colors = colors[labels]
            plt.imshow(false_colors)
            plt.show()

            # Create a mask for large components only
            filtered_mask = np.zeros_like(thresh)

            # Keep components which height is at least 2 meters
            min_height_m = 2
            image_height = image.shape[0]  # pixels
            facade_height_m = facade_height  # in meters

            # Convert meters to pixels
            min_height_px = int(image_height * (min_height_m / facade_height_m))
            ground_dist = 50
            top_dist = 50  

            filtered_mask = np.zeros_like(labels, dtype=np.uint8)

            for i in range(1, n_labels):  # skip background
                comp_height = stats[i, cv2.CC_STAT_HEIGHT]
                comp_width = stats[i, cv2.CC_STAT_WIDTH]
                comp_top = stats[i, cv2.CC_STAT_TOP]
                comp_bottom = comp_top + comp_height
                comp_area = stats[i, cv2.CC_STAT_AREA]
                solidity = comp_area / (comp_height * comp_width)

                if (
                    comp_top >= top_dist and
                    comp_height >= min_height_px and
                    comp_bottom >= image_height - ground_dist and
                    solidity >= 0.6
                    ):
                    filtered_mask[labels == i] = 255

            # Pick most centered component out of the remaining
            img_cx = image.shape[1] / 2

            remaining_labels = [
            i for i in range(1, n_labels)
            if np.any(filtered_mask[labels == i])
            ]

            if remaining_labels:
                best_label = min(
                    remaining_labels,
                    key=lambda i: abs(centroids[i][0] - img_cx)
                )

                # Keep only the best label
                final_mask = np.zeros_like(filtered_mask)
                final_mask[labels == best_label] = 255
            else:
                final_mask = filtered_mask.copy()
        

            # Now filtered_mask contains only large components
            false_colors_height_filtered = false_colors.copy()
            false_colors_height_filtered[final_mask == 0] = 0

            plt.imshow(false_colors_height_filtered)
            plt.show()

            ceiling_row = stats[best_label, cv2.CC_STAT_TOP]
            ceiling_height = facade_height * (1 - ceiling_row / image_height)

            print(f"    Facade {facade_nr} height: {facade_height} m; Estimated underpass height: {ceiling_height} m")

            img_vis = image.copy()

            cv2.line(
                img_vis,
                (0, ceiling_row),                     
                (img_vis.shape[1], ceiling_row),      
                (0, 0, 255), 3                                     
            )

            image_height_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_estimated.jpg')
            os.makedirs(os.path.dirname(image_height_path), exist_ok=True)
            cv2.imwrite(image_height_path, img_vis)
            plt.imshow(img_vis)
            plt.show()

            


            # lines = cv2.HoughLinesP(
            #     edges,
            #     rho=1,
            #     theta=np.pi/180,
            #     threshold=80,
            #     minLineLength=10,
            #     maxLineGap=15
            # )

            # img = image.copy()
            # for line in lines:
            #     x1, y1, x2, y2 = line[0][0], line[0][1], line[0][2], line[0][3] 
            #     if abs(y2-y1) < 10:
            #         cv2.line(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            # image_lines_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_lines.jpg')

            # h, w, _ = image.shape

            # horizontals = []
            # for line in lines:
            #     x1, y1, x2, y2 = line[0][0], line[0][1], line[0][2], line[0][3] 
            #     if abs(y2-y1) < 10:
            #         # Draw a horizontal line
            #         y_mean = int((y1+y2)/2)
            #         horizontals.append(y_mean)
            #         cv2.line(img, (0, y_mean), (w, y_mean), (255, 255, 0), 2)

            # cv2.imwrite(image_lines_path, img)

            # # Start looking at pixels located at 2 meters or higher
            # start_row = int(h * (1 - 2 / facade_height))
            # ceiling_row = -1

            # for y in horizontals:
            #     if y < start_row and y > ceiling_row:
            #         ceiling_row = y

            # ceiling_height = facade_height * (1 - ceiling_row / h)

            # print(f"    Facade {facade_nr} height: {facade_height} m; Estimated underpass height: {ceiling_height} m")

            # estimated = image.copy()
            # cv2.line(estimated, (0, ceiling_row), (w,ceiling_row), (0, 0, 255), 2)

            # image_height_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_estimated.jpg')
            # os.makedirs(os.path.dirname(image_height_path), exist_ok=True)
            # cv2.imwrite(image_height_path, estimated)
            
            

            # Apply connected cmponents 
            # blur = cv2.GaussianBlur(edges, (3,3), 0)
            # thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            # plt.imshow(thresh)
            # plt.show()

        

            

            # # 1. Brightness gradient method
            # # Convert image to gray scale and smooth
            # gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # gray = cv2.GaussianBlur(gray, (5,5), 0)
            # # Compute vertical brightness profile
            # profile = gray.mean(axis=1)
            # # Detect abrupt brightness drop (potential ceiling edge)
            # row_strength = np.diff(profile)
            # ceiling_row = np.argmin(row_strength)

            # 2. Canny filter method
            # Apply Sobel filter
            # gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # gray = cv2.GaussianBlur(
            #     gray,
            #     ksize=(3, 3),
            #     sigmaX=8,
            #     sigmaY=8
            # )
            # sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            # sobel_y = cv2.convertScaleAbs(sobel_y)
            # # Save image with Sobel filter
            # image_sobel_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_sobel.jpg')
            # cv2.imwrite(image_sobel_path, sobel_y)
            # # Apply Canny filter to detect edges
            # edges = cv2.Canny(gray, 50, 120)
            # # Save image with applied filter
            # image_canny_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_canny.jpg')
            # cv2.imwrite(image_canny_path, edges)
            # # Detect horizontal lines, keep only theese
            # lines = cv2.HoughLinesP(
            #     edges,
            #     rho=1,
            #     theta=np.pi/180,
            #     threshold=100,
            #     minLineLength=30,
            #     maxLineGap=30
            # )
            # img = image.copy()
            # for line in lines:
            #     x1, y1, x2, y2 = line[0][0], line[0][1], line[0][2], line[0][3] 
            #     if abs(y2-y1) < 10:
            #         cv2.line(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            # image_lines_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_lines.jpg')
            # cv2.imwrite(image_lines_path, img)

            # # Sum edgeds along rows to find the strongest edge continuity
            # row_strength = edges.sum(axis=1)
            # # Find the row with the highest strength
            # ceiling_row = np.argmax(row_strength)
            # # Tune parameters minVal, maxVal...

            # 3. Sobel filter method
            # gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

            # Save image with applied filter
            # grad_y_abs = np.abs(grad_y)
            # grad_y_norm = cv2.normalize(
            #                 grad_y_abs,
            #                 None,
            #                 alpha=0,
            #                 beta=255,
            #                 norm_type=cv2.NORM_MINMAX
            #             ).astype(np.uint8)
            # image_sobel_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_sobel.jpg')
            # cv2.imwrite(image_sobel_path, grad_y_norm)

            #  # Detect horizontal lines, keep only theese
            # lines = cv2.HoughLinesP(
            #     grad_y_norm,
            #     rho=1,
            #     theta=np.pi/180,
            #     threshold=20,
            #     minLineLength=20,
            #     maxLineGap=30
            # )
            # img = image.copy()
            # for line in lines:
            #     x1, y1, x2, y2 = line[0][0], line[0][1], line[0][2], line[0][3] 
            #     if abs(y2-y1) < 10:
            #         cv2.line(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
            # image_lines_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_lines.jpg')
            # cv2.imwrite(image_lines_path, img)

            # Calculate row strength and select maximum strength
            # row_strength = np.abs(grad_y).mean(axis=1)
            # ceiling_row = np.argmax(row_strength)

            # Calculate ceiling height
            # image_height, image_width, _ = image.shape
            # ceiling_height = facade_height * (1 - ceiling_row / image_height)

            # # Discard false positives and recalculate
            # while (ceiling_height < 2) or ((facade_height - ceiling_height) < 0.25):
            #     # Assign 0 value to current ceiling row to (find next strongest edge)
            #     row_strength[ceiling_row] = 0
            #     ceiling_row = np.argmax(row_strength)
            #     # Recalculate
            #     ceiling_row = np.argmax(row_strength)
            #     ceiling_height = facade_height * (1 - ceiling_row / image_height)

            # print(f"    Facade {facade_nr} height: {facade_height} m; Estimated underpass height: {ceiling_height} m")

            # # # Visualize detected ceiling edge
            # img_vis = image.copy()

            # cv2.line(
            #     img_vis,
            #     (0, ceiling_row),                     
            #     (img_vis.shape[1], ceiling_row),      
            #     (0, 0, 255), 3                                     
            # )

            # image_height_path = os.path.join(PROJECT_ROOT, f'output/height_estimation/{img_id}', f'facade_{facade_nr}_estimated.jpg')
            # os.makedirs(os.path.dirname(image_height_path), exist_ok=True)
            # cv2.imwrite(image_height_path, img_vis)

            facade_nr += 1

        except:
            break
