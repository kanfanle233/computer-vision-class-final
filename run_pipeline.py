#!/usr/bin/env python3
"""Cross-platform launcher for the badminton analysis and dashboard export."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output"
TRACKNET_SCRIPT = ROOT / "scripts" / "tracknet_runtime" / "predict.py"
OVERLAY_SCRIPT = ROOT / "scripts" / "overlay" / "overlay_player_analytics.py"
FX_SCRIPT = ROOT / "scripts" / "fx" / "video_fx_bullet_time.py"
EXPORT_SCRIPT = ROOT / "scripts" / "tools" / "export_frontend_data.py"
FILTER_SCRIPT = ROOT / "scripts" / "tools" / "filter_ball_trajectory.py"
EVALUATE_SCRIPT = ROOT / "scripts" / "tools" / "evaluate_ball_tracking.py"
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


def frame_count(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if frames <= 0:
        raise RuntimeError(f"Could not read frame count: {path}")
    return frames


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run TrackNet, player analytics, final render, and frontend export on Windows CUDA or macOS MPS."
    )
    parser.add_argument("--input-video", type=Path, required=True, help="Original input MP4.")
    parser.add_argument("--work-root", type=Path, default=None, help="Output directory. Default: output/<video_id>.")
    parser.add_argument("--court-points", default="", help="Court corners in TL,TR,BR,BL order: x1,y1,...,x4,y4.")
    parser.add_argument(
        "--manual-court",
        action="store_true",
        help="Select court corners interactively. This is also the default when --court-points is omitted.",
    )
    parser.add_argument(
        "--ball-csv",
        type=Path,
        default=None,
        help="Use an existing raw model prediction CSV and skip TrackNet inference.",
    )
    parser.add_argument(
        "--reference-ball-csv",
        type=Path,
        default=None,
        help="Official/reference trajectory CSV. Default: inputs/<video_id>_ball.csv when present.",
    )
    parser.add_argument(
        "--trajectory-mode",
        choices=["reference", "raw_prediction", "filtered_prediction"],
        default="filtered_prediction",
        help="Trajectory used by the generated overlay; all available modes remain exportable to the dashboard.",
    )
    parser.add_argument(
        "--no-ball-filter",
        action="store_true",
        help="Do not generate the temporally filtered TrackNet trajectory.",
    )
    parser.add_argument("--tracknet-device", choices=["auto", "cuda", "mps", "cpu"], default="auto")
    parser.add_argument(
        "--tracknet-batch-size",
        type=int,
        default=4,
        help="TrackNet inference batch size. Lower this on laptop GPUs if CUDA becomes unstable.",
    )
    parser.add_argument("--pose-device", choices=["auto", "cuda", "mps", "cpu"], default="auto")
    parser.add_argument("--tracknet-threshold", type=float, default=0.15, help="TrackNet visibility threshold.")
    parser.add_argument(
        "--tracknet-eval-mode",
        choices=["weight", "average", "nonoverlap"],
        default="weight",
        help="TrackNet temporal ensemble mode; nonoverlap is faster for quick checks.",
    )
    parser.add_argument("--tracknet-preview", action="store_true", help="Also render TrackNet's ball-only preview video.")
    parser.add_argument("--pose-imgsz", type=int, default=960, help="YOLO pose inference image size.")
    parser.add_argument("--detect-interval", type=int, default=1, help="Run pose detection every N frames.")
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
    existing_file(FILTER_SCRIPT, "Ball filter script")
    existing_file(EVALUATE_SCRIPT, "Ball evaluation script")
    existing_file(TRACKNET_WEIGHT, "TrackNet weight")
    existing_file(YOLO_WEIGHT, "YOLO pose weight")

    video_id = input_video.stem
    work_root = (args.work_root or (OUTPUT_ROOT / video_id)).expanduser().resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    tracknet_dir = work_root / "tracknet_v3_result_regen"
    tracknet_dir.mkdir(parents=True, exist_ok=True)
    trajectory_dir = work_root / "trajectories"
    trajectory_dir.mkdir(parents=True, exist_ok=True)

    ball_csv = work_root / f"{video_id}_ball.csv"
    raw_ball_csv = trajectory_dir / "raw_prediction.csv"
    filtered_ball_csv = trajectory_dir / "filtered_prediction.csv"
    reference_ball_csv = trajectory_dir / "reference.csv"
    candidate_csv = tracknet_dir / f"{video_id}_candidates.csv"
    trajectory_metadata = trajectory_dir / "metadata.json"
    overlay_video = work_root / f"{video_id}_overlay.mp4"
    final_video = work_root / f"{video_id}_final.mp4"
    stats_json = work_root / f"{video_id}_stats.json"
    players_csv = work_root / f"{video_id}_players.csv"
    motion_csv = work_root / f"{video_id}_motion.csv"

    print(f"[INFO] python={sys.executable}")
    print(f"[INFO] video_id={video_id}")
    print(f"[INFO] output={work_root}")
    print(f"[INFO] tracknet_device={args.tracknet_device}, pose_device={args.pose_device}")
    print(f"[INFO] tracknet_batch_size={max(1, args.tracknet_batch_size)}")
    print(f"[INFO] trajectory_mode={args.trajectory_mode}")

    supplied_reference = args.reference_ball_csv or (ROOT / "inputs" / f"{video_id}_ball.csv")
    if supplied_reference.exists():
        copy_file(existing_file(supplied_reference, "Reference ball CSV"), reference_ball_csv)
        print(f"[INFO] reference_ball_csv={reference_ball_csv}")
    elif args.trajectory_mode == "reference":
        raise FileNotFoundError(f"Reference ball CSV not found: {supplied_reference}")

    if args.ball_csv:
        supplied_prediction = existing_file(args.ball_csv, "Raw prediction ball CSV")
        copy_file(supplied_prediction, raw_ball_csv)
        print(f"[STEP 1/4] Reusing raw prediction CSV: {supplied_prediction}")
    else:
        env = os.environ.copy()
        env["TRACKNET_VIS_THRESH"] = str(args.tracknet_threshold)
        tracknet_cmd = [
            sys.executable,
            str(TRACKNET_SCRIPT),
            "--video_file",
            str(input_video),
            "--tracknet_file",
            str(TRACKNET_WEIGHT),
            "--save_dir",
            str(tracknet_dir),
            "--device",
            args.tracknet_device,
            "--batch_size",
            str(max(1, args.tracknet_batch_size)),
            "--large_video",
            "--eval_mode",
            args.tracknet_eval_mode,
            "--output_candidates",
        ]
        if args.tracknet_preview:
            tracknet_cmd.append("--output_video")
        run_step(
            f"STEP 1/4 TrackNet inference (threshold={args.tracknet_threshold}, mode={args.tracknet_eval_mode})",
            tracknet_cmd,
            env=env,
        )
        generated_ball_csv = existing_file(tracknet_dir / f"{video_id}_ball.csv", "Generated ball CSV")
        copy_file(generated_ball_csv, raw_ball_csv)

    if not args.no_ball_filter and raw_ball_csv.exists():
        filter_cmd = [
            sys.executable,
            str(FILTER_SCRIPT),
            "--output",
            str(filtered_ball_csv),
            "--metadata-output",
            str(trajectory_dir / "filtered_prediction_metadata.json"),
            "--frame-count",
            str(frame_count(input_video)),
        ]
        if candidate_csv.exists():
            filter_cmd += ["--candidate-csv", str(candidate_csv)]
        else:
            filter_cmd += ["--raw-csv", str(raw_ball_csv)]
        run_step("STEP 1B/4 Temporal trajectory filtering", filter_cmd)

    trajectory_files = {
        "reference": reference_ball_csv,
        "raw_prediction": raw_ball_csv,
        "filtered_prediction": filtered_ball_csv,
    }
    selected_ball_csv = trajectory_files[args.trajectory_mode]
    if not selected_ball_csv.exists():
        raise FileNotFoundError(f"Selected trajectory mode is unavailable: {args.trajectory_mode} ({selected_ball_csv})")
    copy_file(selected_ball_csv, ball_csv)

    evaluation_reports = {}
    if reference_ball_csv.exists():
        for source_type in ("raw_prediction", "filtered_prediction"):
            prediction = trajectory_files[source_type]
            if prediction.exists():
                report_path = trajectory_dir / f"{source_type}_evaluation.json"
                run_step(
                    f"STEP 1C/4 Evaluate {source_type}",
                    [
                        sys.executable,
                        str(EVALUATE_SCRIPT),
                        "--ground-truth",
                        str(reference_ball_csv),
                        "--prediction",
                        str(prediction),
                        "--source-type",
                        source_type,
                        "--video-id",
                        video_id,
                        "--output",
                        str(report_path),
                    ],
                )
                evaluation_reports[source_type] = str(report_path.relative_to(work_root))

    trajectory_metadata.write_text(
        json.dumps(
            {
                "video_id": video_id,
                "selected_mode": args.trajectory_mode,
                "sources": {
                    mode: str(path.relative_to(work_root)) if path.exists() else None
                    for mode, path in trajectory_files.items()
                },
                "evaluation_reports": evaluation_reports,
                "tracknet": {
                    "device": args.tracknet_device,
                    "threshold": args.tracknet_threshold,
                    "eval_mode": args.tracknet_eval_mode,
                    "batch_size": max(1, args.tracknet_batch_size),
                    "candidate_csv": str(candidate_csv.relative_to(work_root)) if candidate_csv.exists() else None,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[INFO] selected_ball_source={args.trajectory_mode}: {selected_ball_csv}")

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
    ]
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
