#!/usr/bin/env bash
set -euo pipefail

remote_host="${DEPLOY_HOST:-godzilla}"
remote_path="${DEPLOY_PATH:-/var/www/innovatiebudget-3dtiles}"
remote="${remote_host}:${remote_path}/"
tileset_dir="${1:-}"
uploaded_tileset_name=""

usage() {
  echo "Usage: bun run deploy -- [tileset-directory]" >&2
  echo "       DEPLOY_HOST=host DEPLOY_PATH=/remote/path bun run deploy -- [tileset-directory]" >&2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if (( $# > 1 )); then
  usage
  exit 1
fi

for command in bun ssh rsync; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

quote_remote() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

if [[ ! -d node_modules/cesium/Build/Cesium ]]; then
  bun install --frozen-lockfile
fi

bun run build

remote_path_q="$(quote_remote "$remote_path")"
remote_data_path="${remote_path%/}/data"
remote_data_path_q="$(quote_remote "$remote_data_path")"

ssh "$remote_host" "mkdir -p $remote_path_q $remote_data_path_q"
rsync -az --delete --exclude "data/" --exclude "*/3dt-export-nl*/" dist/ "$remote"

echo "Deployed dist/ to $remote"

if [[ -n "$tileset_dir" ]]; then
  if [[ ! -d "$tileset_dir" ]]; then
    echo "Tileset directory does not exist: $tileset_dir" >&2
    exit 1
  fi

  tileset_abs="$(cd "$tileset_dir" && pwd -P)"
  if [[ ! -f "$tileset_abs/tileset.json" ]]; then
    echo "Tileset directory must contain tileset.json: $tileset_abs" >&2
    exit 1
  fi

  tileset_name="$(basename "$tileset_abs")"
  uploaded_tileset_name="$tileset_name"
  remote_tileset="${remote_host}:${remote_data_path}/${tileset_name}/"
  rsync -az "$tileset_abs/" "$remote_tileset"
  echo "Synced tileset $tileset_abs to $remote_tileset"
fi

uploaded_tileset_name_q="$(quote_remote "$uploaded_tileset_name")"

ssh "$remote_host" "DATA_DIR=$remote_data_path_q UPLOADED_TILESET=$uploaded_tileset_name_q python3 - <<'PY'
import json
import os
from pathlib import Path
from urllib.parse import quote

data_dir = Path(os.environ['DATA_DIR'])
uploaded_tileset = os.environ.get('UPLOADED_TILESET', '')
manifest_path = data_dir / 'tilesets.json'
existing_entries = []

if manifest_path.exists():
    with manifest_path.open('r', encoding='utf-8') as f:
        existing = json.load(f)
    if isinstance(existing, list):
        existing_entries = existing
    elif isinstance(existing, dict) and isinstance(existing.get('tilesets'), list):
        existing_entries = existing['tilesets']
    else:
        raise SystemExit(f'Unsupported manifest format in {manifest_path}')

scanned = {}
for tileset_json in sorted(data_dir.glob('*/tileset.json')):
    name = tileset_json.parent.name
    url = f'data/{quote(name)}/tileset.json'
    scanned[url] = {
        'name': name,
        'label': name,
        'url': url,
    }

merged = []
seen = set()
for entry in existing_entries:
    if isinstance(entry, str):
        merged.append(entry)
        seen.add(entry)
        continue

    if not isinstance(entry, dict):
        continue

    url = str(entry.get('url') or entry.get('href') or '')
    name = str(entry.get('name') or '')
    scanned_entry = scanned.get(url) or scanned.get(f'data/{quote(name)}/tileset.json')
    if scanned_entry:
        next_entry = {**scanned_entry, **entry}
        next_entry['url'] = url or scanned_entry['url']
        next_entry['name'] = entry.get('name') or scanned_entry['name']
        next_entry['label'] = entry.get('label') or entry.get('name') or scanned_entry['label']
        merged.append(next_entry)
        seen.add(scanned_entry['url'])
    else:
        merged.append(entry)
        if url:
            seen.add(url)

for url, entry in scanned.items():
    if url not in seen:
        merged.append(entry)

if uploaded_tileset:
    uploaded_url = f'data/{quote(uploaded_tileset)}/tileset.json'
    uploaded_entries = []
    remaining_entries = []
    for entry in merged:
        entry_url = entry if isinstance(entry, str) else str(entry.get('url') or entry.get('href') or '')
        if entry_url == uploaded_url:
            uploaded_entries.append(entry)
        else:
            remaining_entries.append(entry)
    merged = remaining_entries + uploaded_entries

tmp_path = manifest_path.with_suffix('.json.tmp')
with tmp_path.open('w', encoding='utf-8') as f:
    json.dump({'tilesets': merged}, f, indent=2)
    f.write('\n')
tmp_path.replace(manifest_path)
print(f'Wrote {manifest_path} with {len(merged)} tileset entries')
PY"
