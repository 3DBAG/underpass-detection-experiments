#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="${INPUT_DIR:-/fastssd/data/3DBAG_old/bouwlagen_features_seq}"
OUTPUT_DIR="${OUTPUT_DIR:-/fastssd/data/3DBAG_old/bouwlagen_features_seq_underpass}"
LOG_DIR="${LOG_DIR:-/fastssd/data/3DBAG_old/logs_add_underpass}"
JOBS="${JOBS:-32}"
ADD_UNDERPASS="${ADD_UNDERPASS:-$(command -v add_underpass || true)}"
CLEAN="${CLEAN:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER_SCRIPT="$SCRIPT_DIR/run_add_underpass.py"
UV_CMD=()

if command -v uv >/dev/null 2>&1; then
  UV_CMD=(uv)
elif command -v nix >/dev/null 2>&1; then
  UV_CMD=(nix develop --command uv)
else
  cat >&2 <<'EOF'
error: neither uv nor nix is available on PATH.

Run this from a shell where the tests flake dev shell is active, or set UV_CMD
manually to a working command prefix.
EOF
  exit 1
fi

if [[ -z "$ADD_UNDERPASS" || ! -x "$ADD_UNDERPASS" ]]; then
  cat >&2 <<'EOF'
error: add_underpass executable not found.

Set ADD_UNDERPASS to the full executable path, for example:
  ADD_UNDERPASS=/path/to/add_underpass ./run_add_underpass.sh
EOF
  exit 1
fi

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "error: input directory not found: $INPUT_DIR" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

input_count="$(find "$INPUT_DIR" -maxdepth 1 -type f -name '*.city.jsonl' | wc -l)"
if [[ "$input_count" -eq 0 ]]; then
  echo "error: no .city.jsonl files found in $INPUT_DIR" >&2
  exit 1
fi

if [[ "$CLEAN" = "1" ]]; then
  find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.city.jsonl' -delete
  find "$LOG_DIR" -maxdepth 1 -type f \( -name '*.log' -o -name '*.json' -o -name 'results.csv' \) -delete
fi

echo "input:       $INPUT_DIR ($input_count files)"
echo "output:      $OUTPUT_DIR"
echo "logs:        $LOG_DIR"
echo "executable:  $ADD_UNDERPASS"
echo "jobs:        $JOBS"
echo "clean first: $CLEAN"

find "$INPUT_DIR" -maxdepth 1 -type f -name '*.city.jsonl' -print0 \
  | parallel -0 --bar -j "$JOBS" \
      "${UV_CMD[@]}" run "$RUNNER_SCRIPT" run \
        --executable "$ADD_UNDERPASS" \
        --input {} \
        --output-dir "$OUTPUT_DIR" \
        --log-dir "$LOG_DIR"

"${UV_CMD[@]}" run "$RUNNER_SCRIPT" aggregate \
  --log-dir "$LOG_DIR" \
  --output "$LOG_DIR/results.csv"
