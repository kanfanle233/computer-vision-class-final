#!/usr/bin/env python3
"""Evaluate shuttlecock coordinates against TrackNetV2 label CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


DEFAULT_TOLERANCES = (10.0, 20.0)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_ball_csv(path: Path) -> dict:
    rows = {}
    duplicates = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frame = int(_number(row.get("Frame", row.get("frame", 0))))
            if frame in rows:
                duplicates.append(frame)
                continue
            visibility = int(_number(row.get("Visibility", row.get("visibility", 0)))) > 0
            x = _number(row.get("X", row.get("x_px", 0)))
            y = _number(row.get("Y", row.get("y_px", 0)))
            rows[frame] = {
                "frame": frame,
                "visible": visibility and not (x == 0 and y == 0),
                "evaluable_visible": visibility and not (x == 0 and y == 0) and row.get("Source", row.get("source", "")).lower() not in {"interp", "interpolated"},
                "x": x,
                "y": y,
                "source": row.get("Source", row.get("source", "")),
            }
    return {"rows": rows, "duplicates": sorted(set(duplicates)), "path": str(path)}


def integrity_report(prediction: dict, expected_frames: list[int]) -> dict:
    rows = prediction["rows"]
    expected = set(expected_frames)
    actual = set(rows)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    duplicates = prediction["duplicates"]
    return {
        "valid": not duplicates and not missing and not extra,
        "row_count": len(rows),
        "expected_frame_count": len(expected_frames),
        "duplicate_frames": duplicates,
        "missing_frames": missing,
        "extra_frames": extra,
    }


def _metrics(counts: dict) -> dict:
    tp, tn = counts["TP"], counts["TN"]
    fp1, fp2, fn = counts["FP1"], counts["FP2"], counts["FN"]
    precision = tp / (tp + fp1 + fp2) if tp + fp1 + fp2 else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / (tp + tn + fp1 + fp2 + fn) if tp + tn + fp1 + fp2 + fn else 0.0
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _longest_missing_run(gt_rows: dict, pred_rows: dict) -> int:
    longest = current = 0
    for frame in sorted(gt_rows):
        gt = gt_rows[frame]
        pred = pred_rows.get(frame)
        failed = gt["visible"] and (not pred or not pred.get("evaluable_visible", pred["visible"]))
        if failed:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _static_prediction_ratio(pred_rows: dict) -> float:
    visible = [
        (round(row["x"]), round(row["y"]))
        for row in pred_rows.values()
        if row.get("evaluable_visible", row["visible"])
    ]
    if not visible:
        return 0.0
    counts = {}
    for coordinate in visible:
        counts[coordinate] = counts.get(coordinate, 0) + 1
    return max(counts.values()) / len(visible)


def evaluate_rows(gt_rows: dict, pred_rows: dict, tolerance: float) -> dict:
    counts = {"TP": 0, "TN": 0, "FP1": 0, "FP2": 0, "FN": 0}
    localized_distances = []
    visible_pair_distances = []
    for frame in sorted(gt_rows):
        gt = gt_rows[frame]
        pred = pred_rows.get(frame, {"visible": False, "evaluable_visible": False, "x": 0.0, "y": 0.0})
        pred_visible = pred.get("evaluable_visible", pred["visible"])
        if not gt["visible"] and not pred_visible:
            counts["TN"] += 1
        elif not gt["visible"] and pred_visible:
            counts["FP2"] += 1
        elif gt["visible"] and not pred_visible:
            counts["FN"] += 1
        else:
            distance = math.hypot(gt["x"] - pred["x"], gt["y"] - pred["y"])
            visible_pair_distances.append(distance)
            if distance <= tolerance:
                counts["TP"] += 1
                localized_distances.append(distance)
            else:
                counts["FP1"] += 1
    result = {"tolerance_px": tolerance, "counts": counts, **_metrics(counts)}
    result["localized_error_px"] = {
        "median": _percentile(localized_distances, 0.5),
        "p95": _percentile(localized_distances, 0.95),
    }
    result["visible_pair_error_px"] = {
        "median": _percentile(visible_pair_distances, 0.5),
        "p95": _percentile(visible_pair_distances, 0.95),
    }
    return result


def evaluate_files(
    ground_truth: Path,
    prediction: Path,
    tolerances=DEFAULT_TOLERANCES,
    source_type: str = "raw_prediction",
    video_id: str | None = None,
) -> dict:
    gt = read_ball_csv(ground_truth)
    pred = read_ball_csv(prediction)
    expected_frames = sorted(gt["rows"])
    return {
        "video_id": video_id or ground_truth.stem.replace("_ball", ""),
        "source_type": source_type,
        "ground_truth": str(ground_truth),
        "prediction": str(prediction),
        "integrity": integrity_report(pred, expected_frames),
        "frame_count": len(expected_frames),
        "visible_ground_truth_frames": sum(row["visible"] for row in gt["rows"].values()),
        "visible_prediction_frames": sum(row.get("evaluable_visible", row["visible"]) for row in pred["rows"].values()),
        "visualized_prediction_frames": sum(row["visible"] for row in pred["rows"].values()),
        "static_prediction_ratio": _static_prediction_ratio(pred["rows"]),
        "longest_visible_miss_run": _longest_missing_run(gt["rows"], pred["rows"]),
        "metrics": {
            f"f1_at_{int(tolerance)}px": evaluate_rows(gt["rows"], pred["rows"], tolerance)
            for tolerance in tolerances
        },
    }


def aggregate_reports(reports: list[dict]) -> dict:
    aggregate = {"video_count": len(reports), "valid_video_count": 0, "metrics": {}}
    valid_reports = [report for report in reports if report["integrity"]["valid"]]
    aggregate["valid_video_count"] = len(valid_reports)
    for key in ("f1_at_10px", "f1_at_20px"):
        counts = {"TP": 0, "TN": 0, "FP1": 0, "FP2": 0, "FN": 0}
        for report in valid_reports:
            for name, value in report["metrics"].get(key, {}).get("counts", {}).items():
                counts[name] += value
        aggregate["metrics"][key] = {"counts": counts, **_metrics(counts)}
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate predicted shuttle coordinates against official CSV labels.")
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--source-type", choices=["reference", "raw_prediction", "filtered_prediction"], default="raw_prediction")
    parser.add_argument("--video-id", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-invalid", action="store_true", help="Return success for malformed predictions while reporting invalid integrity.")
    args = parser.parse_args()

    report = evaluate_files(
        args.ground_truth,
        args.prediction,
        source_type=args.source_type,
        video_id=args.video_id or None,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["integrity"]["valid"] or args.allow_invalid else 2


if __name__ == "__main__":
    raise SystemExit(main())
