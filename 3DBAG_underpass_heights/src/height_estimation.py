import sys
import os
import torch
import cv2
import numpy as np
import matplotlib.pyplot as plt
from torchvision import transforms
from PIL import Image


# Function to load the Depth-Anything-V2 model
def load_depth_map_model(depth_model_directory):

    """
    Load the Depth-Anything-V2 model for depth estimation.
    This code uses commit e5a2732d3ea2cddc081d7bfd708fc0bf09f812f1 (January 22nd, 2025).
    Link to repository: https://github.com/DepthAnything/Depth-Anything-V2

    Args:
        depth_model_directory: The directory where the Depth-Anything-V2 model checkpoint and code are stored.
    
    Returns:
        Depth-Anything-V2 model.

    """
    # Append Depth-Anything-V2 directory and load modules
    if depth_model_directory not in sys.path:
        sys.path.append(depth_model_directory)

    from depth_anything_v2.dpt import DepthAnythingV2

    # Configure Depth-Anything-V2 model
    device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    model_configs = {
        'vits': {'encoder': 'vits', 'features': 64, 'out_channels': [48, 96, 192, 384]},
        'vitb': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
        'vitl': {'encoder': 'vitl', 'features': 256, 'out_channels': [256, 512, 1024, 1024]},
        'vitg': {'encoder': 'vitg', 'features': 384, 'out_channels': [1536, 1536, 1536, 1536]}
    }
    encoder = 'vitb' # or 'vits', 'vitb', 'vitg'
    checkpoint_path = os.path.join(depth_model_directory, "checkpoints/depth_anything_v2_vitb.pth")
    model = DepthAnythingV2(**model_configs[encoder])
    model.load_state_dict(torch.load(checkpoint_path, map_location="cpu", weights_only=True))
    model = model.to(device).eval()

    return model


# Function to load the U-Net model
def load_unet_model(unet_model_directory):

    """
    Load the U-Net model for underpass segmentation.

    Args:
        unet_model_directory: The directory where the U-Net model checkpoint is stored.

    Returns:
        device: The device on which the model is loaded (CPU or GPU).
        model: The loaded U-Net model.

    """
    if unet_model_directory not in sys.path:
        sys.path.append(unet_model_directory)

    from underpass_dataset import UnderpassDataset
    from unet import UNet

    model_path = os.path.join(unet_model_directory, "model.pth")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = UNet(in_channels=3, num_classes=1).to(device)
    model.load_state_dict(torch.load(model_path, map_location=torch.device(device)))

    return device, model


