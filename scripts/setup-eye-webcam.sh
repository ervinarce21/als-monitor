#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="$ROOT/.venv-shoulder/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Create the working .venv-shoulder environment first (see README)." >&2
    exit 2
fi
# Preserve the working MediaPipe version; eye assessment also needs pygame.
if [[ -x "$ROOT/.venv/bin/uv" ]]; then
    "$ROOT/.venv/bin/uv" pip install --python "$PYTHON" pygame
else
    "$PYTHON" -m ensurepip
    "$PYTHON" -m pip install pygame
fi
mkdir -p "$ROOT/data/models"
MODEL="$ROOT/data/models/face_landmarker.task"
if [[ ! -s "$MODEL" ]]; then
    TEMP_MODEL="$(mktemp "$ROOT/data/models/face_landmarker.XXXXXX")"
    trap 'rm -f -- "$TEMP_MODEL"' EXIT
    curl -fL https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o "$TEMP_MODEL"
    mv -- "$TEMP_MODEL" "$MODEL"
fi
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON" -u -X faulthandler -c 'from als_monitor.eye_tracker.face_tracker import FaceTracker; t = FaceTracker(); t.close(); print("Eye model initialization OK")'
echo "Ready: nexa preview --camera webcam"
