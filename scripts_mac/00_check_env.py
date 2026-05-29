import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "analysis"
LOGS = OUT / "logs"
LOGS.mkdir(parents=True, exist_ok=True)


def run_text(cmd):
    try:
        return subprocess.run(cmd, check=False, capture_output=True, text=True).stdout.strip()
    except Exception as exc:
        return f"ERROR: {exc!r}"


def module_status(name):
    spec = importlib.util.find_spec(name)
    return spec is not None


report = {
    "repo_root": str(ROOT),
    "python": sys.executable,
    "python_version": sys.version,
    "platform": platform.platform(),
    "machine": platform.machine(),
    "macos_version": run_text(["sw_vers", "-productVersion"]),
    "tools": {
        "git": shutil.which("git"),
        "git_lfs": shutil.which("git-lfs"),
        "ffmpeg": shutil.which("ffmpeg"),
        "curl": shutil.which("curl"),
        "brew": shutil.which("brew"),
    },
    "modules": {
        "cv2": module_status("cv2"),
        "numpy": module_status("numpy"),
        "pandas": module_status("pandas"),
        "PIL": module_status("PIL"),
        "torch": module_status("torch"),
        "torchvision": module_status("torchvision"),
        "ultralytics": module_status("ultralytics"),
        "moviepy": module_status("moviepy"),
    },
}

try:
    import torch

    report["torch"] = {
        "version": torch.__version__,
        "mps_available": bool(torch.backends.mps.is_available()),
        "mps_built": bool(torch.backends.mps.is_built()),
        "cuda_available": bool(torch.cuda.is_available()),
    }
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    x = torch.ones(2, device=device)
    report["torch"]["test_tensor_device"] = str(x.device)
except Exception as exc:
    report["torch_error"] = repr(exc)

assets = {}
for rel in [
    "short.mp4",
    "weights/TrackNet_best.pt",
    "weights/yolov8s-pose.pt",
    "demo/short_overlay_demo.mp4",
]:
    path = ROOT / rel
    info = {"exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}
    if path.exists():
        first = path.read_bytes()[:80]
        info["looks_like_lfs_pointer"] = first.startswith(b"version https://git-lfs.github.com/spec")
    assets[rel] = info
report["assets"] = assets

(OUT / "env_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False))
