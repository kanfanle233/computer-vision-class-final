#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/envs/pytorch_env/bin/python}"
LOG_DIR="output/analysis/logs"
mkdir -p "${LOG_DIR}"

{
  echo "[INFO] Python: ${PYTHON_BIN}"
  "${PYTHON_BIN}" -V
  "${PYTHON_BIN}" -m pip install --upgrade pip setuptools wheel

  # macOS PyTorch wheels include CPU/MPS support. Do not install CUDA wheels.
  "${PYTHON_BIN}" -m pip install --upgrade torch torchvision
  "${PYTHON_BIN}" -m pip install --upgrade torchaudio || echo "[WARN] torchaudio install failed; continuing because this pipeline does not import torchaudio."

  if [[ -f requirements_repro.txt ]]; then
    "${PYTHON_BIN}" -m pip install -r requirements_repro.txt
  fi

  if [[ -f scripts/tracknet_runtime/requirements_tracknet.txt ]]; then
    echo "[INFO] Skipping scripts/tracknet_runtime/requirements_tracknet.txt because it pins old numpy/opencv versions that fail on Apple Silicon + Python 3.10."
  fi

  "${PYTHON_BIN}" -m pip install \
    ultralytics \
    opencv-python \
    pandas \
    numpy \
    scipy \
    matplotlib \
    tqdm \
    moviepy \
    dash \
    parse \
    pillow \
    lapx \
    pycocotools

  "${PYTHON_BIN}" - <<'PY'
import importlib
mods = ["torch", "torchvision", "cv2", "numpy", "pandas", "PIL", "ultralytics", "moviepy", "dash", "parse", "pycocotools"]
missing = []
for name in mods:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append((name, repr(exc)))
if missing:
    raise SystemExit(f"Missing imports after install: {missing}")
import torch
print("torch:", torch.__version__)
print("mps available:", torch.backends.mps.is_available())
device = "mps" if torch.backends.mps.is_available() else "cpu"
print("test tensor device:", torch.ones(2, device=device).device)
PY
} 2>&1 | tee "${LOG_DIR}/01_install_deps.log"
