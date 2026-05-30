#!/usr/bin/env python3
"""Create a masked copy of input video for TrackNet inference only.

Masks out broadcast overlay regions (scoreboard, logo, corner bugs)
so TrackNet is less likely to lock onto static non-ball elements.
The original video is never modified — overlay/final video still uses the source.

Usage:
    python scripts/tools/mask_tracknet_input.py \
        --input-video inputs/short.mp4 \
        --output-video /tmp/short_masked.mp4 \
        --preset top_right_scoreboard \
        --fill black \
        --report-json /tmp/short_mask_report.json \
        --debug-video  # optional: draw colored rectangles on output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Presets: each is a list of (x_frac, y_frac, w_frac, h_frac) normalized to [0,1].
# Coordinates are top-left origin, fractions of frame width/height.
# ---------------------------------------------------------------------------

PRESETS: dict[str, list[tuple[float, float, float, float]]] = {
    "none": [],
    "top_bar": [
        # Top 15% of frame — catches logos, channel bugs, top-center scoreboards
        (0.0, 0.0, 1.0, 0.15),
    ],
    "top_right_scoreboard": [
        # Top-right quadrant — catches broadcast scoreboard overlays
        (0.65, 0.0, 0.35, 0.25),
    ],
    "top_right_and_bottom_bar": [
        # Top-right scoreboard + bottom ticker bar
        (0.65, 0.0, 0.35, 0.25),
        (0.0, 0.88, 1.0, 0.12),
    ],
    "broadcast_overlays": [
        # Combined: top-right scoreboard + top bar + bottom bar
        (0.65, 0.0, 0.35, 0.25),
        (0.0, 0.0, 1.0, 0.06),
        (0.0, 0.90, 1.0, 0.10),
    ],
}


def get_rects(preset: str, custom_json_path: str | None, width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Convert preset or custom JSON to absolute pixel rectangles."""
    if preset == "custom_json":
        if not custom_json_path:
            raise ValueError("--mask-json required when preset=custom_json")
        with open(custom_json_path, "r") as f:
            raw_rects = json.load(f)
        # Expected format: list of [x, y, w, h] in absolute pixels or {x_frac, y_frac, w_frac, h_frac}
        rects = []
        for r in raw_rects:
            if isinstance(r, dict):
                x = int(r.get("x_frac", 0) * width)
                y = int(r.get("y_frac", 0) * height)
                w = int(r.get("w_frac", 1) * width)
                h = int(r.get("h_frac", 1) * height)
            else:
                x, y, w, h = int(r[0]), int(r[1]), int(r[2]), int(r[3])
            rects.append((x, y, w, h))
        return rects

    frac_rects = PRESETS.get(preset, [])
    return [
        (int(x * width), int(y * height), int(w * width), int(h * height))
        for x, y, w, h in frac_rects
    ]


def fill_rect(frame: np.ndarray, x: int, y: int, w: int, h: int, mode: str) -> None:
    """Fill a rectangle region in-place."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x0 >= x1 or y0 >= y1:
        return

    if mode == "black":
        frame[y0:y1, x0:x1] = 0

    elif mode == "blur":
        region = frame[y0:y1, x0:x1].copy()
        ksize = max(3, (min(w, h) // 4) | 1)  # odd kernel, at least 3
        ksize = min(ksize, 51)
        blurred = cv2.GaussianBlur(region, (ksize, ksize), 0)
        frame[y0:y1, x0:x1] = blurred

    elif mode == "median":
        region = frame[y0:y1, x0:x1].copy()
        ksize = max(3, (min(w, h) // 4) | 1)
        ksize = min(ksize, 51)
        med = cv2.medianBlur(region, ksize)
        frame[y0:y1, x0:x1] = med

    else:
        frame[y0:y1, x0:x1] = 0


def draw_debug_rects(frame: np.ndarray, rects: list[tuple[int, int, int, int]]) -> None:
    """Draw semi-transparent colored rectangles for debug visualization."""
    colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 0, 255)]
    overlay = frame.copy()
    for i, (x, y, w, h) in enumerate(rects):
        color = colors[i % len(colors)]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        # Add label
        cv2.putText(overlay, f"mask_{i}", (x + 4, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)


def run_mask(
    input_video: Path,
    output_video: Path,
    preset: str = "none",
    fill_mode: str = "black",
    custom_json: str | None = None,
    debug_video: bool = False,
    report_json: Path | None = None,
) -> dict:
    """Mask input video and return report dict."""
    if preset == "none":
        # No masking — just copy or symlink
        import shutil
        output_video.parent.mkdir(parents=True, exist_ok=True)
        if input_video.resolve() != output_video.resolve():
            shutil.copy2(input_video, output_video)
        report = {
            "mask_enabled": False,
            "preset": "none",
            "fill_mode": fill_mode,
            "mask_rects": [],
            "masked_video_path": str(output_video),
        }
        if report_json:
            report_json.parent.mkdir(parents=True, exist_ok=True)
            report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    cap = cv2.VideoCapture(str(input_video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    rects = get_rects(preset, custom_json, width, height)
    if not rects:
        print(f"[WARN] No mask rectangles for preset={preset}")
        cap.release()
        return run_mask(input_video, output_video, preset="none", fill_mode=fill_mode,
                        report_json=report_json)

    output_video.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_video), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot open video writer: {output_video}")

    t0 = time.time()
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Apply mask
        for x, y, w, h in rects:
            fill_rect(frame, x, y, w, h, fill_mode)

        if debug_video:
            draw_debug_rects(frame, rects)

        writer.write(frame)
        frame_idx += 1

        if frame_idx % 100 == 0:
            elapsed = time.time() - t0
            rate = frame_idx / max(elapsed, 0.001)
            print(f"  mask: {frame_idx}/{total_frames} frames ({rate:.0f} fps)")

    cap.release()
    writer.release()
    elapsed = time.time() - t0

    # Rename tmp to final if needed
    print(f"[OK] Masked {frame_idx} frames in {elapsed:.1f}s -> {output_video}")

    report = {
        "mask_enabled": True,
        "preset": preset,
        "fill_mode": fill_mode,
        "debug_video": debug_video,
        "mask_rects": [
            {"x": x, "y": y, "w": w, "h": h, "label": f"mask_{i}"}
            for i, (x, y, w, h) in enumerate(rects)
        ],
        "video_resolution": f"{width}x{height}",
        "total_frames": frame_idx,
        "processing_time_s": round(elapsed, 1),
        "masked_video_path": str(output_video),
    }

    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mask broadcast overlays in input video for TrackNet inference."
    )
    parser.add_argument("--input-video", type=Path, required=True)
    parser.add_argument("--output-video", type=Path, required=True)
    parser.add_argument("--preset", choices=list(PRESETS.keys()) + ["custom_json"],
                        default="none", help="Mask preset or custom_json.")
    parser.add_argument("--fill", choices=["black", "blur", "median"], default="black",
                        help="Fill mode for masked regions.")
    parser.add_argument("--mask-json", type=str, default=None,
                        help="JSON file with custom mask rectangles.")
    parser.add_argument("--debug-video", action="store_true",
                        help="Draw colored rectangles on masked regions.")
    parser.add_argument("--report-json", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_mask(
        input_video=args.input_video,
        output_video=args.output_video,
        preset=args.preset,
        fill_mode=args.fill,
        custom_json=args.mask_json,
        debug_video=args.debug_video,
        report_json=args.report_json,
    )


if __name__ == "__main__":
    main()
