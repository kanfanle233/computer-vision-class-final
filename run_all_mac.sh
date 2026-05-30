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
  --court-length-m FLOAT        Physical court length (13.4 full court, 6.7 half court)
  --court-width-m FLOAT         Physical court width (default: 6.1)
  --manual-court                Select four court corners interactively
  --ball-csv PATH               Reuse an existing verified ball CSV
  --python PATH                 Python executable (default: python3)
  --tracknet-device STR         auto/cuda/mps/cpu (default: auto)
  --yolo-device STR             Alias for --pose-device
  --pose-imgsz INT              YOLO pose inference size (default: 960)
  --detect-interval INT         Detect every N frames (default: 1)
  --tracknet-eval-mode STR      weight/average/nonoverlap
  --inpaintnet-file PATH        Optional InpaintNet weight
  --filter-ball                 Apply conservative shuttle false-positive filtering
  --refine-ball                 Apply the enhanced shuttle trajectory refinement
  --ball-top-pad-px FLOAT       Allowed flight space above far baseline
  --ball-side-pad-px FLOAT      Allowed flight space outside sidelines
  --ball-min-motion-score FLOAT Reject near-static shuttle candidates below score
  --ball-refine-min-motion-score FLOAT Motion gate for refine path (default 0.0)
  --ball-max-interp-gap INT     Interpolate at most this many missing frames
  --ball-refine-max-gap INT     Interpolate at most this many missing frames in refine path
  --ball-max-interp-step-px FLOAT Max per-frame step for jump rejection and interpolation
  --tracknet-mask               Mask broadcast overlays before TrackNet only
  --tracknet-mask-preset STR    none/top_bar/top_right_scoreboard/custom_json
  --tracknet-mask-json PATH     JSON with custom mask rectangles
  --tracknet-mask-fill STR      black/blur/median
  --tracknet-mask-debug-video   Save the masked TrackNet input video
  --draw-court-polygon          Draw calibrated green quadrilateral for checking
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
    --input-video|--work-root|--court-points|--ball-csv|--tracknet-device|--pose-imgsz|--detect-interval|--tracknet-eval-mode|--court-length-m|--court_width_m|--court-width-m|--court_length_m|--inpaintnet-file|--ball-top-pad-px|--ball-side-pad-px|--ball-min-motion-score|--ball-refine-min-motion-score|--ball-max-interp-gap|--ball-refine-max-gap|--ball-max-interp-step-px|--tracknet-mask-preset|--tracknet-mask-json|--tracknet-mask-fill)
      PIPELINE_ARGS+=("$1" "${2:-}"); shift 2 ;;
    --manual-court|--filter-ball|--refine-ball|--tracknet-mask|--tracknet-mask-debug-video|--draw-court-polygon|--draw_court_polygon|--embedded-panels|--cinematic-fx|--no-frontend-export)
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
