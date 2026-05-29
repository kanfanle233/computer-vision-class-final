#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import cv2

from transcode_browser_video import transcode_to_h264, video_codec
from evaluate_ball_tracking import evaluate_files


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "output"
DEFAULT_DATA_ROOT = ROOT / "frontend" / "public" / "data"
COURT_WIDTH_M = 6.1
COURT_LENGTH_M = 13.4
TRAJECTORY_MODES = ("reference", "raw_prediction", "filtered_prediction")
MIN_OPTIMIZED_F1_AT_10 = 0.154
_reference_candidates = [
    Path(os.environ["BADMINTON_UPLOADED_VIDEO"]) if os.environ.get("BADMINTON_UPLOADED_VIDEO") else None,
    ROOT / "inputs" / "前端可视化.mp4",
    Path("/Users/davidfang/Desktop/lida/计算机视觉/前端可视化.mp4"),
]
UPLOADED_VIDEO_PATH = next(
    (path for path in _reference_candidates if path is not None and path.exists()),
    ROOT / "inputs" / "前端可视化.mp4",
)


def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_csv_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def as_float(value, default=0.0):
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def fmt(value, digits=6):
    if value in ("", None):
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    return f"{float(value):.{digits}f}"


def find_first(paths):
    for path in paths:
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def source_video_path(stats, video_id):
    """Use the actual analyzed input, including a video outside this checkout."""
    bundled_input = find_first([ROOT / "inputs" / f"{video_id}.mp4"])
    if bundled_input:
        return bundled_input
    raw_path = str(stats.get("video_path") or "").strip()
    if raw_path:
        path = Path(raw_path).expanduser()
        path = path if path.is_absolute() else ROOT / path
        if path.exists() and path.stat().st_size > 0:
            return path.resolve()
    return None


