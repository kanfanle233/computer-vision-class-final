#!/usr/bin/env python3
"""Enhanced shuttlecock trajectory refinement.

This module provides an improved post-processing path (--refine-ball) that
replaces the conservative --filter-ball filter.  It adds jump rejection,
per-segment constant-velocity Kalman smoothing, and relaxed gap interpolation,
all without introducing new dependencies beyond numpy/cv2.

Source values in output CSV:
  model / refined / interp / rejected_roi / rejected_jump /
  rejected_static_motion / rejected_static_lock / missing
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np

# Reuse utilities from the existing conservative filter (no modification needed).
from smooth_ball_csv import (
    as_int,
    frame_motion_scores,
    parse_court_points,
    read_rows,
    static_locked_frames,
    visible,
)

# ---------------------------------------------------------------------------
# Jump rejection
# ---------------------------------------------------------------------------

def reject_jump_points(
    accepted: dict[int, tuple[int, int]],
    max_step_px: float = 180.0,
    max_dir_change_deg: float = 160.0,
) -> tuple[set[int], list[dict]]:
    """Reject points where per-gap speed or direction reversal is implausible.

    Args:
        accepted: {frame: (x, y)} for currently accepted visible frames.
        max_step_px: Maximum allowed pixel displacement *per frame gap*.
        max_dir_change_deg: Maximum allowed direction change (degrees).

    Returns:
        rejected: set of frame indices flagged as jumps.
        examples: up to 5 example dicts for the report.
    """
    frames = sorted(accepted)
    rejected: set[int] = set()
    examples: list[dict] = []

    if len(frames) < 3:
        return rejected, examples

    # Build per-gap step and direction vectors.
    for i in range(1, len(frames) - 1):
        f_prev, f_curr, f_next = frames[i - 1], frames[i], frames[i + 1]
        gap_prev = f_curr - f_prev
        gap_next = f_next - f_curr
        if gap_prev <= 0 or gap_next <= 0:
            continue

        p_prev = np.array(accepted[f_prev], dtype=np.float64)
        p_curr = np.array(accepted[f_curr], dtype=np.float64)
        p_next = np.array(accepted[f_next], dtype=np.float64)

        step_prev = np.linalg.norm(p_curr - p_prev) / gap_prev
        step_next = np.linalg.norm(p_next - p_curr) / gap_next

        # Speed check (per-gap normalised).
        if step_prev > max_step_px or step_next > max_step_px:
            rejected.add(f_curr)
            examples.append({
                "frame": f_curr,
                "speed_px_per_gap_prev": round(step_prev, 1),
                "speed_px_per_gap_next": round(step_next, 1),
            })
            continue

        # Direction-change check.
        v1 = p_curr - p_prev
        v2 = p_next - p_curr
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 > 1e-6 and n2 > 1e-6:
            cosang = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
            angle = math.degrees(math.acos(cosang))
            if angle > max_dir_change_deg:
                rejected.add(f_curr)
                examples.append({
                    "frame": f_curr,
                    "dir_change_deg": round(angle, 1),
                    "speed_px_per_gap_prev": round(step_prev, 1),
                    "speed_px_per_gap_next": round(step_next, 1),
                })

    return rejected, examples[:5]


# ---------------------------------------------------------------------------
# Per-segment constant-velocity Kalman smoothing
# ---------------------------------------------------------------------------

def constant_velocity_smooth(
    accepted: dict[int, tuple[int, int]],
    segments: list[list[int]],
    sigma_q: float = 8.0,
    sigma_r: float = 4.0,
) -> dict[int, tuple[int, int]]:
    """Apply a constant-velocity Kalman filter *within* each continuous segment.

    Only adjusts trusted visible points — does NOT extrapolate into gaps.

    Args:
        accepted: {frame: (x, y)} of accepted (post-jump-reject) visible frames.
        segments: list of continuous frame-index lists (e.g. [[0,1,2],[10,11,12]]).
        sigma_q: process noise std.
        sigma_r: measurement noise std.

    Returns:
        smoothed: {frame: (x, y)} with updated coordinates for segment frames.
    """
    if not segments:
        return dict(accepted)

    # 4-state Kalman: [x, y, vx, vy].
    # State transition: x_{k+1} = x_k + vx_k, etc. (dt=1 assumed).
    F = np.array([
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ], dtype=np.float64)
    H = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
    ], dtype=np.float64)
    Q = sigma_q ** 2 * np.eye(4)
    R = sigma_r ** 2 * np.eye(2)

    smoothed: dict[int, tuple[int, int]] = {}

    for seg in segments:
        if len(seg) < 2:
            f = seg[0]
            smoothed[f] = accepted[f]
            continue

        # Initialise state from first measurement.
        x0, y0 = accepted[seg[0]]
        state = np.array([x0, y0, 0.0, 0.0], dtype=np.float64)
        P = np.eye(4) * 100.0  # large initial uncertainty

        for f in seg:
            meas = np.array(accepted[f], dtype=np.float64)

            # Predict.
            state = F @ state
            P = F @ P @ F.T + Q

            # Update.
            y_innov = meas - H @ state
            S = H @ P @ H.T + R
            K = P @ H.T @ np.linalg.inv(S)
            state = state + K @ y_innov
            P = (np.eye(4) - K @ H) @ P

            smoothed[f] = (int(round(state[0])), int(round(state[1])))

    return smoothed


# ---------------------------------------------------------------------------
# Gap interpolation
# ---------------------------------------------------------------------------

def interpolate_gaps(
    accepted: dict[int, tuple[int, int]],
    max_gap: int = 6,
    max_step_px: float = 180.0,
    court_poly: np.ndarray | None = None,
    flight_roi: np.ndarray | None = None,
) -> tuple[dict[int, tuple[int, int]], list[dict]]:
    """Fill short holes between consecutive visible points.

    Constraints:
      - distance / gap <= max_step_px  (speed sanity)
      - interpolated point must fall inside flight_roi (if provided)
      - endpoints are accepted points (i.e. model/refined, not already interp)

    Returns:
        interpolated: {frame: (x, y)}
        examples: up to 5 example dicts for the report.
    """
    frames = sorted(accepted)
    interpolated: dict[int, tuple[int, int]] = {}
    examples: list[dict] = []

    for first, second in zip(frames, frames[1:]):
        gap = second - first - 1
        if gap <= 0 or gap > max_gap:
            continue
        distance = math.dist(accepted[first], accepted[second])
        step = distance / (gap + 1)
        if step > max_step_px:
            continue

        all_ok = True
        filled = {}
        for offset in range(1, gap + 1):
            alpha = offset / (gap + 1)
            x = round(accepted[first][0] * (1 - alpha) + accepted[second][0] * alpha)
            y = round(accepted[first][1] * (1 - alpha) + accepted[second][1] * alpha)
            if flight_roi is not None:
                if cv2.pointPolygonTest(flight_roi, (float(x), float(y)), False) < 0:
                    all_ok = False
                    break
            filled[first + offset] = (x, y)

        if all_ok:
            interpolated.update(filled)
            if len(examples) < 5:
                examples.append({
                    "frame_from": first,
                    "frame_to": second,
                    "gap": gap,
                })

    return interpolated, examples


# ---------------------------------------------------------------------------
# Continuous-segment splitting
# ---------------------------------------------------------------------------

def split_segments(frames_sorted: list[int]) -> list[list[int]]:
    """Split a sorted frame list into continuous (gap=1) segments."""
    if not frames_sorted:
        return []
    segments: list[list[int]] = [[frames_sorted[0]]]
    for f in frames_sorted[1:]:
        if f == segments[-1][-1] + 1:
            segments[-1].append(f)
        else:
            segments.append([f])
    return segments


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def write_ball_csv(
    path: Path,
    all_rows: list[dict],
) -> None:
    """Write the refined ball CSV with Frame, Visibility, X, Y, Source, Confidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Frame", "Visibility", "X", "Y", "Source", "Confidence"],
        )
        writer.writeheader()
        writer.writerows(all_rows)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_refine(
    input_csv: Path,
    output_csv: Path,
    video: Path | None,
    court_points: str,
    max_gap: int = 6,
    max_step_px: float = 180.0,
    top_pad_px: float = 160.0,
    side_pad_px: float = 80.0,
    bottom_pad_px: float = 20.0,
    patch_radius_px: int = 7,
    min_motion_score: float = 0.0,
    static_run_frames: int = 8,
    static_radius_px: float = 4.0,
    max_dir_change_deg: float = 160.0,
    sigma_q: float = 8.0,
    sigma_r: float = 4.0,
    inpaintnet_enabled: bool = False,
    inpaintnet_path: str = "",
    report_json: Path | None = None,
) -> dict:
    """Run the full refine pipeline and return a report dict."""
    rows = read_rows(input_csv)
    quad = parse_court_points(court_points)

    # Flight ROI polygon (padded court bounding box).
    flight_roi = np.array(
        [
            [quad[0][0] - side_pad_px, quad[0][1] - top_pad_px],
            [quad[1][0] + side_pad_px, quad[1][1] - top_pad_px],
            [quad[2][0] + side_pad_px, quad[2][1] + bottom_pad_px],
            [quad[3][0] - side_pad_px, quad[3][1] + bottom_pad_px],
        ],
        dtype=np.float32,
    )

    # --- 1. Read raw visible points ---
    raw_visible: dict[int, tuple[int, int]] = {}
    for row in rows:
        frame = as_int(row.get("Frame", row.get("frame", 0)))
        if visible(row):
            x = as_int(row.get("X", row.get("x_px", 0)))
            y = as_int(row.get("Y", row.get("y_px", 0)))
            raw_visible[frame] = (x, y)

    # --- 2. ROI filter ---
    in_roi: dict[int, tuple[int, int]] = {}
    rejected_roi_frames: set[int] = set()
    for frame, point in raw_visible.items():
        if cv2.pointPolygonTest(flight_roi, (float(point[0]), float(point[1])), False) >= 0:
            in_roi[frame] = point
        else:
            rejected_roi_frames.add(frame)

    # --- 3. Static-lock & motion-score filter ---
    motion_scores: dict[int, float] = {}
    if video:
        motion_scores = frame_motion_scores(video, in_roi, patch_radius_px)

    motion_rejected: set[int] = {
        frame for frame in in_roi
        if video and (frame not in motion_scores or motion_scores[frame] < min_motion_score)
    }
    after_motion = {f: p for f, p in in_roi.items() if f not in motion_rejected}

    locked_rejected = static_locked_frames(after_motion, static_run_frames, static_radius_px)
    after_static = {f: p for f, p in after_motion.items() if f not in locked_rejected}

    # --- 4. Jump rejection ---
    jump_rejected, jump_examples = reject_jump_points(
        after_static, max_step_px=max_step_px, max_dir_change_deg=max_dir_change_deg,
    )
    accepted = {f: p for f, p in after_static.items() if f not in jump_rejected}

    # --- 5. Per-segment Kalman smoothing ---
    segments = split_segments(sorted(accepted))
    smoothed = constant_velocity_smooth(accepted, segments, sigma_q=sigma_q, sigma_r=sigma_r)

    # --- 6. Gap interpolation ---
    interpolated, interp_examples = interpolate_gaps(
        smoothed, max_gap=max_gap, max_step_px=max_step_px, flight_roi=flight_roi,
    )

    # --- 7. Compute max missing gap ---
    all_visible_frames = sorted(set(smoothed.keys()) | set(interpolated.keys()))
    max_missing_gap = 0
    total_frames = len(rows)
    if all_visible_frames:
        prev = all_visible_frames[0] - 1
        for f in all_visible_frames:
            gap = f - prev - 1
            if gap > max_missing_gap:
                max_missing_gap = gap
            prev = f
        # Also check gap after last visible frame to end
        if rows:
            last_frame = as_int(rows[-1].get("Frame", rows[-1].get("frame", 0)))
            trailing = last_frame - all_visible_frames[-1]
            if trailing > max_missing_gap:
                max_missing_gap = trailing
    elif total_frames > 0:
        # No visible ball at all — entire video is one continuous gap.
        max_missing_gap = total_frames

    # --- 8. Build output rows ---
    output: list[dict] = []
    for row in rows:
        frame = as_int(row.get("Frame", row.get("frame", 0)))
        entry: dict = {
            "Frame": frame,
            "Visibility": 0,
            "X": 0,
            "Y": 0,
            "Source": "missing",
            "Confidence": "0.000",
        }

        if frame in smoothed:
            x, y = smoothed[frame]
            score = motion_scores.get(frame)
            confidence = 0.60 if score is None else min(0.80, 0.40 + score / 80.0)
            entry.update({
                "Visibility": 1,
                "X": x,
                "Y": y,
                "Source": "refined",
                "Confidence": f"{confidence:.3f}",
            })
        elif frame in interpolated:
            x, y = interpolated[frame]
            entry.update({
                "Visibility": 1,
                "X": x,
                "Y": y,
                "Source": "interp",
                "Confidence": "0.250",
            })
        elif frame in raw_visible and frame in rejected_roi_frames:
            entry["Source"] = "rejected_roi"
        elif frame in motion_rejected:
            entry["Source"] = "rejected_static_motion"
        elif frame in locked_rejected:
            entry["Source"] = "rejected_static_lock"
        elif frame in jump_rejected:
            entry["Source"] = "rejected_jump"

        output.append(entry)

    # --- 9. Write output ---
    write_ball_csv(output_csv, output)

    # --- 10. Report ---
    report = {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "inpaintnet_enabled": inpaintnet_enabled,
        "inpaintnet_path": inpaintnet_path,
        "parameters": {
            "court_points": quad.tolist(),
            "flight_roi": flight_roi.tolist(),
            "top_pad_px": top_pad_px,
            "side_pad_px": side_pad_px,
            "bottom_pad_px": bottom_pad_px,
            "min_motion_score": min_motion_score,
            "static_run_frames": static_run_frames,
            "static_radius_px": static_radius_px,
            "max_step_px": max_step_px,
            "max_dir_change_deg": max_dir_change_deg,
            "max_gap": max_gap,
            "sigma_q": sigma_q,
            "sigma_r": sigma_r,
        },
        "counts": {
            "frames": len(rows),
            "raw_visible": len(raw_visible),
            "in_roi": len(in_roi),
            "rejected_roi": len(rejected_roi_frames),
            "rejected_static_motion": len(motion_rejected),
            "rejected_static_lock": len(locked_rejected),
            "rejected_jump": len(jump_rejected),
            "retained_model": len(accepted),
            "smoothed": len(smoothed),
            "interpolated": len(interpolated),
            "final_visible": len(smoothed) + len(interpolated),
            "max_missing_gap": max_missing_gap,
        },
        "examples": {
            "rejected_jump": jump_examples,
            "interpolated": interp_examples,
        },
        "warning": (
            "Refined points use conservative Kalman smoothing and short-gap interpolation. "
            "Long gaps remain un-filled.  Points with Source=interp are not model predictions."
        ),
    }

    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enhanced shuttlecock trajectory refinement (replaces --filter-ball)."
    )
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--video", type=Path, default=None)
    parser.add_argument("--court-points", required=True, help="TL,TR,BR,BL image coords.")
    parser.add_argument("--max-gap", type=int, default=6, help="Max interpolation gap (frames).")
    parser.add_argument("--max-step-px", type=float, default=180.0, help="Max per-frame step px.")
    parser.add_argument("--max-dir-change-deg", type=float, default=160.0)
    parser.add_argument("--top-pad-px", type=float, default=160.0)
    parser.add_argument("--side-pad-px", type=float, default=80.0)
    parser.add_argument("--bottom-pad-px", type=float, default=20.0)
    parser.add_argument("--patch-radius-px", type=int, default=7)
    parser.add_argument(
        "--min-motion-score",
        type=float,
        default=0.0,
        help="Optional local-motion gate. Default 0.0 keeps refine conservative and lets static-lock/jump filters do the cleanup.",
    )
    parser.add_argument("--static-run-frames", type=int, default=8)
    parser.add_argument("--static-radius-px", type=float, default=4.0)
    parser.add_argument("--sigma-q", type=float, default=8.0, help="Kalman process noise std.")
    parser.add_argument("--sigma-r", type=float, default=4.0, help="Kalman measurement noise std.")
    parser.add_argument("--inpaintnet-enabled", action="store_true",
                         help="Set in report if InpaintNet was used upstream.")
    parser.add_argument("--inpaintnet-path", type=str, default="",
                         help="InpaintNet weight path for report metadata.")
    parser.add_argument("--report-json", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_refine(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        video=args.video,
        court_points=args.court_points,
        max_gap=max(0, args.max_gap),
        max_step_px=args.max_step_px,
        top_pad_px=args.top_pad_px,
        side_pad_px=args.side_pad_px,
        bottom_pad_px=args.bottom_pad_px,
        patch_radius_px=args.patch_radius_px,
        min_motion_score=args.min_motion_score,
        static_run_frames=args.static_run_frames,
        static_radius_px=args.static_radius_px,
        max_dir_change_deg=args.max_dir_change_deg,
        sigma_q=args.sigma_q,
        sigma_r=args.sigma_r,
        inpaintnet_enabled=args.inpaintnet_enabled,
        inpaintnet_path=args.inpaintnet_path,
        report_json=args.report_json,
    )


if __name__ == "__main__":
    main()
