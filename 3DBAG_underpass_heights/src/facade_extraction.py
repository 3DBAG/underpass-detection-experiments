import numpy as np
import cv2
import matplotlib.pyplot as plt

MAX_FACADE_WIDTH = 4096
MAX_FACADE_HEIGHT = 4096
MAX_IMAGE_SCALE = 4.0

def extract_facade(rect_2d, oblique_image):

    """
    Extract the facade image from the oblique image using the projected 2D rectangle of the critical wall.
    
    Args:
        - rect_2d: A 2D rectangle (as numpy array) corresponding to the projected wall on the image.
        - oblique_image: The input oblique image (CV2 image) from which the facade will be extracted.

    Returns:
        - facade_image: The extracted facade image (CV2 image).

    """

    # Reorder rectangle
    ordered = np.float32([rect_2d[2], rect_2d[3], rect_2d[0], rect_2d[1]])
    rect_2d = ordered

    # Compute output size of the facade image
    # Hows width and height computed! Might bring problems... top left, bottom left, bottom right, top right
    rect_2d = np.array(rect_2d, dtype=np.float32).reshape(-1, 2)
    if rect_2d.shape[0] != 4 or not np.isfinite(rect_2d).all():
        return None

    # Reject pathological projected rectangles that would cause huge allocations.
    span_x = float(np.max(rect_2d[:, 0]) - np.min(rect_2d[:, 0]))
    span_y = float(np.max(rect_2d[:, 1]) - np.min(rect_2d[:, 1]))
    image_h, image_w = oblique_image.shape[:2]
    if span_x > image_w * MAX_IMAGE_SCALE or span_y > image_h * MAX_IMAGE_SCALE:
        return None

    width = int(np.sqrt(((rect_2d[0][0] - rect_2d[3][0]) ** 2) + ((rect_2d[0][1] - rect_2d[3][1]) ** 2)))
    width2 = int(np.sqrt(((rect_2d[1][0] - rect_2d[2][0]) ** 2) + ((rect_2d[1][1] - rect_2d[2][1]) ** 2)))
    width = max(width, width2)

    height = int(np.sqrt(((rect_2d[0][0] - rect_2d[1][0]) ** 2) + ((rect_2d[0][1] - rect_2d[1][1]) ** 2)))
    height2 = int(np.sqrt(((rect_2d[2][0] - rect_2d[3][0]) ** 2) + ((rect_2d[2][1] - rect_2d[3][1]) ** 2)))
    height = max(height, height2)

    width = max(1, min(width, MAX_FACADE_WIDTH))
    height = max(1, min(height, MAX_FACADE_HEIGHT))

    output_rectangle = np.array([
                [0, 0],
                [0, height-1],
                [width-1, height-1],
                [width-1, 0]
            ], dtype="float32")

    # Perspective transform
    rect_2d = rect_2d.reshape(-1, 2)
    M = cv2.getPerspectiveTransform(rect_2d, output_rectangle)
    try:
        warped = cv2.warpPerspective(oblique_image, M, (width, height), flags=cv2.INTER_LINEAR)
    except cv2.error:
        return None

    return warped


def display_facade_image(facade_image):

    """
    Display the extracted facade image.
    Args:
        - facade_image: The extracted facade image (CV2 image) to be displayed.

    Returns:
        None
    
    """

    plt.imshow(facade_image)
    plt.title("Facade texture")
    plt.show()