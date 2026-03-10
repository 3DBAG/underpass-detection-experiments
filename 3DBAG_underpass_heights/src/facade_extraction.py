import numpy as np
import cv2
import matplotlib.pyplot as plt

def extract_facade(rect_2d, oblique_image):

    # Reorder rectangle
    ordered = np.float32([rect_2d[2], rect_2d[3], rect_2d[0], rect_2d[1]])
    rect_2d = ordered

    # Compute output size of the facade image
    # Hows width and height computed! Might bring problems... top left, bottom left, bottom right, top right
    rect_2d = np.array(rect_2d, dtype=np.float32).reshape(-1, 2)
    width = int(np.sqrt(((rect_2d[0][0] - rect_2d[3][0]) ** 2) + ((rect_2d[0][1] - rect_2d[3][1]) ** 2)))
    width2 = int(np.sqrt(((rect_2d[1][0] - rect_2d[2][0]) ** 2) + ((rect_2d[1][1] - rect_2d[2][1]) ** 2)))
    width = max(width, width2)

    height = int(np.sqrt(((rect_2d[0][0] - rect_2d[1][0]) ** 2) + ((rect_2d[0][1] - rect_2d[1][1]) ** 2)))
    height2 = int(np.sqrt(((rect_2d[2][0] - rect_2d[3][0]) ** 2) + ((rect_2d[2][1] - rect_2d[3][1]) ** 2)))
    height = max(height, height2)

    output_rectangle = np.array([
                [0, 0],
                [0, height-1],
                [width-1, height-1],
                [width-1, 0]
            ], dtype="float32")

    # Perspective transform
    rect_2d = rect_2d.reshape(-1, 2)
    M = cv2.getPerspectiveTransform(rect_2d, output_rectangle)
    warped = cv2.warpPerspective(oblique_image, M, (width, height), flags=cv2.INTER_LINEAR)

    return warped


def display_facade_image(facade_image):

    plt.imshow(facade_image)
    plt.title("Facade texture")
    plt.show()