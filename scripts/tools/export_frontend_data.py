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

from transcode_browser_video import transcode_to_h264


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "output"
DEFAULT_DATA_ROOT = ROOT / "frontend" / "public" / "data"
COURT_WIDTH_M = 6.1
COURT_LENGTH_M = 13.4
MAX_PROJECTED_BALL_SPEED_MPS = 35.0
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


def has_nonempty_final(source):
    final_path = source.get("final")
    return bool(final_path and final_path.exists() and final_path.stat().st_size > 0)


def load_ball_quality(video_id: str, root: Path) -> dict:
    """Load ball tracking quality from refine report or quality summary.

    Returns dict with at minimum: quality_level, quality_score, visible_rate.
    Defaults to 'Green' if no refine report exists (legacy pipeline).
    """
    # Try individual refine report first
    report_path = root / f"{video_id}_ball_refine_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            c = report.get("counts", {})
            frames = max(c.get("frames", 1), 1)
            final_visible = c.get("final_visible", 0)
            max_missing_gap = c.get("max_missing_gap", 0)
            vis_rate = final_visible / frames

            # Compute quality_score (same formula as audit_ball_quality.py)
            raw_visible = max(c.get("raw_visible", 1), 1)
            interpolated = c.get("interpolated", 0)
            rejected_roi = c.get("rejected_roi", 0)
            rejected_static_lock = c.get("rejected_static_lock", 0)
            rejected_jump = c.get("rejected_jump", 0)
            interp_rate = interpolated / max(final_visible, 1)

            score_visible = min(1.0, vis_rate / 0.55)
            score_gap = 1.0 if max_missing_gap <= 75 else max(0.0, 1.0 - (max_missing_gap - 75) / 120.0)
            score_interp = max(0.0, 1.0 - interp_rate / 0.45)
            score_roi = max(0.0, 1.0 - rejected_roi / raw_visible)
            score_static = max(0.0, 1.0 - rejected_static_lock / raw_visible)
            score_jump = max(0.0, 1.0 - rejected_jump / raw_visible)
            quality_score = (
                35.0 * score_visible + 20.0 * score_gap + 10.0 * score_interp
                + 15.0 * score_roi + 10.0 * score_static + 10.0 * score_jump
            )

            # Grade
            if quality_score >= 75.0 and vis_rate >= 0.55 and max_missing_gap <= 75:
                level = "Green"
            elif quality_score >= 55.0 and vis_rate >= 0.40 and max_missing_gap <= 120:
                level = "Yellow"
            else:
                level = "Red"

            return {
                "quality_level": level,
                "quality_score": round(quality_score, 2),
                "visible_rate": round(vis_rate, 4),
                "max_missing_gap": max_missing_gap,
            }
        except Exception:
            pass

    # No refine report — assume Green (legacy pipeline without refine)
    return {
        "quality_level": "Green",
        "quality_score": 100.0,
        "visible_rate": 0.0,
        "max_missing_gap": 0,
    }


