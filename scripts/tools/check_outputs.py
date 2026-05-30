#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = ROOT / "frontend" / "public" / "data"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def csv_row_count(path):
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def nonempty(path):
    return path.exists() and path.stat().st_size > 0


def check_video(data_root, video):
    errors = []
    warnings = []
    files = video.get("files", {})
    frame_count = int(video.get("frame_count") or 0)
    quality = {}
    quality_rel = files.get("quality")
    if quality_rel and (data_root / quality_rel).exists():
        quality = read_json(data_root / quality_rel)
    ball_quality_level = str(quality.get("ball_quality_level") or video.get("quality", {}).get("ball_quality_level") or "")

    required = ["analysis", "ball", "players", "motion", "quality", "overlay_video"]
    for key in required:
        rel = files.get(key)
        if not rel:
            errors.append(f"{video['id']}: missing manifest entry {key}")
            continue
        path = data_root / rel
        if not nonempty(path):
            errors.append(f"{video['id']}: missing or empty {rel}")

    analysis_path = data_root / files.get("analysis", "")
    if analysis_path.exists():
        analysis = read_json(analysis_path)
        if int(analysis.get("frame_count") or 0) != frame_count:
            errors.append(f"{video['id']}: manifest frame_count does not match analysis.json")
        if not analysis.get("analysis_meta"):
            errors.append(f"{video['id']}: analysis.json missing analysis_meta")
        if not analysis.get("uploaded_video_meta"):
            errors.append(f"{video['id']}: analysis.json missing uploaded_video_meta")

    for key, expected in (("ball", frame_count), ("players", frame_count * 2), ("motion", frame_count * 2)):
        rel = files.get(key)
        if not rel:
            continue
        path = data_root / rel
        if path.exists():
            rows = csv_row_count(path)
            if key == "ball" and ball_quality_level == "Red" and rows == 0:
                continue
            if rows != expected:
                errors.append(f"{video['id']}: {rel} has {rows} rows, expected {expected}")

    final_rel = files.get("final_video")
    if final_rel and not nonempty(data_root / final_rel):
        warnings.append(f"{video['id']}: final video path is present but file is missing")
    if not final_rel:
        warnings.append(f"{video['id']}: final video missing; overlay is available")
    original_rel = files.get("original_video")
    if original_rel and not nonempty(data_root / original_rel):
        warnings.append(f"{video['id']}: original video path is present but file is missing")
    if not original_rel:
        warnings.append(f"{video['id']}: original video missing; original mode disabled")

    if quality_rel and (data_root / quality_rel).exists():
        warnings.extend(f"{video['id']}: {item}" for item in quality.get("warnings", []))

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate frontend dashboard data exports.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    manifest_path = data_root / "manifest.json"
    errors = []
    warnings = []
    if not nonempty(manifest_path):
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = read_json(manifest_path)
    videos = manifest.get("videos", [])
    if not videos:
        errors.append("manifest contains no videos")
    ids = [video.get("id") for video in videos]
    if manifest.get("default_video") not in ids:
        errors.append("default_video is not in manifest videos")
    uploaded_meta = manifest.get("uploaded_video_meta")
    if not uploaded_meta:
        errors.append("manifest missing uploaded_video_meta")

    for video in videos:
        video_errors, video_warnings = check_video(data_root, video)
        errors.extend(video_errors)
        warnings.extend(video_warnings)

    summary = {
        "ok": not errors,
        "data_root": str(data_root),
        "video_count": len(videos),
        "default_video": manifest.get("default_video"),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
