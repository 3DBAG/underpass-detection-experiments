# Download an example CityJSON tile from 3DBAG
# Usage: just download-tile [tile_id]
# Example: just download-tile 9-444-728
download-tile tile_id="9-444-728":
    #!/usr/bin/env bash
    set -euo pipefail
    z=$(echo "{{tile_id}}" | cut -d- -f1)
    x=$(echo "{{tile_id}}" | cut -d- -f2)
    y=$(echo "{{tile_id}}" | cut -d- -f3)
    url="https://data.3dbag.nl/v20250903/tiles/${z}/${x}/${y}/{{tile_id}}.city.json"
    out="sample_data/{{tile_id}}.city.json"
    mkdir -p sample_data
    echo "Downloading ${url} -> ${out}"
    wget -O "${out}" "${url}"
