#!/usr/bin/env python3
"""Run a label-aware CUDA parameter sweep for TrackNet predictions."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from evaluate_ball_tracking import aggregate_reports, evaluate_files


ROOT = Path(__file__).resolve().parents[2]
PREDICT = ROOT / "scripts" / "tracknet_runtime" / "predict.py"
FILTER = ROOT / "scripts" / "tools" / "filter_ball_trajectory.py"
WEIGHT = ROOT / "weights" / "TrackNet_best.pt"
DEFAULT_THRESHOLDS = (0.15, 0.20, 0.25, 0.30)
DEFAULT_MODES = ("nonoverlap", "average", "weight")


def run_logged(command, log_path, env=None):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
    return completed.returncode, time.perf_counter() - started


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate TrackNet CUDA threshold/mode combinations on labelled clips.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used for inference.")
    parser.add_argument("--device", choices=["cuda", "cpu", "auto"], default="cuda")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--retry-batch-size", type=int, default=2)
    parser.add_argument("--threshold", type=float, action="append", default=[])
    parser.add_argument("--eval-mode", choices=DEFAULT_MODES, action="append", default=[])
    parser.add_argument("--video-id", action="append", default=[], help="Restrict sweep to selected IDs.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "output" / "tracknet_sweep")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def labelled_ids(requested):
    all_ids = sorted(path.name.replace("_ball.csv", "") for path in (ROOT / "inputs").glob("pro_match*_ball.csv"))
    if requested:
        unknown = sorted(set(requested) - set(all_ids))
        if unknown:
            raise SystemExit(f"Unknown labelled video ids: {', '.join(unknown)}")
        return requested
    return all_ids


def main() -> int:
    args = parse_args()
    thresholds = args.threshold or list(DEFAULT_THRESHOLDS)
    modes = args.eval_mode or list(DEFAULT_MODES)
    video_ids = labelled_ids(args.video_id)
    output_root = args.output_root.resolve()
    summary = {"device": args.device, "video_ids": video_ids, "configurations": []}
    commands = []

    for threshold in thresholds:
        for mode in modes:
            tag = f"threshold_{threshold:.2f}_{mode}"
            configuration = {
                "tag": tag,
                "threshold": threshold,
                "eval_mode": mode,
                "requested_batch_size": args.batch_size,
                "videos": [],
            }
            reports = []
            elapsed_total = 0.0
            for video_id in video_ids:
                input_video = ROOT / "inputs" / f"{video_id}.mp4"
                ground_truth = ROOT / "inputs" / f"{video_id}_ball.csv"
                directory = output_root / tag / video_id
                raw_csv = directory / f"{video_id}_ball.csv"
                candidates_csv = directory / f"{video_id}_candidates.csv"
                filtered_csv = directory / f"{video_id}_filtered.csv"
                environment = os.environ.copy()
                environment["TRACKNET_VIS_THRESH"] = str(threshold)
                inference = [
                    args.python, str(PREDICT),
                    "--video_file", str(input_video),
                    "--tracknet_file", str(WEIGHT),
                    "--save_dir", str(directory),
                    "--device", args.device,
                    "--batch_size", str(args.batch_size),
                    "--large_video",
                    "--eval_mode", mode,
                    "--output_candidates",
                ]
                commands.append(inference)
                used_batch_size = args.batch_size
                retried = False
                if args.dry_run:
                    continue
                if not (args.skip_existing and raw_csv.exists() and candidates_csv.exists()):
                    status, elapsed = run_logged(inference, directory / "inference.log", environment)
                    elapsed_total += elapsed
                    if status != 0 and args.device == "cuda" and args.retry_batch_size != args.batch_size:
                        retried = True
                        used_batch_size = args.retry_batch_size
                        inference[inference.index("--batch_size") + 1] = str(args.retry_batch_size)
                        status, elapsed = run_logged(inference, directory / "inference_retry.log", environment)
                        elapsed_total += elapsed
                    if status != 0:
                        configuration["videos"].append({"video_id": video_id, "status": "inference_failed", "retried": retried})
                        continue
                filter_command = [
                    args.python, str(FILTER),
                    "--candidate-csv", str(candidates_csv),
                    "--frame-count", str(sum(1 for _ in ground_truth.open("r", encoding="utf-8-sig")) - 1),
                    "--output", str(filtered_csv),
                    "--metadata-output", str(directory / "filtered_metadata.json"),
                ]
                status, elapsed = run_logged(filter_command, directory / "filter.log")
                elapsed_total += elapsed
                if status != 0:
                    configuration["videos"].append({"video_id": video_id, "status": "filter_failed"})
                    continue
                raw_report = evaluate_files(ground_truth, raw_csv, source_type="raw_prediction", video_id=video_id)
                filtered_report = evaluate_files(ground_truth, filtered_csv, source_type="filtered_prediction", video_id=video_id)
                (directory / "raw_evaluation.json").write_text(json.dumps(raw_report, indent=2, ensure_ascii=False), encoding="utf-8")
                (directory / "filtered_evaluation.json").write_text(json.dumps(filtered_report, indent=2, ensure_ascii=False), encoding="utf-8")
                reports.append(filtered_report)
                configuration["videos"].append(
                    {
                        "video_id": video_id,
                        "status": "ok",
                        "batch_size": used_batch_size,
                        "retried": retried,
                        "raw_f1_at_10px": raw_report["metrics"]["f1_at_10px"]["f1"],
                        "filtered_f1_at_10px": filtered_report["metrics"]["f1_at_10px"]["f1"],
                    }
                )
            if not args.dry_run:
                configuration["elapsed_s"] = elapsed_total
                configuration["filtered_aggregate"] = aggregate_reports(reports)
                medians = [
                    report["metrics"]["f1_at_10px"]["visible_pair_error_px"]["median"]
                    for report in reports
                    if report["metrics"]["f1_at_10px"]["visible_pair_error_px"]["median"] is not None
                ]
                configuration["median_visible_error_px"] = statistics.median(medians) if medians else None
            summary["configurations"].append(configuration)

    if args.dry_run:
        print(json.dumps({"commands": commands}, indent=2, ensure_ascii=False))
        return 0

    viable = [
        config for config in summary["configurations"]
        if config.get("filtered_aggregate", {}).get("valid_video_count") == len(video_ids)
    ]
    if viable:
        viable.sort(
            key=lambda config: (
                -config["filtered_aggregate"]["metrics"]["f1_at_10px"]["f1"],
                config["median_visible_error_px"] if config["median_visible_error_px"] is not None else float("inf"),
                config["elapsed_s"],
            )
        )
        summary["selected_configuration"] = viable[0]["tag"]
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "sweep_summary.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Summary: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
