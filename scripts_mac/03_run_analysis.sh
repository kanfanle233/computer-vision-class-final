#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/envs/pytorch_env/bin/python}"
ANALYSIS_DIR="${ANALYSIS_DIR:-output/analysis}"
TRACKNET_DEVICE="${TRACKNET_DEVICE:-auto}"
YOLO_DEVICE="${YOLO_DEVICE:-mps}"
ALLOW_CPU_FALLBACK="${ALLOW_CPU_FALLBACK:-1}"
LOG_DIR="${ANALYSIS_DIR}/logs"

mkdir -p "${ANALYSIS_DIR}" "${LOG_DIR}"

SHORT_VIDEO="$(find . -type f -name 'short.mp4' ! -path './output/*' | head -n 1 || true)"
if [[ -z "${SHORT_VIDEO}" ]]; then
  echo "ERROR: short.mp4 not found. Check ${LOG_DIR}/02_fetch_assets.log" | tee "${LOG_DIR}/03_run_analysis.log"
  exit 1
fi

if head -n 1 "${SHORT_VIDEO}" | grep -q "version https://git-lfs.github.com/spec"; then
  echo "ERROR: ${SHORT_VIDEO} is a Git LFS pointer, not a real mp4. Run scripts_mac/02_fetch_assets.sh." | tee "${LOG_DIR}/03_run_analysis.log"
  exit 1
fi

for required in run_all_mac.sh weights/TrackNet_best.pt weights/yolov8s-pose.pt; do
  if [[ ! -f "${required}" ]]; then
    echo "ERROR: missing ${required}" | tee "${LOG_DIR}/03_run_analysis.log"
    exit 1
  fi
  if head -n 1 "${required}" | grep -q "version https://git-lfs.github.com/spec"; then
    echo "ERROR: ${required} is a Git LFS pointer. Run scripts_mac/02_fetch_assets.sh." | tee "${LOG_DIR}/03_run_analysis.log"
    exit 1
  fi
done

run_pipeline() {
  local tracknet_device="$1"
  local yolo_device="$2"
  local log_file="$3"
  echo "[INFO] Using video: ${SHORT_VIDEO}" | tee "${log_file}"
  echo "[INFO] Using python: ${PYTHON_BIN}" | tee -a "${log_file}"
  echo "[INFO] TrackNet device: ${tracknet_device}" | tee -a "${log_file}"
  echo "[INFO] YOLO device: ${yolo_device}" | tee -a "${log_file}"
  bash run_all_mac.sh \
    --input-video "${SHORT_VIDEO}" \
    --work-root "${ANALYSIS_DIR}" \
    --python "${PYTHON_BIN}" \
    --tracknet-device "${tracknet_device}" \
    --yolo-device "${yolo_device}" \
    2>&1 | tee -a "${log_file}"
}

chmod +x run_all_mac.sh

if run_pipeline "${TRACKNET_DEVICE}" "${YOLO_DEVICE}" "${LOG_DIR}/03_run_analysis.log"; then
  exit 0
fi

if [[ "${ALLOW_CPU_FALLBACK}" == "1" && "${YOLO_DEVICE}" != "cpu" ]]; then
  echo "[WARN] MPS run failed. Retrying with CPU fallback." | tee -a "${LOG_DIR}/03_run_analysis.log"
  run_pipeline "cpu" "cpu" "${LOG_DIR}/03_run_analysis_cpu_fallback.log"
else
  echo "[ERROR] Pipeline failed and CPU fallback is disabled." | tee -a "${LOG_DIR}/03_run_analysis.log"
  exit 1
fi
