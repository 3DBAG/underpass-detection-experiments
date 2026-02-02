import re
import numpy as np


def compute_r_matrix(omega, phi, kappa):

    # Rotation matrix around X-axis (omega)
    r_omega = np.array([[1, 0, 0],
                        [0, np.cos(omega), np.sin(omega)],
                        [0, -np.sin(omega), np.cos(omega)]])
    
    # Rotation matrix around Y-axis (phi)
    r_phi = np.array([[np.cos(phi), 0, -np.sin(phi)],
                      [0, 1, 0],
                      [np.sin(phi), 0, np.cos(phi)]])
    
    # Rotation matrix around Z-axis (kappa)
    r_kappa = np.array([[np.cos(kappa), np.sin(kappa), 0],
                        [-np.sin(kappa), np.cos(kappa), 0],
                        [0, 0, 1]])
    
    # Combined rotation matrix
    r = r_kappa @ r_phi @ r_omega

    return r



def get_extrinsic_params(extrinsic_params, img_id):

    # Open extrinsic parameters files
    with open(extrinsic_params, 'r') as f:
        lines = f.readlines()
        for line in lines:
            params = line.split()

            if params[0] != img_id:
                continue
            
            # Camera center
            c = np.array([float(params[1]), float(params[2]), float(params[3])]).reshape(3, 1)
            # Convert angles from degrees to radians
            omega = np.deg2rad(float(params[4]))
            phi = np.deg2rad(float(params[5]))
            kappa = np.deg2rad(float(params[6]))
            # Compute rotation matrix
            r = compute_r_matrix(omega, phi, kappa)

            return c, r



def get_intrinsic_params(intrinsic_params, img_id):

    # Open intrinsic parameters files
    with open(intrinsic_params, 'r') as f:
        lines = f.readlines()
        for line in lines:
            params = line.split()
            
            if len(params) == 0 or params[0] != img_id:
                continue
            
            # Principal point
            line_cx = lines.index(line) + 1
            cx = lines[line_cx].split()[2]
            line_cy = lines.index(line) + 2
            cy = lines[line_cy].split()[2]
            c = np.array([float(cx), float(cy)]).reshape(2, 1)

            # Focal length
            line_fx = lines.index(line) + 1
            fx = lines[line_fx].split()[0]
            line_fy = lines.index(line) + 2
            fy = lines[line_fy].split()[1]
            f = np.array([float(fx), float(fy)]).reshape(2, 1)

            return c, f
        

def get_camera_coordinates(points, c, r):

    #Initialize list for camera coordinates
    pc = []
    for point in points:
        point_c = r @ (np.array(point).reshape(3,1) - c) 
        pc.append(point_c.flatten().tolist())
    
    return pc


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


def project_3d_2d(rect_3d, c, f):
    
    rect_2d = []

    for point in rect_3d:
        x = point[0]
        y = point[1]
        z = point[2]

        u = f[0][0] * (x / z) + c[0][0]
        v = f[1][0] * (y / z) + c[1][0]
        
        rect_2d.append([u, v])
        print(f"3D point: ({x}, {y}, {z}) -> 2D point: ({u}, {v})")

    return rect_2d