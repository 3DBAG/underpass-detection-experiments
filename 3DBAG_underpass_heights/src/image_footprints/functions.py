import re
import numpy as np
import os

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# def compute_r_matrix(omega, phi, kappa):

#     # Rotation matrix around X-axis (omega)
#     r_omega = np.array([[1, 0, 0],
#                         [0, np.cos(omega), np.sin(omega)],
#                         [0, -np.sin(omega), np.cos(omega)]])
    
#     # Rotation matrix around Y-axis (phi)
#     r_phi = np.array([[np.cos(phi), 0, -np.sin(phi)],
#                       [0, 1, 0],
#                       [np.sin(phi), 0, np.cos(phi)]])
    
#     # Rotation matrix around Z-axis (kappa)
#     r_kappa = np.array([[np.cos(kappa), -np.sin(kappa), 0],
#                         [-np.sin(kappa), np.cos(kappa), 0],
#                         [0, 0, 1]])
    
#     # Combined rotation matrix
#     r = r_kappa @ r_phi @ r_omega
    
#     return r

def compute_r_matrix(omega, phi, kappa):

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

    r = r_kappa @ r_phi @ r_omega
    return r


def read_mesh_vertex(path):

    vertices = []

    with open(path) as file:
        for line in file.readlines()[2:]:
            clean_parts = line.strip()
            parts = re.split(r'[,\s]+', clean_parts)
            if(len(parts)) == 3:
                vertices.append([float(parts[0]), float(parts[1]), float(parts[2])])
    return vertices


def read_mesh_faces(path):

    faces = []
    colors = []
    with open(path) as file:
        for line in file.readlines():
            clean_parts = line.strip()
            parts = re.split(r'[,\s]+', clean_parts)
            if (len(parts)) == 7:
                face = [int(parts[1]), int(parts[2]), int(parts[3])]
                color = [int(parts[4]), int(parts[5]), int(parts[6])]
                faces.append(face)
                colors.append(color)

    return faces,colors


def vertical_test(face, vertices):

    v1 = np.array(vertices[face[0]])
    v2 = np.array(vertices[face[1]])  # Coordinates of second vertex
    v3 = np.array(vertices[face[2]])  # Coordinates of third vertex

    # Calculate two vectors lying on the plane of the triangle
    u = v2 - v1
    v = v3 - v1

    # Calculate the normal vector by taking the cross product of the two vectors
    normal = np.cross(u, v)

    # Normalize the normal vector to have unit length
    normal = normal / np.linalg.norm(normal)

    # if normal[2] <= np.sin(10 * np.pi / 180. ) or normal[2] >= np.sin(-10 * np.pi / 180. ):
    perpendicular = np.array([0,0,1])
    if normal[2] == 0.:
        return True
    else:
        return False


def wallsurface_filter_bynormal(faces, colors, vertices):

    wallsurface = []
    new_color_list = []

    for i in range(len(faces)):
        if vertical_test(faces[i], vertices):
            wallsurface.append(faces[i])
            new_color_list.append(colors[i])

    return wallsurface, new_color_list


def merge_surface(faces, colors, vertices):

    group_faces = []
    new_colors = np.unique(np.array(colors), axis=0)
    for color in new_colors:
        group_faces.append([])

    for i in range(len(new_colors)):
        if new_colors[i][0] == 0 and new_colors[i][1] ==0 and new_colors[i][2] == 0:
            continue
        else:
            for j in range(len(colors)):
                if new_colors[i][0] == colors[j][0] and new_colors[i][1] == colors[j][1] and new_colors[i][2] == colors[j][2]:
                    group_faces[i].append(faces[j])

    return group_faces, new_colors


def triangle_area(face, vertices):

    pt1 = np.array(vertices[face[0]])
    pt2 = np.array(vertices[face[1]])  # Coordinates of second vertex
    pt3 = np.array(vertices[face[2]])  # Coordinates of third vertex

    # calculate the vector from P1 to P2
    V1 = pt2 - pt1

    V2 = pt3 - pt1
    cross_product = np.cross(V1, V2)

    area = 0.5 * np.linalg.norm(cross_product)

    # print("The area of the triangle is:", area)
    return area


def create_3d_footprint(each, vertices):
    max_pt = [0.0, 0.0, -100.0]
    min_pt = [9999999.0, 9999999.0, 999999.0]

    for facade in each:
        for i in facade:

            if vertices[i][0] > max_pt[0]: max_pt[0] = vertices[i][0]
            if vertices[i][0] < min_pt[0]: min_pt[0] = vertices[i][0]
            if vertices[i][1] > max_pt[1]: max_pt[1] = vertices[i][1]
            if vertices[i][1] < min_pt[1]: min_pt[1] = vertices[i][1]
            if vertices[i][2] > max_pt[2]: max_pt[2] = vertices[i][2]
            if vertices[i][2] < min_pt[2]: min_pt[2] = vertices[i][2]

    if_bbox_correct = False

    for facade in each:
        for i in facade:
            if vertices[i][0] == max_pt[0] and vertices[i][1] == max_pt[1] and vertices[i][2] == max_pt[2]:
                if_bbox_correct = True
            if vertices[i][0] == min_pt[0] and vertices[i][1] == min_pt[1] and vertices[i][2] == min_pt[2]:
                if_bbox_correct = True

    if not if_bbox_correct:
        temp = max_pt[1]
        max_pt[1] = min_pt[1]
        min_pt[1] = temp

    return [max_pt, [max_pt[0], max_pt[1], min_pt[2]], min_pt, [min_pt[0], min_pt[1], max_pt[2]]]


