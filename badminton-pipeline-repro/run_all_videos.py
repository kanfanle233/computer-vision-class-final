#!/usr/bin/env python3
"""Batch-run all input videos with interactive court-point annotation.

For each video:
  1. Opens the first frame in a window — click TL → TR → BR → BL
  2. Saves court points to court_points.json (skips next time)
  3. Runs the full pipeline (TrackNet + Overlay + FX + Export)

Uses MPS (Apple Metal) acceleration by default on macOS.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "inputs"
OUTPUT_DIR = ROOT / "output"
COURT_JSON = ROOT / "court_points.json"

LABELS = ["TL", "TR", "BR", "BL"]


def load_court_db() -> dict:
    if COURT_JSON.exists():
        return json.loads(COURT_JSON.read_text())
    return {}


def save_court_db(db: dict) -> None:
    COURT_JSON.write_text(json.dumps(db, indent=2, ensure_ascii=False))
    print(f"  [saved court points → {COURT_JSON.name}]")


def select_court_points(video_path: Path) -> str | None:
    """Open first frame, let user click 4 corners, return 'x1,y1,...,x4,y4'."""
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"  [ERROR] Cannot read first frame: {video_path}")
        return None

    h, w = frame.shape[:2]
    pts: list[tuple[int, int]] = []
    win = f"Mark Court: {video_path.name}"

    def on_mouse(event, x, y, flags, param):
        nonlocal pts
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x, y))
            print(f"    point {len(pts)} ({LABELS[len(pts)-1]}): ({x}, {y})")

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, min(w * 2, 1600), min(h * 2, 900))
    cv2.setMouseCallback(win, on_mouse)

    print(f"  → Click 4 corners: TL → TR → BR → BL")
    print(f"    'r' = reset, 'q'/ESC = confirm (need 4 points)")

    while True:
        canvas = frame.copy()
        for i, p in enumerate(pts):
            cv2.circle(canvas, p, 6, (0, 255, 255), -1)
            cv2.putText(canvas, LABELS[i], (p[0] + 8, p[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if len(pts) >= 2:
            for i in range(len(pts)):
                j = (i + 1) % 4
                if j < len(pts):
                    cv2.line(canvas, pts[i], pts[j], (0, 255, 0), 2)
            if len(pts) == 4:
                cv2.line(canvas, pts[3], pts[0], (0, 255, 0), 2)
        tip = f"{len(pts)}/4 clicked — next: {LABELS[len(pts)] if len(pts) < 4 else 'done, press q'}"
        cv2.putText(canvas, tip, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(win, canvas)
        k = cv2.waitKey(20) & 0xFF
        if k in (ord("q"), 27) and len(pts) == 4:
            break
        if k == ord("r"):
            pts = []
            print("    [reset]")

    cv2.destroyAllWindows()
    s = ",".join(f"{x},{y}" for x, y in pts)
    return s


def run_pipeline(video_path: Path, court_points: str) -> bool:
    """Run the full pipeline for one video."""
    cmd = [
        sys.executable,
        str(ROOT / "run_pipeline.py"),
        "--input-video", str(video_path),
        "--court-points", court_points,
        "--tracknet-device", "mps",
        "--pose-device", "mps",
        "--refine-ball",
        "--ball-top-pad-px", "200",
        "--ball-side-pad-px", "120",
        "--ball-refine-min-motion-score", "0.0",
        "--ball-refine-max-gap", "6",
        "--no-frontend-export",
    ]
    print(f"  [CMD] {' '.join(cmd)}")
    t0 = time.time()
    try:
        subprocess.run(cmd, cwd=ROOT, check=True)
        elapsed = time.time() - t0
        print(f"  [OK] {video_path.name} — {elapsed:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [FAIL] {video_path.name} — exit code {e.returncode}")
        return False


def main() -> int:
    videos = sorted(INPUT_DIR.glob("*.mp4"))
    if not videos:
        print(f"No .mp4 files found in {INPUT_DIR}")
        return 1

    print(f"Found {len(videos)} videos in {INPUT_DIR}")
    print(f"MPS available: {cv2.__version__}")  # just a sanity print
    print(f"Court points cache: {COURT_JSON}")
    print("=" * 60)

    db = load_court_db()
    results: list[tuple[str, str]] = []

    for i, video in enumerate(videos, 1):
        name = video.stem
        print(f"\n[{i}/{len(videos)}] {name}")

        # Quick sanity check: can we read the first frame?
        cap = cv2.VideoCapture(str(video))
        ok_read, _ = cap.read()
        cap.release()
        if not ok_read:
            print(f"  [SKIP] Corrupt/unreadable video: {video.name}")
            results.append((name, "SKIP (corrupt)"))
            continue

        # Check if court points already saved
        if name in db:
            cp = db[name]
            print(f"  Court points (cached): {cp}")
        else:
            cp = select_court_points(video)
            if cp is None:
                results.append((name, "SKIP (no points)"))
                continue
            db[name] = cp
            save_court_db(db)

        ok = run_pipeline(video, cp)
        results.append((name, "OK" if ok else "FAIL"))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, status in results:
        print(f"  {name}: {status}")

    ok_count = sum(1 for _, s in results if s == "OK")
    print(f"\n{ok_count}/{len(results)} succeeded.")
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
