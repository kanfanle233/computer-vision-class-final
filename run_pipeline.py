#!/usr/bin/env python3
"""Cross-platform launcher for the badminton analysis and dashboard export."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output"
TRACKNET_SCRIPT = ROOT / "scripts" / "tracknet_runtime" / "predict.py"
OVERLAY_SCRIPT = ROOT / "scripts" / "overlay" / "overlay_player_analytics.py"
FX_SCRIPT = ROOT / "scripts" / "fx" / "video_fx_bullet_time.py"
EXPORT_SCRIPT = ROOT / "scripts" / "tools" / "export_frontend_data.py"
SMOOTH_BALL_SCRIPT = ROOT / "scripts" / "tools" / "smooth_ball_csv.py"
REFINE_BALL_SCRIPT = ROOT / "scripts" / "tools" / "refine_ball_csv.py"
MASK_SCRIPT = ROOT / "scripts" / "tools" / "mask_tracknet_input.py"
TRACKNET_WEIGHT = ROOT / "weights" / "TrackNet_best.pt"
YOLO_WEIGHT = ROOT / "weights" / "yolov8s-pose.pt"


def existing_file(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def run_step(label: str, cmd: list[str], env: dict[str, str] | None = None) -> None:
    print(f"\n[{label}]")
    print(" ".join(f'"{item}"' if " " in item else item for item in cmd))
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run TrackNet, player analytics, final render, and frontend export on Windows CUDA or macOS MPS."
    )
    parser.add_argument("--input-video", type=Path, required=True, help="Original input MP4.")
    parser.add_argument("--work-root", type=Path, default=None, help="Output directory. Default: output/<video_id>.")
    parser.add_argument("--court-points", default="", help="Court corners in TL,TR,BR,BL order: x1,y1,...,x4,y4.")
    parser.add_argument("--court-width-m", "--court_width_m", dest="court_width_m", type=float, default=6.1)
    parser.add_argument("--court-length-m", "--court_length_m", dest="court_length_m", type=float, default=13.4)
    parser.add_argument(
        "--manual-court",
        action="store_true",
        help="Select court corners interactively. This is also the default when --court-points is omitted.",
    )
    parser.add_argument(
        "--ball-csv",
        type=Path,
        default=None,
        help="Use an existing verified TrackNet ball CSV and skip TrackNet inference.",
    )
    parser.add_argument("--tracknet-device", choices=["auto", "cuda", "mps", "cpu"], default="auto")
    parser.add_argument("--pose-device", choices=["auto", "cuda", "mps", "cpu"], default="auto")
    parser.add_argument("--tracknet-threshold", type=float, default=0.15, help="TrackNet visibility threshold.")
    parser.add_argument(
        "--inpaintnet-file",
        type=Path,
        default=None,
        help="Path to InpaintNet weight. Auto-detects weights/InpaintNet_best.pt if omitted.",
    )
    parser.add_argument(
        "--filter-ball",
        action="store_true",
        help="Conservatively filter obvious shuttle false positives before overlay/export (requires --court-points).",
    )
    parser.add_argument(
        "--refine-ball",
        action="store_true",
        help="Enhanced trajectory refinement (jump rejection, Kalman smoothing, relaxed interp). "
             "Replaces --filter-ball; if both are passed, --refine-ball takes precedence.",
    )
    parser.add_argument("--ball-top-pad-px", type=float, default=160.0)
    parser.add_argument("--ball-side-pad-px", type=float, default=80.0)
    parser.add_argument("--ball-min-motion-score", type=float, default=4.0)
    parser.add_argument("--ball-refine-min-motion-score", type=float, default=0.0,
                         help="Min local motion score for --refine-ball. Keep 0.0 to rely on static-lock/jump filtering.")
    parser.add_argument("--ball-max-interp-gap", type=int, default=2)
    parser.add_argument("--ball-max-interp-step-px", type=float, default=180.0,
                         help="Max per-frame step in pixels for interpolation/jump rejection.")
    parser.add_argument("--ball-refine-max-gap", type=int, default=6,
                         help="Max interpolation gap (frames) for --refine-ball. Ignored by --filter-ball.")
    parser.add_argument(
        "--tracknet-eval-mode",
        choices=["weight", "average", "nonoverlap"],
        default="weight",
        help="TrackNet temporal ensemble mode; nonoverlap is faster for quick checks.",
    )
    parser.add_argument("--tracknet-preview", action="store_true", help="Also render TrackNet's ball-only preview video.")
    parser.add_argument(
        "--tracknet-mask", action="store_true",
        help="Mask broadcast overlays before TrackNet inference. Original video unchanged for overlay/final.",
    )
    parser.add_argument(
        "--tracknet-mask-preset",
        choices=["none", "top_bar", "top_right_scoreboard", "top_right_and_bottom_bar", "broadcast_overlays", "custom_json"],
        default="none",
        help="Mask preset for broadcast overlay regions.",
    )
    parser.add_argument("--tracknet-mask-json", type=str, default=None, help="Custom mask rectangles JSON.")
    parser.add_argument("--tracknet-mask-fill", choices=["black", "blur", "median"], default="black", help="Fill mode.")
    parser.add_argument("--tracknet-mask-debug-video", action="store_true", help="Draw mask rectangles on masked video.")
    parser.add_argument("--pose-imgsz", type=int, default=960, help="YOLO pose inference image size.")
    parser.add_argument("--detect-interval", type=int, default=1, help="Run pose detection every N frames.")
    parser.add_argument(
        "--draw-court-polygon",
        "--draw_court_polygon",
        dest="draw_court_polygon",
        action="store_true",
        help="Draw the calibrated green court quadrilateral in the overlay for point-order verification.",
    )
    parser.add_argument("--embedded-panels", action="store_true", help="Draw stats and mini court inside the video.")
    parser.add_argument(
        "--cinematic-fx",
        action="store_true",
        help="Enable slow-motion bullet-time effects; disabled by default to keep dashboard timing aligned.",
    )
    parser.add_argument(
        "--no-frontend-export",
        action="store_true",
        help="Do not rebuild frontend/public/data after generation.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_video = existing_file(args.input_video, "Input video")
    existing_file(TRACKNET_SCRIPT, "TrackNet script")
    existing_file(OVERLAY_SCRIPT, "Overlay script")
    existing_file(FX_SCRIPT, "FX script")
    existing_file(EXPORT_SCRIPT, "Frontend export script")
    existing_file(SMOOTH_BALL_SCRIPT, "Ball smoothing script")
    existing_file(TRACKNET_WEIGHT, "TrackNet weight")
    existing_file(YOLO_WEIGHT, "YOLO pose weight")

    video_id = input_video.stem
    work_root = (args.work_root or (OUTPUT_ROOT / video_id)).expanduser().resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    tracknet_dir = work_root / "tracknet_v3_result_regen"
    tracknet_dir.mkdir(parents=True, exist_ok=True)

    ball_csv = work_root / f"{video_id}_ball.csv"
    overlay_video = work_root / f"{video_id}_overlay.mp4"
    final_video = work_root / f"{video_id}_final.mp4"
    stats_json = work_root / f"{video_id}_stats.json"
    players_csv = work_root / f"{video_id}_players.csv"
    motion_csv = work_root / f"{video_id}_motion.csv"

    print(f"[INFO] python={sys.executable}")
    print(f"[INFO] video_id={video_id}")
    print(f"[INFO] output={work_root}")
    print(f"[INFO] tracknet_device={args.tracknet_device}, pose_device={args.pose_device}")

    # Resolve InpaintNet path early so both Step 1 and refine-ball can use it.
    inpaintnet_path: Path | None = None
    if args.inpaintnet_file:
        inpaintnet_path = existing_file(args.inpaintnet_file, "InpaintNet weight")
    else:
        auto_path = ROOT / "weights" / "InpaintNet_best.pt"
        if auto_path.is_file():
            inpaintnet_path = auto_path

    # TrackNet input masking (Step 0.5 — before TrackNet, only affects TrackNet input).
    tracknet_input_video = input_video
    if args.tracknet_mask and args.tracknet_mask_preset != "none":
        existing_file(MASK_SCRIPT, "TrackNet mask script")
        masked_video = work_root / f"{video_id}_tracknet_masked.mp4"
        mask_report_json = work_root / f"{video_id}_tracknet_mask_report.json"
        mask_cmd = [
            sys.executable, str(MASK_SCRIPT),
            "--input-video", str(input_video),
            "--output-video", str(masked_video),
            "--preset", args.tracknet_mask_preset,
            "--fill", args.tracknet_mask_fill,
            "--report-json", str(mask_report_json),
        ]
        if args.tracknet_mask_json:
            mask_cmd += ["--mask-json", args.tracknet_mask_json]
        if args.tracknet_mask_debug_video:
            mask_cmd.append("--debug-video")
        run_step("TrackNet input masking", mask_cmd)
        tracknet_input_video = existing_file(masked_video, "Masked video")
        print(f"[INFO] TrackNet will use masked video: {masked_video}")
    elif args.tracknet_mask:
        print("[INFO] --tracknet-mask passed but preset=none; no masking applied.")

    if args.ball_csv:
        verified_ball_csv = existing_file(args.ball_csv, "Ball CSV")
        copy_file(verified_ball_csv, ball_csv)
        print(f"[STEP 1/4] Reusing verified ball CSV: {verified_ball_csv}")
    else:
        env = os.environ.copy()
        env["TRACKNET_VIS_THRESH"] = str(args.tracknet_threshold)
        tracknet_cmd = [
            sys.executable,
            str(TRACKNET_SCRIPT),
            "--video_file",
            str(tracknet_input_video),
            "--tracknet_file",
            str(TRACKNET_WEIGHT),
            "--save_dir",
            str(tracknet_dir),
            "--device",
            args.tracknet_device,
            "--large_video",
            "--eval_mode",
            args.tracknet_eval_mode,
        ]
        if args.tracknet_preview:
            tracknet_cmd.append("--output_video")
        if inpaintnet_path:
            tracknet_cmd += ["--inpaintnet_file", str(inpaintnet_path)]
            print(f"[INFO] InpaintNet rectification enabled: {inpaintnet_path}")
        else:
            reason_msg = "weights/InpaintNet_best.pt not found" if not args.inpaintnet_file else ""
            print(f"[INFO] InpaintNet rectification not enabled{': ' + reason_msg if reason_msg else ''}")
        run_step(
            f"STEP 1/4 TrackNet inference (threshold={args.tracknet_threshold}, mode={args.tracknet_eval_mode})",
            tracknet_cmd,
            env=env,
        )
        generated_ball_csv = existing_file(tracknet_dir / f"{video_id}_ball.csv", "Generated ball CSV")
        copy_file(generated_ball_csv, ball_csv)

    if args.refine_ball:
        if args.filter_ball:
            print("[WARN] Both --filter-ball and --refine-ball passed; --refine-ball takes precedence.")
        if not args.court_points or args.manual_court:
            raise ValueError("--refine-ball requires fixed --court-points.")
        existing_file(REFINE_BALL_SCRIPT, "Ball refinement script")
        raw_ball_csv = work_root / f"{video_id}_ball_tracknet_raw.csv"
        copy_file(ball_csv, raw_ball_csv)
        refine_cmd = [
            sys.executable,
            str(REFINE_BALL_SCRIPT),
            "--input-csv",
            str(raw_ball_csv),
            "--output-csv",
            str(ball_csv),
            "--video",
            str(input_video),
            "--court-points",
            args.court_points,
            "--max-gap",
            str(max(0, args.ball_refine_max_gap)),
            "--max-step-px",
            str(args.ball_max_interp_step_px),
            "--top-pad-px",
            str(args.ball_top_pad_px),
            "--side-pad-px",
            str(args.ball_side_pad_px),
            "--min-motion-score",
            str(args.ball_refine_min_motion_score),
            "--report-json",
            str(work_root / f"{video_id}_ball_refine_report.json"),
        ]
        if inpaintnet_path:
            refine_cmd += ["--inpaintnet-enabled", "--inpaintnet-path", str(inpaintnet_path)]
        run_step("Ball trajectory refinement", refine_cmd)
    elif args.filter_ball:
        if not args.court_points or args.manual_court:
            raise ValueError("--filter-ball requires fixed --court-points so the flight-region filter is reproducible.")
        raw_ball_csv = work_root / f"{video_id}_ball_raw.csv"
        copy_file(ball_csv, raw_ball_csv)
        filter_cmd = [
            sys.executable,
            str(SMOOTH_BALL_SCRIPT),
            "--input-csv",
            str(raw_ball_csv),
            "--output-csv",
            str(ball_csv),
            "--video",
            str(input_video),
            "--court-points",
            args.court_points,
            "--top-pad-px",
            str(args.ball_top_pad_px),
            "--side-pad-px",
            str(args.ball_side_pad_px),
            "--min-motion-score",
            str(args.ball_min_motion_score),
            "--max-interp-gap",
            str(max(0, args.ball_max_interp_gap)),
            "--report-json",
            str(work_root / f"{video_id}_ball_filter_report.json"),
        ]
        run_step("Ball false-positive filtering", filter_cmd)

    overlay_cmd = [
        sys.executable,
        str(OVERLAY_SCRIPT),
        "--video_path",
        str(input_video),
        "--output_path",
        str(overlay_video),
        "--ball_csv",
        str(ball_csv),
        "--stats_json",
        str(stats_json),
        "--players_csv",
        str(players_csv),
        "--motion_csv",
        str(motion_csv),
        "--yolo_model",
        str(YOLO_WEIGHT),
        "--tracker_cfg",
        "bytetrack.yaml",
        "--device",
        args.pose_device,
        "--imgsz",
        str(args.pose_imgsz),
        "--detect_interval",
        str(max(1, args.detect_interval)),
        "--court_width_m",
        str(args.court_width_m),
        "--court_length_m",
        str(args.court_length_m),
    ]
    if args.draw_court_polygon:
        overlay_cmd.append("--draw_court_polygon")
    if not args.embedded_panels:
        overlay_cmd.append("--no_draw_embedded_panels")
    if args.court_points and not args.manual_court:
        overlay_cmd += ["--no_select_court_points", "--court_points", args.court_points]
    else:
        overlay_cmd.append("--select_court_points")
        print("[INFO] Court points not provided; select TL -> TR -> BR -> BL in the OpenCV window, then press q.")
    run_step("STEP 2/4 Player analytics overlay", overlay_cmd)
    existing_file(overlay_video, "Overlay video")

    fx_cmd = [sys.executable, str(FX_SCRIPT), "--input", str(overlay_video), "--output", str(final_video)]
    if not args.cinematic_fx:
        fx_cmd += [
            "--uniform_bullet_count",
            "0",
            "--auto_bullet_count",
            "0",
            "--slow_frames",
            "0",
            "--slow_repeat",
            "1",
        ]
    run_step("STEP 3/4 Final video render", fx_cmd)
    existing_file(final_video, "Final video")

    if not args.no_frontend_export:
        try:
            work_root.relative_to(OUTPUT_ROOT)
        except ValueError:
            print("[WARN] Frontend export skipped: --work-root is outside the project's output/ directory.")
        else:
            run_step("STEP 4/4 Frontend data export", [sys.executable, str(EXPORT_SCRIPT)])
    else:
        print("[STEP 4/4] Frontend export skipped by request.")

    print("\n[DONE] Pipeline completed.")
    for path in (ball_csv, players_csv, motion_csv, stats_json, overlay_video, final_video):
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