def get_off_3Dfootprint(grouped_faces, vertices):
    count = 0
    total_3Dfootprint = []
    else_polygon = []
    for each in grouped_faces:

        area_sum = 0.

        for tri in each:
            area = triangle_area(tri, vertices)
            area_sum += area

        if area_sum > 5:
            each_3Dfootprint = create_3d_footprint(each, vertices)
            total_3Dfootprint.append(each_3Dfootprint)
        else:
            for tri in each:
                else_polygon.append(tri)
        count += 1

    return total_3Dfootprint, else_polygon


def compute_projection_matrix(img_id, params_path):

    # Get camera parameters
    img = False
    with open(params_path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            params = line.split()

            if params[0] != img_id:
                continue

            img = True
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

    # Compute projection matrix
    m = k @ np.hstack((r, t.reshape(3, 1)))

    return m


def project_3d_2d(rect_3d, img_id, params_path):
    
    # Compute projection matrix
    m = compute_projection_matrix(img_id, params_path)

    rect_2d = []
    for vertex in rect_3d:
        # Express rectangle vertex in homogeneous coordinates
        vertex_3d_homogeneous = np.hstack((vertex, np.array([1])))
        # Compute projected point 
        vertex_2d_homogeneous = m @ vertex_3d_homogeneous.reshape(4, 1)
        # Convert projected point back to Cartesian coordinates
        vertex_2d = vertex_2d_homogeneous[:2] / vertex_2d_homogeneous[2]
        # Construct projected rectangle
        rect_2d.append([int(14192 - vertex_2d[0][0]), int(10640 - vertex_2d[1][0])])

    for i in range(len(rect_2d)):
        print("original 3D Point: ({}, {}, {}), ->> ({}, {})".format(rect_3d[i][0], rect_3d[i][1], rect_3d[i][2], 
                                                                     rect_2d[i][0], rect_2d[i][1]))

    return rect_2d


def compute_image_footprint(K, R, t, width, height, Z_ground=0):
    # Camera center in world coordinates
    C = (-R.T @ t).reshape(3)

    corners_px = np.array([
        [0, 0],
        [width-1, 0],
        [width-1, height-1],
        [0, height-1]
    ])

    fx, fy = K[0,0], K[1,1]
    cx, cy = K[0,2], K[1,2]

    footprint = []
    for u,v in corners_px:
        # normalized camera coordinates
        x = (u - cx) / fx
        y = (v - cy) / fy
        ray_c = np.array([x, y, 1.0])

        # ray in world coordinates
        ray_w = (R.T @ ray_c).flatten()

        # scale to intersect plane Z=Z_ground
        lam = (Z_ground - C[2]) / ray_w[2]
        P = C + lam * ray_w
        footprint.append(P)

    return np.array(footprint)  # 4x3 array


# def get_camera_parameters(img_id):
#     """
#     :param img_id: image id
#     :return: return original R and t
#     """
#     cp_file = os.path.join(PROJECT_ROOT, 'data\perspective_projection', 'calibrated_camera_parameters.txt')

#     print(cp_file)
#     if_img = False
#     parameters_count = 0
#     camera_parameters = []
#     with open(cp_file) as lines:
#         for line in lines:
#             parts = line.strip().split(" ")
#             if parts[0] == img_id:
#                 if_img = True
#                 continue
#             elif if_img == True and parameters_count != 9:
#                 camera_parameters.append(parts)
#                 parameters_count+=1
#             elif parameters_count == 9:
#                 break

#     K = np.array([camera_parameters[0], camera_parameters[1], camera_parameters[2]]).astype(np.float32)
#     t = np.array([camera_parameters[5]]).astype(np.float32)
#     R = np.array([camera_parameters[6], camera_parameters[7], camera_parameters[8]]).astype(np.float32)

#     t = t.reshape(3, 1)
#     t1 = -1. * R @ t
#     Rt = np.hstack((R, t1.reshape(3, 1)))
#     KRt = K @ Rt

#     return KRt


# def get_offset(img_id):
#     """
#     offset of 3D coordinates
#     :return: offset in x,y,z dimension
#     """
#     offset_file = os.path.join(PROJECT_ROOT, 'data/perspective_projection', 'offset.xyz')

#     img_type = img_id.strip().split("_")[0]

#     with open(offset_file) as file:
#         for line in file:
#             parts = line.strip().split(" ")

#             if parts[0] == img_type:
#                 offset_x = parts[1]
#                 offset_y = parts[2]
#                 offset_z = parts[3]

#                 return float(offset_x), float(offset_y), float(offset_z)
            

# def projection(img_id, P):

#     M = get_camera_parameters(img_id)

#     offset_x, offset_y, offset_z = get_offset(img_id)

#     Ps = []
#     for line in P:
#         P_new = [0, 0, 0]
#         P_new[0] = line[0] - offset_x
#         P_new[1] = line[1] - offset_y
#         P_new[2] = line[2] - offset_z
#         # reshape 3D point coordinates
#         P_new = np.hstack((P_new, np.array([1])))
#         Ps.append(P_new)

#     # Ps = np.hstack((P,np.array([1,1,1,1]).reshape(4,1)))

#     point = []
#     for pt in Ps:
#         P_proj = M @ pt.reshape(4, 1)
#         x = P_proj[:2] / P_proj[2]
#         point.append([int(x[0][0]), int(x[1][0])])
        
#     # Print result

#     for i in range(len(P)):
#         print("original 3D Point: ({}, {}, {}), ->> ({}, {})".format(P[i][0], P[i][1], P[i][2], point[i][0],
#                                                                      point[i][1]))
#     return point