def video_metadata(path):
    if not path or not path.exists():
        return None
    cap = cv2.VideoCapture(str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    meta = {
        "file_name": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frames,
        "duration_s": frames / fps if fps else 0.0,
        "resolution": f"{width}x{height}" if width and height else "",
    }
    if path == UPLOADED_VIDEO_PATH:
        meta.update({
            "codec": "H.264 / AVC",
            "bitrate_kbps": 123.6,
            "audio_codec": "AAC LC",
            "audio_sample_rate_hz": 44100,
            "audio_channels": "stereo",
            "audio_duration_s": 265.61,
        })
    return meta


def uploaded_video_meta():
    meta = video_metadata(UPLOADED_VIDEO_PATH)
    if meta:
        meta["source"] = "uploaded_reference_video"
        return meta
    return {
        "file_name": "前端可视化.mp4",
        "path": str(UPLOADED_VIDEO_PATH),
        "source": "missing_reference_video",
        "warning": "Uploaded reference video was not found on disk.",
    }


def compute_homography(court_points, court_size):
    src = np.array(court_points, dtype=np.float64)
    dst = np.array(
        [
            [0.0, 0.0],
            [court_size["width"], 0.0],
            [court_size["width"], court_size["length"]],
            [0.0, court_size["length"]],
        ],
        dtype=np.float64,
    )
    rows = []
    rhs = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        rhs.append(v)
    h = np.linalg.solve(np.array(rows), np.array(rhs))
    return np.array(
        [
            [h[0], h[1], h[2]],
            [h[3], h[4], h[5]],
            [h[6], h[7], 1.0],
        ],
        dtype=np.float64,
    )


def to_court(point, homography):
    if point is None or homography is None:
        return None
    src = np.array([point[0], point[1], 1.0], dtype=np.float64)
    dst = homography.dot(src)
    if abs(dst[2]) < 1e-9:
        return None
    return (float(dst[0] / dst[2]), float(dst[1] / dst[2]))


def missing_segments(flags):
    segments = []
    start = None
    for idx, missing in enumerate(flags):
        if missing and start is None:
            start = idx
        elif not missing and start is not None:
            segments.append({"start_frame": start, "end_frame": idx - 1, "length": idx - start})
            start = None
    if start is not None:
        segments.append({"start_frame": start, "end_frame": len(flags) - 1, "length": len(flags) - start})
    return segments


def guess_video_id(stats_path, stats):
    if stats.get("video_id"):
        return str(stats["video_id"])
    name = stats_path.parent.name
    return name if name else "latest"


def add_latest_source(sources, source):
    """Retain the freshest complete export source for each video id."""
    video_id = source["video_id"]
    previous = sources.get(video_id)
    if previous is None or source.get("source_mtime", 0) >= previous.get("source_mtime", 0):
        sources[video_id] = source


def discover_sources():
    sources = {}
    for directory in sorted(OUTPUT_ROOT.iterdir() if OUTPUT_ROOT.exists() else []):
        if not directory.is_dir():
            continue
        if directory.name == "analysis" or directory.name.startswith("analysis_"):
            continue
        stats_candidates = sorted(directory.glob("*_stats.json"))
        ball_candidates = sorted(directory.glob("*_ball.csv"))
        if not stats_candidates and not ball_candidates:
            continue
        stats_path = stats_candidates[0] if stats_candidates else None
        stats = read_json(stats_path) if stats_path else {}
        video_id = guess_video_id(stats_path or directory / "placeholder.json", stats)
        source = {
            "video_id": video_id,
            "root": directory,
            "original": source_video_path(stats, video_id),
            "stats": stats_path,
            "ball": find_first([directory / f"{video_id}_ball.csv", *ball_candidates]),
            "players": find_first([directory / f"{video_id}_players.csv"]),
            "motion": find_first([directory / f"{video_id}_motion.csv"]),
            "overlay": find_first([directory / f"{video_id}_overlay.mp4"]),
            "final": find_first([directory / f"{video_id}_final.mp4"]),
            "trajectory_metadata": directory / "trajectories" / "metadata.json",
            "source_mtime": max((p.stat().st_mtime for p in directory.rglob("*") if p.is_file()), default=0),
        }
        if has_nonempty_final(source):
            add_latest_source(sources, source)

    standard_stats = OUTPUT_ROOT / "analysis.json"
    if standard_stats.exists():
        stats = read_json(standard_stats)
        video_id = stats.get("video_id") or Path(str(stats.get("output_path", "latest"))).stem.replace("_overlay", "")
        video_id = str(video_id or "latest")
        source = {
            "video_id": video_id,
            "root": OUTPUT_ROOT,
            "original": source_video_path(stats, video_id),
            "stats": standard_stats,
            "ball": find_first([OUTPUT_ROOT / "ball.csv"]),
            "players": find_first([OUTPUT_ROOT / "players.csv"]),
            "motion": find_first([OUTPUT_ROOT / "motion.csv"]),
            "overlay": find_first([OUTPUT_ROOT / "overlay.mp4"]),
            "final": find_first([OUTPUT_ROOT / "final.mp4", OUTPUT_ROOT / f"{video_id}" / f"{video_id}_final.mp4"]),
            "trajectory_metadata": OUTPUT_ROOT / "trajectories" / "metadata.json",
            "source_mtime": max(
                (p.stat().st_mtime for p in [standard_stats, OUTPUT_ROOT / "ball.csv", OUTPUT_ROOT / "overlay.mp4"] if p.exists()),
                default=0,
            ),
        }
        if has_nonempty_final(source):
            add_latest_source(sources, source)
    return sources


def source_paths_for_video(source):
    root = source["root"]
    video_id = source["video_id"]
    return {
        "ball": source.get("ball") or root / f"{video_id}_ball.csv",
        "players": source.get("players") or root / f"{video_id}_players.csv",
        "motion": source.get("motion") or root / f"{video_id}_motion.csv",
        "stats": source.get("stats") or root / f"{video_id}_stats.json",
        "original": source.get("original") or ROOT / "inputs" / f"{video_id}.mp4",
        "overlay": source.get("overlay") or root / f"{video_id}_overlay.mp4",
        "final": source.get("final") or root / f"{video_id}_final.mp4",
    }


def trajectory_paths_for_video(source):
    root = source["root"]
    video_id = source["video_id"]
    trajectory_root = root / "trajectories"
    return {
        "reference": find_first([trajectory_root / "reference.csv", ROOT / "inputs" / f"{video_id}_ball.csv"]),
        "raw_prediction": find_first(
            [trajectory_root / "raw_prediction.csv", root / "tracknet_v3_result_regen" / f"{video_id}_ball.csv"]
        ),
        "filtered_prediction": find_first([trajectory_root / "filtered_prediction.csv"]),
    }


def has_nonempty_final(source):
    final_path = source.get("final")
    return bool(final_path and final_path.exists() and final_path.stat().st_size > 0)


def normalize_ball(rows, frame_count, fps, homography, ball_shift, source_type="raw_prediction"):
    by_frame = {as_int(r.get("Frame", r.get("frame", 0))): r for r in rows}
    out = []
    prev = None
    missing_flags = []
    visible_count = 0
    for frame in range(frame_count):
        raw = by_frame.get(frame, {})
        visibility = as_int(raw.get("Visibility", raw.get("visibility", 0)))
        x_px = as_float(raw.get("X", raw.get("x_px", "")), default=math.nan)
        y_px = as_float(raw.get("Y", raw.get("y_px", "")), default=math.nan)
        missing = visibility <= 0 or math.isnan(x_px) or math.isnan(y_px) or (x_px == 0 and y_px == 0)
        source = raw.get("Source", raw.get("source", "missing" if missing else source_type))
        court = None if missing else to_court((x_px, y_px), homography)
        if court is not None:
            court = (float(np.clip(court[0] + ball_shift, 0.0, COURT_WIDTH_M)), float(np.clip(court[1], 0.0, COURT_LENGTH_M)))
        speed = 0.0
        time_s = frame / max(fps, 1e-6)
        if court is not None and prev is not None:
            dt = max(time_s - prev["time_s"], 1e-6)
            speed = math.dist(court, prev["court"]) / dt
        if court is not None:
            prev = {"time_s": time_s, "court": court}
            visible_count += 1
        missing_flags.append(missing)
        out.append({
            "frame": frame,
            "time_s": fmt(time_s),
            "visibility": 0 if missing else 1,
            "x_px": "" if missing else fmt(x_px, 3),
            "y_px": "" if missing else fmt(y_px, 3),
            "court_x_m": "" if court is None else fmt(court[0]),
            "court_y_m": "" if court is None else fmt(court[1]),
            "speed_mps": fmt(speed),
            "is_missing": int(missing),
            "is_interpolated": int(source == "interp"),
            "source": source,
            "confidence": raw.get("Confidence", raw.get("confidence", "")),
        })
    return out, visible_count, missing_segments(missing_flags)


def normalize_players(rows, frame_count, fps, homography):
    out = []
    has_long = bool(rows and "role" in rows[0])
    if has_long:
        for row in rows:
            frame = as_int(row.get("frame", row.get("Frame", 0)))
            role = row.get("role", "near")
            x_px = as_float(row.get("x_px", ""), default=math.nan)
            y_px = as_float(row.get("y_px", ""), default=math.nan)
            court_x = row.get("court_x_m", "")
            court_y = row.get("court_y_m", "")
            if (court_x == "" or court_y == "") and not math.isnan(x_px) and not math.isnan(y_px):
                court = to_court((x_px, y_px), homography)
                court_x = "" if court is None else fmt(court[0])
                court_y = "" if court is None else fmt(court[1])
            out.append({
                "frame": frame,
                "time_s": row.get("time_s", fmt(frame / max(fps, 1e-6))),
                "role": role,
                "track_id": row.get("track_id", ""),
                "x_px": row.get("x_px", ""),
                "y_px": row.get("y_px", ""),
                "court_x_m": court_x,
                "court_y_m": court_y,
                "bbox_x1": row.get("bbox_x1", ""),
                "bbox_y1": row.get("bbox_y1", ""),
                "bbox_x2": row.get("bbox_x2", ""),
                "bbox_y2": row.get("bbox_y2", ""),
                "confidence": row.get("confidence", "0"),
                "source": row.get("source", "detected"),
            })
        return out

    by_frame = {as_int(r.get("Frame", 0)): r for r in rows}
    for frame in range(frame_count):
        raw = by_frame.get(frame, {})
        for role, prefix in (("near", "Near"), ("far", "Far")):
            x_px = as_float(raw.get(f"{prefix}_X", ""), default=math.nan)
            y_px = as_float(raw.get(f"{prefix}_Y", ""), default=math.nan)
            missing = not rows or math.isnan(x_px) or math.isnan(y_px) or (x_px == 0 and y_px == 0)
            court = None if missing else to_court((x_px, y_px), homography)
            out.append({
                "frame": frame,
                "time_s": fmt(frame / max(fps, 1e-6)),
                "role": role,
                "track_id": "",
                "x_px": "" if missing else fmt(x_px, 3),
                "y_px": "" if missing else fmt(y_px, 3),
                "court_x_m": "" if court is None else fmt(court[0]),
                "court_y_m": "" if court is None else fmt(court[1]),
                "bbox_x1": "",
                "bbox_y1": "",
                "bbox_x2": "",
                "bbox_y2": "",
                "confidence": "0",
                "source": "missing" if missing else "legacy",
            })
    return out


def normalize_motion(rows, frame_count, fps):
    out = []
    has_long = bool(rows and "role" in rows[0])
    if has_long:
        for row in rows:
            frame = as_int(row.get("frame", row.get("Frame", 0)))
            out.append({
                "frame": frame,
                "time_s": row.get("time_s", fmt(frame / max(fps, 1e-6))),
                "role": row.get("role", "near"),
                "speed_mps": row.get("speed_mps", "0"),
                "cumulative_distance_m": row.get("cumulative_distance_m", "0"),
                "rally_distance_m": row.get("rally_distance_m", "0"),
                "max_speed_so_far_mps": row.get("max_speed_so_far_mps", "0"),
            })
        return out

    by_frame = {as_int(r.get("Frame", 0)): r for r in rows}
    for frame in range(frame_count):
        raw = by_frame.get(frame, {})
        for role, prefix in (("near", "Near"), ("far", "Far")):
            speed = as_float(raw.get(f"{prefix}_Speed_mps", 0.0))
            distance = as_float(raw.get(f"{prefix}_Dist_m", 0.0))
            out.append({
                "frame": frame,
                "time_s": fmt(frame / max(fps, 1e-6)),
                "role": role,
                "speed_mps": fmt(speed),
                "cumulative_distance_m": fmt(distance),
                "rally_distance_m": fmt(distance),
                "max_speed_so_far_mps": fmt(speed),
            })
    return out


def player_coverage(players, frame_count):
    counts = {"near": set(), "far": set()}
    for row in players:
        if row.get("source") != "missing" and row.get("court_x_m") != "":
            counts.setdefault(row.get("role", ""), set()).add(as_int(row.get("frame", 0)))
    return {
        "near": len(counts.get("near", set())) / max(frame_count, 1),
        "far": len(counts.get("far", set())) / max(frame_count, 1),
    }


def export_one(source, data_root):
    paths = source_paths_for_video(source)
    stats = read_json(paths["stats"])
    trajectory_metadata = read_json(source["trajectory_metadata"]) if source.get("trajectory_metadata") and source["trajectory_metadata"].exists() else {}
    video_id = source["video_id"]
    fps = float(stats.get("fps") or 30.0)
    frame_count = int(stats.get("frame_count") or stats.get("frames_processed") or stats.get("source_frames") or 0)
    ball_rows_raw = read_csv_rows(paths["ball"])
    if frame_count <= 0 and ball_rows_raw:
        frame_count = max(as_int(r.get("Frame", r.get("frame", 0))) for r in ball_rows_raw) + 1
    court_points = stats.get("court_points_px") or stats.get("court_points") or []
    court_size = stats.get("court_size_m") or {"width": COURT_WIDTH_M, "length": COURT_LENGTH_M}
    homography = np.array(stats["homography"], dtype=np.float64) if stats.get("homography") else None
    if homography is None and court_points:
        homography = compute_homography(court_points, court_size)
    ball_shift = float(stats.get("ball_center_shift_m") or 0.0)

    video_dir = data_root / "videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    trajectory_paths = trajectory_paths_for_video(source)
    mode_rows = {}
    mode_quality = {}
    export_warnings = []
    reference_path = trajectory_paths["reference"]
    for mode in TRAJECTORY_MODES:
        path = trajectory_paths.get(mode)
        if not path:
            continue
        evaluation = None
        if mode != "reference" and reference_path:
            evaluation = evaluate_files(reference_path, path, source_type=mode, video_id=video_id)
            if not evaluation["integrity"]["valid"]:
                export_warnings.append(f"{mode} ignored: duplicate, missing, or extra frames in source CSV")
                continue
        normalized, visible, missing = normalize_ball(
            read_csv_rows(path), frame_count, fps, homography, ball_shift, source_type=mode
        )
        mode_rows[mode] = normalized
        mode_quality[mode] = {
            "source_type": mode,
            "label": {
                "reference": "官方参考",
                "raw_prediction": "原始预测",
                "filtered_prediction": "优化预测",
            }[mode],
            "source_file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "ball_visible_frames": visible,
            "ball_detection_rate": visible / max(frame_count, 1),
            "ball_missing_segments": missing,
            "evaluation": evaluation,
        }
        write_csv_rows(video_dir / f"ball_{mode}.csv", list(normalized[0].keys()) if normalized else [], normalized)

    raw_f1 = (
        mode_quality.get("raw_prediction", {}).get("evaluation", {}).get("metrics", {}).get("f1_at_10px", {}).get("f1")
    )
    filtered_f1 = (
        mode_quality.get("filtered_prediction", {}).get("evaluation", {}).get("metrics", {}).get("f1_at_10px", {}).get("f1")
    )
    if filtered_f1 is not None:
        improved = raw_f1 is not None and filtered_f1 > raw_f1 and filtered_f1 > MIN_OPTIMIZED_F1_AT_10
        mode_quality["filtered_prediction"]["optimization_status"] = "improved" if improved else "experiment_only"
        if not improved:
            mode_quality["filtered_prediction"]["label"] = "过滤实验（未达标）"

    default_trajectory_mode = next(
        (mode for mode in ("reference", "filtered_prediction", "raw_prediction") if mode in mode_rows),
        None,
    )
    if default_trajectory_mode is None:
        fallback, visible, missing = normalize_ball(
            ball_rows_raw, frame_count, fps, homography, ball_shift, source_type="unclassified"
        )
        mode_rows["unclassified"] = fallback
        mode_quality["unclassified"] = {
            "source_type": "unclassified",
            "label": "未分类轨迹",
            "ball_visible_frames": visible,
            "ball_detection_rate": visible / max(frame_count, 1),
            "ball_missing_segments": missing,
            "evaluation": None,
        }
        default_trajectory_mode = "unclassified"
    ball_rows = mode_rows[default_trajectory_mode]
    visible_ball = mode_quality[default_trajectory_mode]["ball_visible_frames"]
    ball_missing = mode_quality[default_trajectory_mode]["ball_missing_segments"]
    players_rows = normalize_players(read_csv_rows(paths["players"]), frame_count, fps, homography)
    motion_rows = normalize_motion(read_csv_rows(paths["motion"]), frame_count, fps)
    coverage = player_coverage(players_rows, frame_count)

    write_csv_rows(video_dir / "ball.csv", list(ball_rows[0].keys()) if ball_rows else [], ball_rows)
    write_csv_rows(video_dir / "players.csv", list(players_rows[0].keys()) if players_rows else [], players_rows)
    write_csv_rows(video_dir / "motion.csv", list(motion_rows[0].keys()) if motion_rows else [], motion_rows)

    warnings = list(export_warnings)
    copied = {}
    for label in ("original", "overlay", "final"):
        path = paths[label]
        if path and path.exists():
            cached_video = next(
                (
                    candidate
                    for candidate in (video_dir / f"{label}.webm", video_dir / f"{label}.mp4")
                    if candidate.exists()
                    and candidate.stat().st_mtime >= path.stat().st_mtime
                    and (candidate.suffix.lower() == ".webm" or video_codec(candidate).lower() in {"h264", "avc1"})
                ),
                None,
            )
            if cached_video is not None:
                copied[label] = cached_video.name
                continue
            target = video_dir / f"{label}{path.suffix.lower()}"
            requested_target = target
            if label in {"original", "overlay", "final"}:
                try:
                    transcode_result = transcode_to_h264(path, target, overwrite=True)
                    target = Path(transcode_result["output"])
                    if target != requested_target and requested_target.exists():
                        requested_target.unlink()
                except Exception as exc:
                    shutil.copy2(path, target)
                    warnings.append(f"{label} browser transcode failed; copied source video: {exc}")
            else:
                shutil.copy2(path, target)
            copied[label] = target.name

    if not paths["players"].exists():
        warnings.append("players source csv missing; placeholder rows generated")
    if not paths["motion"].exists():
        warnings.append("motion source csv missing; placeholder rows generated")
    if "overlay" not in copied:
        warnings.append("overlay video missing")
    if "final" not in copied:
        warnings.append("final video missing; overlay remains available")
    if "original" not in copied:
        warnings.append("original input video missing; original mode disabled")

    original_meta = video_metadata(paths["original"]) if paths["original"] and paths["original"].exists() else None
    overlay_meta = video_metadata(paths["overlay"]) if paths["overlay"] and paths["overlay"].exists() else None
    analysis_resolution = ""
    if original_meta and original_meta.get("resolution"):
        analysis_resolution = original_meta["resolution"]
    elif overlay_meta and overlay_meta.get("resolution"):
        analysis_resolution = overlay_meta["resolution"]

    far_stats = stats.get("players", {}).get("far", {})
    near_stats = stats.get("players", {}).get("near", {})
    analysis_meta = {
        "video_id": video_id,
        "frames": frame_count,
        "fps": fps,
        "duration_s": frame_count / max(fps, 1e-6),
        "resolution": analysis_resolution,
        "ball_visible_rate": visible_ball / max(frame_count, 1),
        "near_visible_rate": coverage["near"],
        "far_visible_rate": coverage["far"],
        "detection_gaps": len(ball_missing),
        "near_distance_m": float(near_stats.get("total_distance_m") or 0.0),
        "far_distance_m": float(far_stats.get("total_distance_m") or 0.0),
        "max_speed_mps": max(float(near_stats.get("total_max_speed_mps") or 0.0), float(far_stats.get("total_max_speed_mps") or 0.0)),
    }

    analysis = {
        "video_id": video_id,
        "title": video_id,
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": frame_count / max(fps, 1e-6),
        "court_points_px": court_points,
        "court_size_m": court_size,
        "homography": homography.tolist() if homography is not None else None,
        "players": stats.get("players", {}),
        "analysis_meta": analysis_meta,
        "original_video_meta": original_meta,
        "uploaded_video_meta": uploaded_video_meta(),
        "default_trajectory_mode": default_trajectory_mode,
        "trajectory_modes": list(mode_rows),
        "trajectory_metadata": trajectory_metadata,
        "files": {
            "ball": "ball.csv",
            "players": "players.csv",
            "motion": "motion.csv",
            "quality": "quality.json",
            "original_video": copied.get("original"),
            "overlay_video": copied.get("overlay"),
            "final_video": copied.get("final"),
            "ball_modes": {mode: f"ball_{mode}.csv" for mode in mode_rows if mode != "unclassified"},
        },
    }
    quality = {
        "video_id": video_id,
        "frame_count": frame_count,
        "ball_visible_frames": visible_ball,
        "ball_detection_rate": visible_ball / max(frame_count, 1),
        "ball_missing_segments": ball_missing,
        "default_trajectory_mode": default_trajectory_mode,
        "trajectory_modes": mode_quality,
        "trajectory_metadata": trajectory_metadata,
        "player_coverage": coverage,
        "source_files": {name: str(path.relative_to(ROOT)) if path and path.exists() else None for name, path in paths.items()},
        "warnings": warnings,
    }

    write_json(video_dir / "analysis.json", analysis)
    write_json(video_dir / "quality.json", quality)
    return {
        "id": video_id,
        "title": video_id,
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": analysis["duration_s"],
        "analysis_meta": analysis_meta,
        "updated_at": datetime.fromtimestamp(source.get("source_mtime", 0)).isoformat(),
        "files": {
            "analysis": f"videos/{video_id}/analysis.json",
            "ball": f"videos/{video_id}/ball.csv",
            "players": f"videos/{video_id}/players.csv",
            "motion": f"videos/{video_id}/motion.csv",
            "quality": f"videos/{video_id}/quality.json",
            "original_video": f"videos/{video_id}/{copied['original']}" if "original" in copied else None,
            "overlay_video": f"videos/{video_id}/{copied['overlay']}" if "overlay" in copied else None,
            "final_video": f"videos/{video_id}/{copied['final']}" if "final" in copied else None,
            "ball_modes": {
                mode: f"videos/{video_id}/ball_{mode}.csv"
                for mode in mode_rows
                if mode != "unclassified"
            },
        },
        "quality": {
            "ball_detection_rate": quality["ball_detection_rate"],
            "default_trajectory_mode": default_trajectory_mode,
            "trajectory_modes": {
                mode: {
                    "label": payload["label"],
                    "evaluation": payload["evaluation"],
                    "ball_detection_rate": payload["ball_detection_rate"],
                }
                for mode, payload in mode_quality.items()
            },
            "near_player_coverage": coverage["near"],
            "far_player_coverage": coverage["far"],
            "warning_count": len(warnings),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Export normalized data for the D3 frontend dashboard.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--video-id", action="append", default=[], help="Export only the given video id. May be repeated.")
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    sources = discover_sources()
    if args.video_id:
        wanted = set(args.video_id)
        sources = {key: value for key, value in sources.items() if key in wanted}
    if not sources:
        raise SystemExit("No exportable output directories found under output/.")

    videos = []
    for source in sorted(sources.values(), key=lambda item: item.get("source_mtime", 0)):
        videos.append(export_one(source, data_root))
    default_video = max(videos, key=lambda item: item["updated_at"])["id"]
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "default_video": default_video,
        "uploaded_video_meta": uploaded_video_meta(),
        "videos": videos,
    }
    write_json(data_root / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
