import numpy as np
import cv2
import matplotlib.pyplot as plt


def project_walls_on_image(image, image_id, img_prefix, wall_ids, df_camera_parameters, gdf_critical_walls):

    image_width = df_camera_parameters[df_camera_parameters['img_id'] == image_id]['width'].iloc[0]
    image_height = df_camera_parameters[df_camera_parameters['img_id'] == image_id]['height'].iloc[0]

    # Compute camera matrix
    fx = float(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['fx'].iloc[0])
    fy = float(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['fy'].iloc[0])
    cx = float(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['cx'].iloc[0])
    cy = float(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['cy'].iloc[0])
    k = np.array([[fx, 0, cx],
                    [0, fy, cy],
                    [0, 0, 1]]).astype(np.float32)
        
    # Compute r matrix
    omega = np.deg2rad(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['omega'].iloc[0])
    phi = np.deg2rad(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['phi'].iloc[0])
    kappa = np.deg2rad(df_camera_parameters[df_camera_parameters['img_id'] == image_id]['kappa'].iloc[0])
    r_omega = np.array([
            [1, 0, 0],
            [0, np.cos(omega), -np.sin(omega)],
            [0, np.sin(omega),  np.cos(omega)]
        ])
    r_phi = np.array([
            [ np.cos(phi), 0, np.sin(phi)],
            [0, 1, 0],
            [-np.sin(phi), 0, np.cos(phi)]
        ])
    r_kappa = np.array([
        [np.cos(kappa), -np.sin(kappa), 0],
        [np.sin(kappa),  np.cos(kappa), 0],
        [0, 0, 1]
        ])
    # Showed to solve problems with orientation when calculating image footprints
    r = r_omega @ r_phi @ r_kappa
    R = r.T
    # Adjusting reflection across plane YZ "The world coordinate system X-axis is opposite to the camera coordinate X-axis definition used in the projection model."
    R = np.diag([-1, 1, 1]) @ R

    # Compute translation vector
    x = df_camera_parameters[df_camera_parameters['img_id'] == image_id]['X'].iloc[0]
    y = df_camera_parameters[df_camera_parameters['img_id'] == image_id]['Y'].iloc[0]
    z = df_camera_parameters[df_camera_parameters['img_id'] == image_id]['Z'].iloc[0]
    t = -R @ np.array([[x], [y], [z]]).astype(np.float32).reshape(3, 1)

    # Compute projection matrix
    m = k @ np.hstack((R, t.reshape(3, 1)))

    rectangles_2d = []
    for wall_id in wall_ids:
        # Extract wall 3d coordinates
        wall_geom = gdf_critical_walls[gdf_critical_walls['wall_id'] == wall_id]['geometry'].iloc[0]
        rect_3d = list(wall_geom.exterior.coords[:-1])

        rect_2d = []
        for vertex in rect_3d:
        # Express rectangle vertex in homogeneous coordinates
            vertex_3d_homogeneous = np.hstack((vertex, np.array([1])))
            # Compute projected point 
            vertex_2d_homogeneous = m @ vertex_3d_homogeneous.reshape(4, 1)
            # Convert projected point back to Cartesian coordinates
            vertex_2d = vertex_2d_homogeneous[:2] / vertex_2d_homogeneous[2]
            # Construct projected rectangle. Camera 402, 403 need width height adjustment
            if img_prefix == '402' or img_prefix == '403':
                rect_2d.append([int(round(image_width - vertex_2d[0][0] - 1)), int(round(image_height - vertex_2d[1][0]))])
            else:
                rect_2d.append([int(vertex_2d[0][0]), int(vertex_2d[1][0])])

            # for i in range(len(rect_2d)):
            #     print("original 3D Point: ({}, {}, {}), ->> ({}, {})".format(rect_3d[i][0], rect_3d[i][1], rect_3d[i][2], 
            #                                                          rect_2d[i][0], rect_2d[i][1]))
                
        # Draw projected wall
        rect_2d = np.array(rect_2d, dtype=np.int32)
        rect_2d = rect_2d.reshape((-1, 1, 2))
        rectangles_2d.append(rect_2d)

    return rectangles_2d


def display_image(rectangles_2d, image):

    limit_width = 1920
    limit_height = 1080

    image_h, image_w = image.shape[:2]
    
    for rect_2d in rectangles_2d:
        cv2.polylines(image, [rect_2d], True, (0, 0, 255), 10)

    if image_h > limit_height or image_w > limit_width:
        display_image = cv2.resize(image, (0, 0), fx=0.1, fy=0.1)

    else:
        display_image = image

    cv2.imshow("Projected facades", display_image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
