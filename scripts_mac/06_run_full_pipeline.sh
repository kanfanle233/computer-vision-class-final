#!/usr/bin/env bash
set -euo pipefail

export PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/envs/pytorch_env/bin/python}"
export ANALYSIS_DIR="${ANALYSIS_DIR:-output/analysis}"

mkdir -p "${ANALYSIS_DIR}/logs"

"${PYTHON_BIN}" scripts_mac/00_check_env.py | tee "${ANALYSIS_DIR}/logs/00_check_env.log"
scripts_mac/01_install_deps.sh
scripts_mac/02_fetch_assets.sh
scripts_mac/03_run_analysis.sh
"${PYTHON_BIN}" scripts_mac/04_validate_outputs.py | tee "${ANALYSIS_DIR}/logs/04_validate_outputs.log"
"${PYTHON_BIN}" scripts_mac/05_export_json.py | tee "${ANALYSIS_DIR}/logs/05_export_json.log"

echo "[DONE] Full pipeline completed. See ${ANALYSIS_DIR}/result.json"
