#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 INPUT_DIRECTORY OUTPUT_JSON" >&2
  exit 2
fi

input_dir=$1
output_manifest=$2

command -v jq >/dev/null || {
  echo "jq is not available in PATH" >&2
  exit 1
}

mapfile -d '' input_files < <(
  find "$input_dir" -maxdepth 1 -type f -name '*.city.jsonl' -print0 | sort -z
)

if [[ ${#input_files[@]} -eq 0 ]]; then
  echo "No .city.jsonl files found in $input_dir" >&2
  exit 1
fi

manifest_tmp=$(mktemp "${output_manifest}.tmp.XXXXXX")
trap 'rm -f "$manifest_tmp"' EXIT

{
  for input_file in "${input_files[@]}"; do
    jq -c '
      select(.type == "CityJSONFeature")
      | select(any(
          .CityObjects[];
          .type == "BuildingPart"
          and (
            .attributes.add_underpass_success? == 1
            or .attributes.add_underpass_success? == true
          )
        ))
      | select(.id | type == "string")
      | {
          buildingId: .id,
          maxUnderpassArea: (
            [
              .CityObjects[]
              | .geometry[]?
              | .semantics.surfaces[]?
              | select(.type == "OuterCeilingSurface")
              | .underpass_area?
              | if type == "number" then .
                elif type == "string" then tonumber?
                else empty
                end
            ]
            | max // 0
          )
        }
    ' "$input_file"
  done
} \
  | jq -sc '
      group_by(.buildingId)
      | map({
          buildingId: .[0].buildingId,
          maxUnderpassArea: (map(.maxUnderpassArea) | max)
        })
      | sort_by([-.maxUnderpassArea, .buildingId])
      | map(.buildingId)
    ' \
  > "$manifest_tmp"

mv "$manifest_tmp" "$output_manifest"
trap - EXIT
