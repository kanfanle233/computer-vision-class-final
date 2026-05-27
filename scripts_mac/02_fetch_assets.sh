#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="output/analysis/logs"
mkdir -p "${LOG_DIR}"

PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/envs/pytorch_env/bin/python}"
LFS_BATCH_URL="${LFS_BATCH_URL:-https://github.com/ychenfen/badminton-pipeline-repro.git/info/lfs/objects/batch}"
LFS_WORKERS="${LFS_WORKERS:-24}"
LFS_CHUNK_SIZE="${LFS_CHUNK_SIZE:-4194304}"

is_lfs_pointer() {
  local path="$1"
  [[ -f "${path}" ]] && head -n 1 "${path}" | grep -q "version https://git-lfs.github.com/spec"
}

download_asset() {
  local rel="$1"
  local oid="$2"
  local expected_size="$3"
  local path="${rel}"
  mkdir -p "$(dirname "${path}")"

  if [[ -s "${path}" ]] && ! is_lfs_pointer "${path}"; then
    echo "[OK] ${path} already downloaded ($(wc -c < "${path}") bytes)"
    return 0
  fi

  echo "[INFO] Downloading ${rel}"
  "${PYTHON_BIN}" scripts_mac/download_lfs_parallel.py \
    --output "${path}" \
    --oid "${oid}" \
    --size "${expected_size}" \
    --batch-url "${LFS_BATCH_URL}" \
    --workers "${LFS_WORKERS}" \
    --chunk-size "${LFS_CHUNK_SIZE}"
}

{
  echo "[INFO] Fetching required LFS assets without requiring local git-lfs..."
  download_asset "inputs/short.mp4" "9fc16cad2c812ee6255d9447a88da5de0caed90e68d41c50809a18487a334f2d" "2111189"
  download_asset "weights/TrackNet_best.pt" "b8b8e61775eca5dc6f311a704761419c5e9524e74db6739fce057f3ff27a3e28" "136118079"
  download_asset "weights/yolov8s-pose.pt" "234314cd8baf62616791aceb9ea6ad5c19f26cf6c0d8f3a1bfce1e23b186cfb3" "23513657"
  if [[ "${SKIP_PREBUILT_DEMO:-1}" != "1" ]]; then
    download_asset "demo/short_overlay_demo.mp4" "f7864b2e13732d0f23ff64f08ca8f81711caf9dfb51ef6f9b8502b63934561d1" "13605055"
  else
    echo "[INFO] Skipping prebuilt demo/short_overlay_demo.mp4 because it is not required for inference."
  fi

  echo "[INFO] Asset summary:"
  find inputs/short.mp4 weights demo -maxdepth 2 -type f -print -exec wc -c {} \;
} 2>&1 | tee "${LOG_DIR}/02_fetch_assets.log"
