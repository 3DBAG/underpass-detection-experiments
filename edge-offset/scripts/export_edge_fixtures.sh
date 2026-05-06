#!/usr/bin/env bash

EDGE_OFFSET_EDGES_TABLE="${EDGE_OFFSET_EDGES_TABLE:-underpasses.edges}"

for ident in \
  'NL.IMBAG.Pand.0363100012182123' \
  'NL.IMBAG.Pand.0637100000164662' \
  'NL.IMBAG.Pand.0637100000303797' \
  'NL.IMBAG.Pand.0637100000157787' \
  'NL.IMBAG.Pand.0363100012165684' \
  'NL.IMBAG.Pand.0363100012111986' \
  'NL.IMBAG.Pand.0606100000012670' \
  'NL.IMBAG.Pand.0363100012084610' \
  'NL.IMBAG.Pand.0437100000007755'
do
  docker run --rm -v "$PWD:/tmp" --network=host --env-file .env \
  ghcr.io/osgeo/gdal:alpine-normal-latest \
  ogr2ogr \
    -f GeoJSON "/tmp/tests/data/regression/${ident}.geojson" \
    PG: \
    "${EDGE_OFFSET_EDGES_TABLE}" \
    -where "identificatie = '${ident}'" \
    -select "identificatie,underpass_id,edge_id,edge_type" \
    -lco RFC7946=NO
done
