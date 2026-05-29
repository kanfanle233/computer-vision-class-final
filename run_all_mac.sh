#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  ./run_all_mac.sh --input-video <path_to_mp4> [options]

This compatibility wrapper calls run_pipeline.py. New code may call
`python run_pipeline.py --help` directly.

Options:
  --input-video PATH            Input original video (.mp4)
  --work-root PATH              Output directory (default: output/<video_id>)
  --court-points STR            Court points in TL,TR,BR,BL order
  --manual-court                Select four court corners interactively
  --ball-csv PATH               Reuse an existing verified ball CSV
  --python PATH                 Python executable (default: python3)
  --tracknet-device STR         auto/cuda/mps/cpu (default: auto)
  --yolo-device STR             Alias for --pose-device
  --pose-imgsz INT              YOLO pose inference size (default: 960)
  --detect-interval INT         Detect every N frames (default: 1)
  --tracknet-eval-mode STR      weight/average/nonoverlap
  --embedded-panels             Draw panels directly in rendered video
  --cinematic-fx                Enable slow-motion effects
  --no-frontend-export          Skip dashboard data export
  -h, --help                    Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="${2:-}"; shift 2 ;;
    --yolo-device)
      PIPELINE_ARGS+=("--pose-device" "${2:-}"); shift 2 ;;
    --input-video|--work-root|--court-points|--ball-csv|--tracknet-device|--pose-imgsz|--detect-interval|--tracknet-eval-mode)
      PIPELINE_ARGS+=("$1" "${2:-}"); shift 2 ;;
    --manual-court|--embedded-panels|--cinematic-fx|--no-frontend-export)
      PIPELINE_ARGS+=("$1"); shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "[ERROR] Unknown arg: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ -n "${TRACKNET_VIS_THRESH:-}" ]]; then
  PIPELINE_ARGS+=("--tracknet-threshold" "${TRACKNET_VIS_THRESH}")
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_pipeline.py" "${PIPELINE_ARGS[@]}"
