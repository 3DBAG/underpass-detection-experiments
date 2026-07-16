#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 INPUT_DIRECTORY OUTPUT_FCB" >&2
  exit 2
fi

input_dir=$1
output_fcb=$2

command -v fcb >/dev/null || {
  echo "fcb is not available in PATH" >&2
  exit 1
}
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

temporary_dir=$(mktemp -d)
trap 'rm -rf "$temporary_dir"' EXIT

first_file=${input_files[0]}
clean_first="$temporary_dir/$(basename "$first_file")"

# FCB currently fetches declared extension schemas while writing its header.
# The viewer does not use the val3dity extension, so make the merged header
# self-contained while leaving all feature records untouched.
{
  head -n 1 "$first_file" | jq -c 'del(.extensions)'
  tail -n +2 "$first_file"
} > "$clean_first"

echo "Building $output_fcb from ${#input_files[@]} CityJSONSeq files"
fcb ser \
  -i "$clean_first" "${input_files[@]:1}" \
  -o "$output_fcb" \
  -a identificatie \
  -g

underpass_manifest="${output_fcb%.fcb}.underpasses.json"
echo "Building $underpass_manifest"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
"$script_dir/build-underpass-manifest.sh" "$input_dir" "$underpass_manifest"