def apply_cc_method(facade_image, facade_height, min_height, ground_dist, top_dist, min_solidity):
    
    """
    Apply connected components method to estimate underpass height from facade image.
    Args:
    - facade_image: The input image of the building facade (CV2 image).
    - facade_height: The height of the building facade in meters.
    - min_height: Minimum height of underpass in meters (e.g., 2.2m), for component filtering.
    - ground_dist: Minimum distance from bottom of image to component in pixels, for component filtering.
    - top_dist: Minimum distance from top of image to component in pixels, for component filtering.
    - min_solidity: Minimum solidity of underpass component (e.g., 0.5).

    Returns:
    - pixel_row: The pixel row in the facade image corresponding to the estimated underpass height.
    - underpass_height: The estimated underpass height in meters.
    """

    facade_image_height, facade_image_width, _ = facade_image.shape
            
    # Apply Canny filter to image
    gray = cv2.cvtColor(facade_image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(gray, 30, 100)

    # Apply morphology to close edges and create more complete contours
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    # Detect connected components
    blur = cv2.GaussianBlur(edges, (3,3), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=4)
    # Create false color image with black background and colored objects
    colors = np.random.randint(0, 255, size=(n_labels, 3), dtype=np.uint8)
    colors[0] = [0, 0, 0]
    false_colors = colors[labels]
    # plt.imshow(false_colors)
    # plt.title("Connected components")
    # plt.show()
 
    filtered_mask = np.zeros_like(thresh)

    # Keep components higher than threshold
    min_height_px = int(facade_image_height * (min_height / facade_height))
    filtered_mask = np.zeros_like(labels, dtype=np.uint8)

    for i in range(1, n_labels):  
        comp_height = stats[i, cv2.CC_STAT_HEIGHT]
        comp_width = stats[i, cv2.CC_STAT_WIDTH]
        comp_top = stats[i, cv2.CC_STAT_TOP]
        comp_bottom = comp_top + comp_height
        comp_area = stats[i, cv2.CC_STAT_AREA]
        solidity = comp_area / (comp_height * comp_width)

        if (
            comp_top >= top_dist and
            comp_height >= min_height_px and
            comp_bottom >= facade_image_height - ground_dist and
            solidity >= min_solidity
                    ):
                    filtered_mask[labels == i] = 255

    # Pick most centered component out of the remaining
    img_cx = facade_image_width / 2

    remaining_labels = [
        i for i in range(1, n_labels)
        if np.any(filtered_mask[labels == i])]

    if remaining_labels:
        best_label = min(
            remaining_labels,
            key=lambda i: abs(centroids[i][0] - img_cx))
        # Keep only the best label
        final_mask = np.zeros_like(filtered_mask)
        final_mask[labels == best_label] = 255

    else:
        final_mask = filtered_mask.copy()
        
    # Now filtered_mask contains only large components
    false_colors_height_filtered = false_colors.copy()
    false_colors_height_filtered[final_mask == 0] = 0

    # plt.imshow(false_colors_height_filtered)
    # plt.title("Underpass candidate component")
    # plt.show()

    if len(remaining_labels) == 0:
        return None, None

    pixel_row = stats[best_label, cv2.CC_STAT_TOP]
    underpass_height = facade_height * (1 - pixel_row / facade_image_height)

    # Filter out unrealistic height estimates
    if underpass_height >= (facade_height - 0.2) or underpass_height < 2:
        return None, None   
    
    return pixel_row, underpass_height


def apply_depth_method(facade_image, facade_height, depth_map_model, k):

    """
    Apply depth estimation method to estimate underpass height from facade image.
    Args: 
    - facade_image: The input image of the building facade (CV2 image).
    - facade_height: The height of the building facade in meters.
    - depth_map_model: The loaded Depth-Anything-V2 model.
    - k: The number of clusters to use in k-means clustering of the depth map.

    Returns:
    - pixel_row: The pixel row in the facade image corresponding to the estimated underpass height.
    - underpass_height: The estimated underpass height in meters.
    
    """

    original_height, original_width, _ = facade_image.shape
    facade_image_height, facade_image_width = original_height, original_width

    limit= 1024
    scale = 1.0

    # Resize image if larger than limit to avoid memory issues with depth estimation model
    if original_height > limit or original_width > limit:
        scale = min(limit / facade_image_height, limit / facade_image_width)
        new_size = (int(facade_image_width * scale), int(facade_image_height * scale))
        facade_image = cv2.resize(facade_image, new_size)
        facade_image_height, facade_image_width = facade_image.shape[:2]

    # Perform depth estimation
    with torch.no_grad():
        depth_map = depth_map_model.infer_image(facade_image.copy())

    # plt.imshow(depth_map)
    # plt.title("Predicted Depth Map")
    # plt.show()

    # Apply depth clusters
    depth_map_height, depth_map_width = depth_map.shape

    # Downsample for clustering
    small_depth = cv2.resize(depth_map, (256, 256))
    depth_reshaped = small_depth.reshape(-1, 1).astype(np.float32)

    # Apply k-means clustering
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, centers = cv2.kmeans(
        depth_reshaped,
        k,
        None,
        criteria,
        10,
        cv2.KMEANS_RANDOM_CENTERS
    )

    # Reshape labels back to image
    segmented = labels.reshape(256, 256)

    # plt.imshow(segmented)
    # plt.title("Depth Clusters")
    # plt.show()

    # Deepest cluster = cluster with smallest center value
    deepest_cluster_idx = np.argmin(centers)
    deepest_mask = (segmented == deepest_cluster_idx).astype(np.uint8) * 255
    #Resize mask back to original image size
    deepest_mask = cv2.resize(deepest_mask, (facade_image_width, facade_image_height))

    # plt.imshow(deepest_mask, cmap='gray')
    # plt.title("Deepest Region")
    # plt.show()

    # Find connected components to select only ground component
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(deepest_mask)
    bottoms = stats[:, cv2.CC_STAT_TOP] + stats[:, cv2.CC_STAT_HEIGHT]
    deepest_component_idx = np.argmax(bottoms[1:]) + 1 
    ground_region_mask = (labels == deepest_component_idx).astype(np.uint8) * 255

    # plt.imshow(ground_region_mask, cmap='gray')
    # plt.title("Estimated underpass region")
    # plt.show()

    # Get coordinates of non-zero pixels
    ys, xs = np.nonzero(ground_region_mask)
    if len(ys) == 0:
        return None, None

    # Pixel row in original image coordinates
    pixel_row_resized = np.min(ys)
    pixel_row_original = int(pixel_row_resized / scale)

    underpass_height = facade_height * (1 - pixel_row_original / original_height)
    # Filter out unrealistic height estimates
    if underpass_height >= (facade_height - 0.2) or underpass_height < 2:
        return None, None
    
    return pixel_row_original, underpass_height


def apply_unet_method(facade_image, facade_height, unet_model, device):

    """
    Apply U-Net segmentation method to estimate underpass height from facade image.
    Args:   
    - facade_image: The input image of the building facade (CV2 image).
    - facade_height: The height of the building facade in meters.
    - unet_model: The loaded U-Net model.
    - device: The device on which the U-Net model is loaded (CPU or GPU).
    
    Returns:
    - pixel_row: The pixel row in the facade image corresponding to the estimated underpass height.
    - underpass_height: The estimated underpass height in meters.   
    
    """

    original_height, original_width, _ = facade_image.shape

    facade_image_rgb = cv2.cvtColor(facade_image, cv2.COLOR_BGR2RGB)
    facade_image_pil = Image.fromarray(facade_image_rgb)

    transform = transforms.Compose([
         transforms.Resize((224, 224)),
        transforms.ToTensor()
    ])

    input_tensor = transform(facade_image_pil).float().to(device)
    input_tensor = input_tensor.unsqueeze(0)

    pred_mask = unet_model(input_tensor)

    resized_height, resized_width = 224, 224

    pred_mask = pred_mask.squeeze(0).cpu().detach()
    pred_mask = pred_mask.permute(1, 2, 0)
    pred_mask[pred_mask < 0] = 0
    pred_mask[pred_mask > 0] = 1

    # Convert mask to uint8 image
    mask = (pred_mask.squeeze().numpy() * 255).astype(np.uint8)

    # plt.imshow(mask, cmap='gray')                 
    # plt.title("Predicted Mask")
    # plt.show()

    # Find lowest connected component in the mask
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    if num_labels <= 1:
        return None, None
    
    bottoms = stats[:, cv2.CC_STAT_TOP] + stats[:, cv2.CC_STAT_HEIGHT]
    target_component_idx = np.argmax(bottoms[1:]) + 1
    component_mask = (labels == target_component_idx).astype(np.uint8) * 255

    # plt.imshow(component_mask, cmap='gray')                 
    # plt.title("Selected Component Mask")
    # plt.show()

    ys, xs = np.nonzero(component_mask)
    top_y = np.min(ys)
    pixel_row = top_y

    pixel_row_original = int(round(pixel_row * (original_height / resized_height)))
    pixel_row_original = max(0, min(pixel_row_original, original_height - 1))

    underpass_height = facade_height * (1 - pixel_row_original / original_height)

    if underpass_height >= (facade_height - 0.2) or underpass_height < 2:
        return None, None

    return pixel_row_original, underpass_height


def display_image(facade_image, pixel_row):

    """Display the facade image with a line indicating the estimated underpass height.
    Args:
    - facade_image: The input image of the building facade (CV2 image).
    - pixel_row: The pixel row in the facade image corresponding to the estimated underpass height.
    """
     
    img_vis = facade_image.copy()
    cv2.line(
        img_vis,
        (0, pixel_row),                     
        (img_vis.shape[1], pixel_row),      
        (0, 0, 255), 3)
    
    plt.imshow(img_vis)
    plt.title("Estimated underpass height")
    plt.show()


def record_observation(gdf_underpass_polygons, gdf_critical_walls, wall_id, underpass_height):

    """
    Record the estimated underpass height in the GeoDataFrame of underpass polygons.
    Args:
    - gdf_underpass_polygons: GeoDataFrame containing underpass polygons.
    - gdf_critical_walls: GeoDataFrame containing critical walls with their corresponding underpass IDs.
    - wall_id: The ID of the critical wall for which the underpass height was estimated.
    - underpass_height: The estimated underpass height in meters to be recorded.
    
    """
     
    underpass_id = gdf_critical_walls[gdf_critical_walls['wall_id'] == wall_id]['underpass_id'].iloc[0] 
    idx = gdf_underpass_polygons[gdf_underpass_polygons['underpass_id'] == underpass_id].index[0]
    gdf_underpass_polygons.at[idx, 'observed_heights'].append(underpass_height)


def trimmed_mean(values, trim_ratio=0.15):
    values = sorted(values)
    n = len(values)
    k = int(n * trim_ratio)
    trimmed = values[k:n-k] if n > 2*k else values
    return sum(trimmed) / len(trimmed)


def write_geojson(gdf_underpass_polygons, output_path):

    """
    Write the GeoDataFrame of underpass polygons with recorded heights to a GeoJSON file.
    Args:
    - gdf_underpass_polygons: GeoDataFrame containing underpass polygons with recorded heights.
    - output_path: The file path or directory where the GeoJSON file should be saved.
    
    This function allows passing either a full .geojson file path or a directory. If a directory is provided, the GeoJSON file will be saved with a default name in that directory.
    """
    
    # Allow passing either a directory or a full .geojson path.
    if output_path.lower().endswith('.geojson'):
        output_file = output_path
    else:
        os.makedirs(output_path, exist_ok=True)
        output_file = os.path.join(output_path, 'underpasses_estimated_heights.geojson')

    gdf_underpass_polygons.to_file(output_file, driver='GeoJSON')