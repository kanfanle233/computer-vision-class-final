import csv
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "output" / "analysis"
LOGS = ANALYSIS / "logs"
LOGS.mkdir(parents=True, exist_ok=True)


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def count_csv_rows(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in csv.reader(f))


def first_nonempty(paths):
    for path in paths:
        if nonempty(path):
            return path
    return paths[0] if paths else None


files = list(ANALYSIS.rglob("*")) if ANALYSIS.exists() else []
csv_files = sorted(p for p in files if p.suffix.lower() == ".csv")
video_files = sorted(p for p in files if p.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"})
json_files = sorted(p for p in files if p.suffix.lower() == ".json")

short_ball = ANALYSIS / "short_ball.csv"
if not short_ball.exists():
    candidates = [p for p in csv_files if p.name == "short_ball.csv" or "ball" in p.name.lower()]
    short_ball = candidates[0] if candidates else short_ball

overlay = first_nonempty(
    [
        ANALYSIS / "end1_fix_swap2_precision_full_regen.mp4",
        *sorted(ANALYSIS.glob("*_overlay.mp4")),
    ]
)
fx = first_nonempty(
    [
        ANALYSIS / "end1_fix_swap2_precision_full_fx_regen.mp4",
        *sorted(ANALYSIS.glob("*_final.mp4")),
    ]
)
motionstats = first_nonempty(
    [
        ANALYSIS / "motionstats_summary.json",
        *sorted(ANALYSIS.glob("*_stats.json")),
    ]
)

checks = {
    "analysis_dir_exists": ANALYSIS.exists(),
    "csv_files": [str(p.relative_to(ROOT)) for p in csv_files],
    "video_files": [str(p.relative_to(ROOT)) for p in video_files],
    "json_files": [str(p.relative_to(ROOT)) for p in json_files],
    "short_ball_csv": str(short_ball.relative_to(ROOT)) if short_ball.exists() else None,
    "short_ball_not_empty": nonempty(short_ball),
    "short_ball_rows": count_csv_rows(short_ball) if nonempty(short_ball) else 0,
    "overlay_video": str(overlay.relative_to(ROOT)) if overlay and overlay.exists() else None,
    "overlay_video_not_empty": nonempty(overlay),
    "fx_demo_video": str(fx.relative_to(ROOT)) if fx and fx.exists() else None,
    "fx_demo_video_not_empty": nonempty(fx),
    "motionstats_json": str(motionstats.relative_to(ROOT)) if motionstats and motionstats.exists() else None,
    "motionstats_json_not_empty": nonempty(motionstats),
}

summary = {
    "ok": (
        checks["analysis_dir_exists"]
        and checks["short_ball_not_empty"]
        and checks["short_ball_rows"] > 1
        and checks["overlay_video_not_empty"]
        and checks["fx_demo_video_not_empty"]
        and checks["motionstats_json_not_empty"]
    ),
    "checks": checks,
}

summary_path = ANALYSIS / "analysis_summary.json"
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))

if not summary["ok"]:
    archive = ANALYSIS / "failure_logs.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        if LOGS.exists():
            tar.add(LOGS, arcname="logs")
        tar.add(summary_path, arcname="analysis_summary.json")
    raise SystemExit(f"Validation failed. Logs packed at {archive}")
