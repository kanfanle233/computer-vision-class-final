import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "output" / "analysis"


def rel(path):
    if not path:
        return None
    return str(path.relative_to(ROOT)) if path.exists() else str(path)


def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


csv_path = ANALYSIS / "short_ball.csv"
if not csv_path.exists():
    candidates = [p for p in ANALYSIS.rglob("*.csv") if "ball" in p.name.lower()]
    csv_path = candidates[0] if candidates else csv_path

rows = []
if csv_path.exists():
    with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        rows = list(csv.DictReader(f))

overlay = ANALYSIS / "end1_fix_swap2_precision_full_regen.mp4"
fx = ANALYSIS / "end1_fix_swap2_precision_full_fx_regen.mp4"
motionstats_path = ANALYSIS / "motionstats_summary.json"
summary_path = ANALYSIS / "analysis_summary.json"

result = {
    "video": "short.mp4",
    "device_preference": "mps",
    "status": "success" if overlay.exists() and fx.exists() and csv_path.exists() else "incomplete",
    "outputs": {
        "short_ball_csv": rel(csv_path) if csv_path.exists() else None,
        "overlay_video": rel(overlay) if overlay.exists() else None,
        "motionstats_output": rel(motionstats_path) if motionstats_path.exists() else None,
        "demo_video": rel(fx) if fx.exists() else None,
    },
    "motionstats": load_json(motionstats_path),
    "validation": load_json(summary_path),
    "ball_tracking_preview": rows[:10],
    "row_count": len(rows),
}

(ANALYSIS / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False))