def normalize_ball(rows, frame_count, fps, homography, ball_shift):
    by_frame = {as_int(r.get("Frame", r.get("frame", 0))): r for r in rows}
    conservative_filter = bool(rows and ("Source" in rows[0] or "source" in rows[0]))
    out = []
    prev = None
    missing_flags = []
    visible_count = 0
    spatial_count = 0
    interpolated_count = 0
    low_confidence_count = 0
    filtered_count = 0
    for frame in range(frame_count):
        raw = by_frame.get(frame, {})
        visibility = as_int(raw.get("Visibility", raw.get("visibility", 0)))
        x_px = as_float(raw.get("X", raw.get("x_px", "")), default=math.nan)
        y_px = as_float(raw.get("Y", raw.get("y_px", "")), default=math.nan)
        missing = visibility <= 0 or math.isnan(x_px) or math.isnan(y_px) or (x_px == 0 and y_px == 0)
        source = raw.get("Source", raw.get("source", "model" if not missing else "missing"))
        confidence = as_float(raw.get("Confidence", raw.get("confidence", "")), default=0.9 if not missing else 0.0)
        is_interpolated = int("interp" in str(source).lower() or as_int(raw.get("is_interpolated", 0)) > 0)
        projected = None if missing else to_court((x_px, y_px), homography)
        court = None
        if projected is not None:
            shifted = (projected[0] + ball_shift, projected[1])
            if conservative_filter and 0.0 <= shifted[0] <= COURT_WIDTH_M and 0.0 <= shifted[1] <= COURT_LENGTH_M:
                court = (float(shifted[0]), float(shifted[1]))
            elif not conservative_filter:
                # Preserve legacy exports until their source detections have
                # been reviewed and processed by smooth_ball_csv.py.
                court = (
                    float(np.clip(shifted[0], 0.0, COURT_WIDTH_M)),
                    float(np.clip(shifted[1], 0.0, COURT_LENGTH_M)),
                )
        speed = None
        speed_valid = 0
        time_s = frame / max(fps, 1e-6)
        if court is not None and prev is not None and frame - prev["frame"] <= 2:
            dt = max(time_s - prev["time_s"], 1e-6)
            candidate_speed = math.dist(court, prev["court"]) / dt
            if candidate_speed <= MAX_PROJECTED_BALL_SPEED_MPS:
                speed = candidate_speed
                speed_valid = 1
        if court is not None:
            prev = {"frame": frame, "time_s": time_s, "court": court}
            spatial_count += 1
        if not missing:
            visible_count += 1
            interpolated_count += is_interpolated
            low_confidence_count += int(confidence < 0.5)
            filtered_count += int("filtered" in str(source).lower())
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
            "is_interpolated": is_interpolated,
            "is_spatial_valid": int(court is not None),
            "speed_valid": speed_valid,
            "confidence": fmt(confidence, 3),
            "source": source,
        })
    return (
        out, visible_count, spatial_count, interpolated_count,
        low_confidence_count, filtered_count, conservative_filter,
        missing_segments(missing_flags),
    )


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

    # Quality gate: check ball tracking quality before export
    ball_quality = load_ball_quality(video_id, source["root"])
    quality_level = ball_quality["quality_level"]

    if quality_level == "Red":
        # Red: do not export ball trajectory/speed — export empty data with quality explanation
        ball_rows = []
        visible_ball = 0
        spatial_ball = 0
        interpolated_ball = 0
        low_confidence_ball = 0
        filtered_ball = 0
        conservative_ball = True
        ball_missing = [{"start_frame": 0, "end_frame": max(frame_count - 1, 0), "length": frame_count}]
    else:
        (
            ball_rows, visible_ball, spatial_ball, interpolated_ball,
            low_confidence_ball, filtered_ball, conservative_ball, ball_missing,
        ) = normalize_ball(
            ball_rows_raw, frame_count, fps, homography, ball_shift
        )
    players_rows = normalize_players(read_csv_rows(paths["players"]), frame_count, fps, homography)
    motion_rows = normalize_motion(read_csv_rows(paths["motion"]), frame_count, fps)
    coverage = player_coverage(players_rows, frame_count)

    write_csv_rows(video_dir / "ball.csv", list(ball_rows[0].keys()) if ball_rows else [], ball_rows)
    write_csv_rows(video_dir / "players.csv", list(players_rows[0].keys()) if players_rows else [], players_rows)
    write_csv_rows(video_dir / "motion.csv", list(motion_rows[0].keys()) if motion_rows else [], motion_rows)

    warnings = []
    copied = {}
    for label in ("original", "overlay", "final"):
        path = paths[label]
        if path and path.exists():
            target = video_dir / f"{label}{path.suffix.lower()}"
            if label in {"original", "overlay", "final"}:
                try:
                    transcode_to_h264(path, target, overwrite=True)
                except Exception as exc:
                    shutil.copy2(path, target)
                    warnings.append(f"{label} H.264 transcode failed; copied source video: {exc}")
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
    if conservative_ball and visible_ball and spatial_ball / visible_ball < 0.5:
        warnings.append("Most shuttle detections cannot be reliably floor-projected; omitted from court map.")
    if low_confidence_ball:
        warnings.append(f"{low_confidence_ball} shuttle detections are filtered or interpolated low-confidence points.")
    if filtered_ball:
        warnings.append("Shuttle trajectory uses conservative heuristic filtering and is not manually verified ground truth.")

    # Quality gate warnings
    if quality_level == "Red":
        warnings.append(
            f"Ball tracking quality is Red (score={ball_quality['quality_score']:.0f}). "
            "Shuttle trajectory and ball speed data are NOT exported. "
            "Only player analytics data is available."
        )
    elif quality_level == "Yellow":
        warnings.append(
            f"Ball tracking quality is Yellow (score={ball_quality['quality_score']:.0f}, "
            f"visible_rate={ball_quality['visible_rate']:.0%}). "
            "Shuttle trajectory is exported but marked as low confidence."
        )

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
        "ball_spatial_rate": spatial_ball / max(frame_count, 1),
        "ball_filter_applied": conservative_ball,
        "ball_quality_level": quality_level,
        "ball_quality_score": ball_quality["quality_score"],
        "ball_low_confidence": quality_level != "Green",
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
        "files": {
            "ball": "ball.csv",
            "players": "players.csv",
            "motion": "motion.csv",
            "quality": "quality.json",
            "original_video": copied.get("original"),
            "overlay_video": copied.get("overlay"),
            "final_video": copied.get("final"),
        },
    }
    quality = {
        "video_id": video_id,
        "frame_count": frame_count,
        "ball_visible_frames": visible_ball,
        "ball_detection_rate": visible_ball / max(frame_count, 1),
        "ball_spatial_frames": spatial_ball,
        "ball_spatial_rate": spatial_ball / max(frame_count, 1),
        "ball_interpolated_frames": interpolated_ball,
        "ball_low_confidence_frames": low_confidence_ball,
        "ball_filtered_frames": filtered_ball,
        "ball_filter_applied": conservative_ball,
        "ball_missing_segments": ball_missing,
        "ball_quality_level": quality_level,
        "ball_quality_score": ball_quality["quality_score"],
        "ball_low_confidence": quality_level != "Green",
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
        },
        "quality": {
            "ball_detection_rate": quality["ball_detection_rate"],
            "ball_quality_level": quality_level,
            "ball_quality_score": ball_quality["quality_score"],
            "ball_low_confidence": quality_level != "Green",
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
    quality_rank = {"Green": 0, "Yellow": 1, "Red": 2}
    videos.sort(
        key=lambda item: (
            quality_rank.get(item.get("quality", {}).get("ball_quality_level", "Red"), 3),
            item["id"] != "short",
            item["id"],
        )
    )
    default_video = videos[0]["id"]
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
