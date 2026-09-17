#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="$(readlink -f -- "$0")"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd)"

# Install or refresh the command used by each desktop shortcut.
bash "$SCRIPT_DIR/install-launcher.sh"

DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [[ -z "$DESKTOP_DIR" ]]; then
    DESKTOP_DIR="$HOME/Desktop"
fi
mkdir -p "$DESKTOP_DIR"

create_shortcut() {
    local filename="$1"
    local name="$2"
    local comment="$3"
    local icon="$4"
    local service="$5"
    local destination="$DESKTOP_DIR/$filename"

    cat > "$destination" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$name
Comment=$comment
Exec=/usr/local/bin/als-monitor $service
Icon=$icon
Terminal=true
Categories=Science;Utility;
StartupNotify=true
EOF

    chmod +x "$destination"

    # Some Raspberry Pi desktop environments track launcher trust separately.
    if command -v gio >/dev/null 2>&1; then
        gio set "$destination" metadata::trusted true >/dev/null 2>&1 || true
    fi

    echo "Created: $destination"
}

create_shortcut \
    "als-eye-tracker.desktop" \
    "ALS Eye Tracker" \
    "Run the IR eye-tracking and prosaccade service" \
    "camera-photo" \
    "eye"

create_shortcut \
    "als-grip-monitor.desktop" \
    "ALS Grip Monitor" \
    "Run the left and right grip-strength service" \
    "utilities-system-monitor" \
    "grip"

create_shortcut \
    "als-shoulder-monitor.desktop" \
    "ALS Shoulder Monitor" \
    "Run the shoulder-angle and arm-raise service" \
    "camera-video" \
    "shoulder"

echo "Desktop shortcuts installed successfully."

