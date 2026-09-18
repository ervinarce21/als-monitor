#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="$(readlink -f -- "$0")"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd)"
LAUNCHER="$SCRIPT_DIR/als-monitor"
INSTALL_PATH="/usr/local/bin/nexa"

if [[ ! -f "$LAUNCHER" ]]; then
    echo "Launcher not found: $LAUNCHER" >&2
    exit 1
fi

chmod +x "$LAUNCHER"
sudo ln -sfn "$LAUNCHER" "$INSTALL_PATH"

echo "Installed: $INSTALL_PATH"
echo "Run 'nexa' from any directory."

