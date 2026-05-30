#!/usr/bin/env python3
"""Conservatively clean shuttle detections before dashboard export.

This is intentionally a filter rather than a truth generator.  It removes
obvious detections outside the playable flight region and static background
locks, then fills only very short gaps between plausible neighbours.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_court_points(value):
    values = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(values) != 8:
        raise ValueError("--court-points must contain TL,TR,BR,BL as 8 comma-separated numbers")
    return np.array(values, dtype=np.float32).reshape(4, 2)


def visible(row):
    return as_int(row.get("Visibility", row.get("visibility", 0))) > 0


def read_rows(path):
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        return list(csv.DictReader(handle))


def frame_motion_scores(video_path, candidates, patch_radius):
    if not video_path:
        return {}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for shuttle filtering: {video_path}")
    scores = {}
    previous = None
    frame = 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        point = candidates.get(frame)
        if point is not None and previous is not None:
            x, y = point
            x1, x2 = max(0, x - patch_radius), min(gray.shape[1], x + patch_radius + 1)
            y1, y2 = max(0, y - patch_radius), min(gray.shape[0], y + patch_radius + 1)
            if x2 > x1 and y2 > y1:
                scores[frame] = float(cv2.absdiff(gray[y1:y2, x1:x2], previous[y1:y2, x1:x2]).mean())
        previous = gray
        frame += 1
    cap.release()
    return scores


def static_locked_frames(points, minimum_frames, radius_px):
    """Mark stationary runs such as a logo or scoreboard mistaken for a shuttle."""
    rejected = set()
    ordered = sorted(points)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end] == ordered[end - 1] + 1:
            end += 1
        run = ordered[start:end]
        for window_start in range(0, max(0, len(run) - minimum_frames + 1)):
            window = run[window_start:window_start + minimum_frames]
            coords = np.array([points[frame] for frame in window], dtype=np.float32)
            extent = np.ptp(coords, axis=0)
            if float(np.hypot(extent[0], extent[1])) <= radius_px:
                rejected.update(window)
        start = end
    return rejected


def build_parser():
    parser = argparse.ArgumentParser(description="Filter unreliable TrackNet shuttle points without fabricating long tracks.")
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--video", type=Path, default=None, help="Source video used for local-motion rejection.")
    parser.add_argument("--court-points", required=True, help="TL,TR,BR,BL image coordinates.")
    parser.add_argument("--top-pad-px", type=float, default=160.0, help="Air-space allowance above far baseline.")
    parser.add_argument("--side-pad-px", type=float, default=80.0)
    parser.add_argument("--bottom-pad-px", type=float, default=20.0)
    parser.add_argument("--patch-radius-px", type=int, default=7)
    parser.add_argument("--min-motion-score", type=float, default=4.0)
    parser.add_argument("--static-run-frames", type=int, default=8)
    parser.add_argument("--static-radius-px", type=float, default=4.0)
    parser.add_argument("--max-interp-gap", type=int, default=2)
    parser.add_argument("--max-interp-step-px", type=float, default=70.0)
    parser.add_argument("--report-json", type=Path, default=None)
    return parser


def main():
    args = build_parser().parse_args()
    rows = read_rows(args.input_csv)
    quad = parse_court_points(args.court_points)
    flight_roi = np.array(
        [
            [quad[0][0] - args.side_pad_px, quad[0][1] - args.top_pad_px],
            [quad[1][0] + args.side_pad_px, quad[1][1] - args.top_pad_px],
            [quad[2][0] + args.side_pad_px, quad[2][1] + args.bottom_pad_px],
            [quad[3][0] - args.side_pad_px, quad[3][1] + args.bottom_pad_px],
        ],
        dtype=np.float32,
    )

    raw_visible = {}
    for row in rows:
        frame = as_int(row.get("Frame", row.get("frame", 0)))
        if visible(row):
            raw_visible[frame] = (as_int(row.get("X", row.get("x_px", 0))), as_int(row.get("Y", row.get("y_px", 0))))

    in_roi = {
        frame: point
        for frame, point in raw_visible.items()
        if cv2.pointPolygonTest(flight_roi, (float(point[0]), float(point[1])), False) >= 0
    }
    motion_scores = frame_motion_scores(args.video, in_roi, args.patch_radius_px)
    motion_rejected = {
        frame for frame in in_roi
        if args.video and (frame not in motion_scores or motion_scores[frame] < args.min_motion_score)
    }
    after_motion = {frame: point for frame, point in in_roi.items() if frame not in motion_rejected}
    locked_rejected = static_locked_frames(after_motion, args.static_run_frames, args.static_radius_px)
    accepted = {frame: point for frame, point in after_motion.items() if frame not in locked_rejected}

    interpolated = {}
    accepted_frames = sorted(accepted)
    for first, second in zip(accepted_frames, accepted_frames[1:]):
        gap = second - first - 1
        if gap <= 0 or gap > args.max_interp_gap:
            continue
        distance = math.dist(accepted[first], accepted[second])
        if distance / (gap + 1) > args.max_interp_step_px:
            continue
        for offset in range(1, gap + 1):
            alpha = offset / (gap + 1)
            x = round(accepted[first][0] * (1 - alpha) + accepted[second][0] * alpha)
            y = round(accepted[first][1] * (1 - alpha) + accepted[second][1] * alpha)
            interpolated[first + offset] = (x, y)

    output = []
    for row in rows:
        frame = as_int(row.get("Frame", row.get("frame", 0)))
        result = {"Frame": frame, "Visibility": 0, "X": 0, "Y": 0, "Source": "missing", "Confidence": "0.000"}
        if frame in accepted:
            x, y = accepted[frame]
            score = motion_scores.get(frame)
            # This is a heuristic screen, not a calibrated detector score:
            # never present retained fallback points as high-confidence truth.
            confidence = 0.55 if score is None else min(0.70, 0.35 + score / 100.0)
            result.update({"Visibility": 1, "X": x, "Y": y, "Source": "filtered_model", "Confidence": f"{confidence:.3f}"})
        elif frame in interpolated:
            x, y = interpolated[frame]
            result.update({"Visibility": 1, "X": x, "Y": y, "Source": "interp", "Confidence": "0.250"})
        elif frame in raw_visible and frame not in in_roi:
            result["Source"] = "rejected_roi"
        elif frame in motion_rejected:
            result["Source"] = "rejected_static_motion"
        elif frame in locked_rejected:
            result["Source"] = "rejected_static_lock"
        output.append(result)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Frame", "Visibility", "X", "Y", "Source", "Confidence"])
        writer.writeheader()
        writer.writerows(output)

    report = {
        "input_csv": str(args.input_csv),
        "output_csv": str(args.output_csv),
        "parameters": {
            "court_points": quad.tolist(),
            "flight_roi": flight_roi.tolist(),
            "top_pad_px": args.top_pad_px,
            "side_pad_px": args.side_pad_px,
            "bottom_pad_px": args.bottom_pad_px,
            "min_motion_score": args.min_motion_score,
            "static_run_frames": args.static_run_frames,
            "static_radius_px": args.static_radius_px,
            "max_interp_gap": args.max_interp_gap,
            "max_interp_step_px": args.max_interp_step_px,
        },
        "counts": {
            "frames": len(rows),
            "raw_visible": len(raw_visible),
            "in_flight_roi": len(in_roi),
            "rejected_roi": len(raw_visible) - len(in_roi),
            "rejected_static_motion": len(motion_rejected),
            "rejected_static_lock": len(locked_rejected),
            "retained_model": len(accepted),
            "interpolated": len(interpolated),
            "final_visible": len(accepted) + len(interpolated),
        },
        "warning": "Filtered points are conservative detections, not manually verified shuttle ground truth.",
    }
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
