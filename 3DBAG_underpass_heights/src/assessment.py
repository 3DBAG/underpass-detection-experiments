import geopandas as gpd
import os
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
import numpy as np

# Configure root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

output_directory = os.path.join(PROJECT_ROOT, 'output')
ground_truth_directory = os.path.join(PROJECT_ROOT, 'data', 'ground_truth')

def deduplicate_comparison(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
	"""Keep one row per underpass/surface pair after one-to-many spatial joins."""
	return gdf.drop_duplicates(subset=['underpass_id', 'surface_id']).copy()

# Load ground truth data
gdf_ground_truth = gpd.read_file(os.path.join(ground_truth_directory, 'underpasses_rotterdam3d_revised.geojson'))

# Load image footprints 
gdf_image_footprints = gpd.read_file(os.path.join(PROJECT_ROOT, 'data', 'oblique_images', 'image_footprints.geojson'))

# Load result from methods
gdf_cc_results = gpd.read_file(os.path.join(output_directory, 'underpass_heights_ccmethod.geojson'))
gdf_depth_results = gpd.read_file(os.path.join(output_directory, 'underpass_heights_depthmethod.geojson'))
gdf_unet_results = gpd.read_file(os.path.join(output_directory, 'underpass_heights_unetmethod.geojson'))

# Join spatially both datasets to compare results
gdf_comparison_cc = gpd.sjoin(gdf_cc_results, gdf_ground_truth, how='inner', predicate='intersects')
gdf_comparison_depth = gpd.sjoin(gdf_depth_results, gdf_ground_truth, how='inner', predicate='intersects')
gdf_comparison_unet = gpd.sjoin(gdf_unet_results, gdf_ground_truth, how='inner', predicate='intersects')

# Select important columns
gdf_comparison_cc = gdf_comparison_cc[['underpass_id', 'surface_id', 'estimated_height', 'upass_h', 'geometry']].rename(columns={'upass_h': 'real_height'})
gdf_comparison_depth = gdf_comparison_depth[['underpass_id', 'surface_id', 'estimated_height', 'upass_h', 'geometry']].rename(columns={'upass_h': 'real_height'})
gdf_comparison_unet = gdf_comparison_unet[['underpass_id', 'surface_id', 'estimated_height', 'upass_h', 'geometry']].rename(columns={'upass_h': 'real_height'})

#Select only features which are actually visible in the oblique images (i.e. intersect with image footprints)
gdf_comparison_cc = gpd.sjoin(gdf_comparison_cc, gdf_image_footprints, how='inner', predicate='within')
gdf_comparison_depth = gpd.sjoin(gdf_comparison_depth, gdf_image_footprints, how='inner', predicate='within')
gdf_comparison_unet = gpd.sjoin(gdf_comparison_unet, gdf_image_footprints, how='inner', predicate='within')

# Drop duplicates after spatial join with image footprints
gdf_comparison_cc = deduplicate_comparison(gdf_comparison_cc)
gdf_comparison_depth = deduplicate_comparison(gdf_comparison_depth)
gdf_comparison_unet = deduplicate_comparison(gdf_comparison_unet)

# Select important columns
gdf_comparison_cc = gdf_comparison_cc[['underpass_id', 'surface_id', 'estimated_height', 'real_height', 'geometry']]
gdf_comparison_depth = gdf_comparison_depth[['underpass_id', 'surface_id', 'estimated_height', 'real_height', 'geometry']]
gdf_comparison_unet = gdf_comparison_unet[['underpass_id', 'surface_id', 'estimated_height', 'real_height', 'geometry']]

# Calculate absolute error
gdf_comparison_cc['error'] = (gdf_comparison_cc['estimated_height'] - gdf_comparison_cc['real_height']).abs()
gdf_comparison_depth['error'] = (gdf_comparison_depth['estimated_height'] - gdf_comparison_depth['real_height']).abs()
gdf_comparison_unet['error'] = (gdf_comparison_unet['estimated_height'] - gdf_comparison_unet['real_height']).abs()

# Calculate relative error
gdf_comparison_cc['relative_error'] = (gdf_comparison_cc['error'] / gdf_comparison_cc['real_height']).abs() * 100
gdf_comparison_depth['relative_error'] = (gdf_comparison_depth['error'] / gdf_comparison_depth['real_height']).abs() * 100
gdf_comparison_unet['relative_error'] = (gdf_comparison_unet['error'] / gdf_comparison_unet['real_height']).abs() * 100

# Write file back to output directory
gdf_comparison_cc.to_file(os.path.join(output_directory, 'assessment_ccmethod.geojson'), driver='GeoJSON')
print("Assessment of CC method: \n", gdf_comparison_cc.head())
gdf_comparison_depth.to_file(os.path.join(output_directory, 'assessment_depthmethod.geojson'), driver='GeoJSON')
print("Assessment of depth method: \n",gdf_comparison_depth.head())
gdf_comparison_unet.to_file(os.path.join(output_directory, 'assessment_unetmethod.geojson'), driver='GeoJSON')
print("Assessment of unet method: \n",gdf_comparison_unet.head())

print("\n")

# Calculate total number of features 
total_unet = len(gdf_comparison_unet)
print(f"Total number of features: {total_unet}")

print("\n")

# Calculate number of features where estimated height is null across all methods
null_cc = set(gdf_comparison_cc.loc[gdf_comparison_cc['estimated_height'].isnull(), 'underpass_id'])
null_depth = set(gdf_comparison_depth.loc[gdf_comparison_depth['estimated_height'].isnull(), 'underpass_id'])
null_unet = set(gdf_comparison_unet.loc[gdf_comparison_unet['estimated_height'].isnull(), 'underpass_id'])
null_all = null_cc & null_depth & null_unet
null_all_count = len(null_all)

print(f"Number of features where estimated_height is null across all methods: {null_all_count}")

print("\n")


# Calculate number of features where estimated_height is null
null_cc = gdf_comparison_cc['estimated_height'].isnull().sum()
null_depth = gdf_comparison_depth['estimated_height'].isnull().sum()
null_unet = gdf_comparison_unet['estimated_height'].isnull().sum()
print(f"Number of features where estimated_height is null for CC method: {null_cc - null_all_count}")
print(f"Number of features where estimated_height is null for Depth method: {null_depth - null_all_count}")
print(f"Number of features where estimated_height is null for UNet method: {null_unet - null_all_count}")

print("\n")

# Calculate overall MAE for each method
mae_cc = gdf_comparison_cc['error'].mean()
mae_depth = gdf_comparison_depth['error'].mean()
mae_unet = gdf_comparison_unet['error'].mean()
print(f"Mean Absolute Error (MAE) for CC method: {mae_cc:.2f} meters")
print(f"Mean Absolute Error (MAE) for Depth method: {mae_depth:.2f} meters")
print(f"Mean Absolute Error (MAE) for UNet method: {mae_unet:.2f} meters")

print("\n")

#Calculate RMSE for each method
rmse_cc = (gdf_comparison_cc['error'] ** 2).mean() ** 0.5
rmse_depth = (gdf_comparison_depth['error'] ** 2).mean() ** 0.5
rmse_unet = (gdf_comparison_unet['error'] ** 2).mean() ** 0.5
print(f"Root Mean Squared Error (RMSE) for CC method: {rmse_cc:.2f} meters")
print(f"Root Mean Squared Error (RMSE) for Depth method: {rmse_depth:.2f} meters")
print(f"Root Mean Squared Error (RMSE) for UNet method: {rmse_unet:.2f} meters")

print("\n")

# Calculate mean relative error for each method
relative_error_cc = (abs(gdf_comparison_cc['error']) / gdf_comparison_cc['real_height']).mean() * 100
relative_error_depth = (abs(gdf_comparison_depth['error']) / gdf_comparison_depth['real_height']).mean() * 100
relative_error_unet = (abs(gdf_comparison_unet['error']) / gdf_comparison_unet['real_height']).mean() * 100
print(f"Relative Error (RE) for CC method: {relative_error_cc:.2f}%")
print(f"Relative Error (RE) for Depth method: {relative_error_depth:.2f}%")
print(f"Relative Error (RE) for UNet method: {relative_error_unet:.2f}%")

# Print histograms
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde

def plot_histogram_with_kde_ax(ax, data, title, bins, show_ylabel=False):
    # Clean data
    data_clean = data[np.isfinite(data)]
    if len(data_clean) == 0:
        ax.set_title(f"{title}\n(No data)")
        return

    # Histogram
    counts, bin_edges, _ = ax.hist(
        data_clean,
        bins=bins,
        edgecolor='black',
        alpha=0.6
    )

    # KDE
    kde = gaussian_kde(data_clean)
    x_vals = np.linspace(min(data_clean), max(data_clean), 1000)
    bin_width = bin_edges[1] - bin_edges[0]
    ax.plot(
        x_vals,
        kde(x_vals) * len(data_clean) * bin_width,
        color='orange',
        label="KDE (density estimate)"
    )

    # Mean line
    mean_val = np.mean(data_clean)
    ax.axvline(
        mean_val,
        linestyle='--',
        color='red',
        label=rf"Mean ($\bar{{x}}$ = {mean_val:.2f} m)"
    )

    # Titles and labels
    ax.set_title(title)
    ax.set_xlabel("Absolute error (m)")

    if show_ylabel:
        ax.set_ylabel("Feature Count")

    # Axis formatting
    ax.set_yticks(np.arange(0, 18, 2))
    ax.set_xticks(np.arange(0, 12, 1))
    ax.set_ylim(0, 15)
    ax.set_xlim(0, 11)

    ax.set_axisbelow(True)
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.4)

    ax.legend()


# Bins
# bins = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12]
bins = [0, 0.2, 0.4, 0.6, 0.8, 1, 1.2, 1.4, 1.6, 1.8, 2, 2.2, 2.4, 2.6, 2.8, 3, 3.2, 3.4, 3.6, 3.8, 4, 4.2, 4.4, 4.6, 4.8, 5
        , 5.2, 5.4, 5.6, 5.8, 6, 6.2, 6.4, 6.6, 6.8, 7, 7.2, 7.4, 7.6, 7.8, 8, 8.2, 8.4, 8.6, 8.8, 9, 9.2, 9.4, 9.6, 9.8, 10, 10.2, 10.4, 10.6, 10.8, 11]

# Create subplots
fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)

# Plot each method
plot_histogram_with_kde_ax(axes[0], gdf_comparison_cc['error'], "CC method", bins, show_ylabel=True)
plot_histogram_with_kde_ax(axes[1], gdf_comparison_depth['error'], "Depth method", bins)
plot_histogram_with_kde_ax(axes[2], gdf_comparison_unet['error'], "UNet method", bins)

# Suptitle
fig.suptitle("Absolute error histograms", fontsize=16)

# Layout adjustment
plt.tight_layout()
plt.show()