

# This script uses the overturemaps Python CLI to download Netherlands roads data
# Install overturemaps CLI: pip install overturemaps

# Netherlands bounding box: min_lon, min_lat, max_lon, max_lat
NETHERLANDS_BBOX = [3.2, 50.7, 7.3, 53.6]

import subprocess
import sys
import os
import overturemaps

def main():
	"""
	Downloads Netherlands roads data from Overture Maps and saves it as a GeoJSON file."""

	bbox_str = ','.join(str(x) for x in NETHERLANDS_BBOX)
	output_path = os.path.join(os.path.dirname(__file__), "roads_netherlands.geojson")
	print("Downloading Netherlands roads data from Overture Maps...")
	subprocess.check_call([
		os.path.join(sys.prefix, "bin", "overturemaps"), "download",
		"--bbox=" + bbox_str,
		"-f", "geojson",
		"-t", "segment",
		"-o", output_path
	])
	print(f"Netherlands roads saved to {output_path}")

if __name__ == "__main__":
	main()
