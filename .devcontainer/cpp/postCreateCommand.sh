#!/bin/bash
set -euo pipefail

# Enable debug output
set -x

echo "=== Starting postCreateCommand ==="

# Install Claude
curl -fsSL https://claude.ai/install.sh | bash

# Install Codex
npm install -g @openai/codex

## Create vcpkg directories
#mkdir -p "${VCPKG_ROOT}" "${VCPKG_BINARY_CACHE}"

## Install vcpkg dependencies
#proj_dir="$(pwd)"
#cd "${VCPKG_ROOT}"
#git config --global --add safe.directory /usr/local/vcpkg
#git pull --ff-only
#cd "${proj_dir}"
#vcpkg install

echo "=== postCreateCommand completed ==="
