#!/usr/bin/env python3
"""Publish one scored sweep result as dashboard prediction trajectories."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy a selected sweep prediction into output/<video>/trajectories.")
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--configuration", default="", help="Configuration tag. Default: selected_configuration from sweep summary.")
    parser.add_argument("--video-id", action="append", default=[], help="Video to publish. Default: all videos in sweep summary.")
    args = parser.parse_args()

    sweep_root = args.sweep_root.resolve()
    summary_path = sweep_root / "sweep_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    configuration_tag = args.configuration or summary.get("selected_configuration", "")
    if not configuration_tag:
        raise SystemExit("Provide --configuration or run a sweep that selects a configuration.")
    video_ids = args.video_id or summary.get("video_ids", [])
    if not video_ids:
        raise SystemExit("Provide --video-id or use a sweep summary containing video_ids.")
    configuration = next(
        (entry for entry in summary.get("configurations", []) if entry.get("tag") == configuration_tag),
        {},
    )
    published = []
    for video_id in video_ids:
        source = sweep_root / configuration_tag / video_id
        raw = source / f"{video_id}_ball.csv"
        candidates = source / f"{video_id}_candidates.csv"
        filtered = source / f"{video_id}_filtered.csv"
        required = [raw, candidates, filtered, source / "raw_evaluation.json", source / "filtered_evaluation.json"]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise SystemExit("Cannot publish incomplete sweep output:\n" + "\n".join(missing))
        target = ROOT / "output" / video_id / "trajectories"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw, target / "raw_prediction.csv")
        shutil.copy2(filtered, target / "filtered_prediction.csv")
        shutil.copy2(candidates, target / "candidates.csv")
        shutil.copy2(source / "raw_evaluation.json", target / "raw_prediction_evaluation.json")
        shutil.copy2(source / "filtered_evaluation.json", target / "filtered_prediction_evaluation.json")
        metadata = {
            "video_id": video_id,
            "selected_mode": "filtered_prediction",
            "published_from_sweep": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
            "configuration": {
                "threshold": configuration.get("threshold"),
                "eval_mode": configuration.get("eval_mode"),
                "device": summary.get("device"),
                "requested_batch_size": configuration.get("requested_batch_size"),
            },
            "sources": {
                "raw_prediction": "trajectories/raw_prediction.csv",
                "filtered_prediction": "trajectories/filtered_prediction.csv",
                "candidate_csv": "trajectories/candidates.csv",
            },
        }
        (target / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        published.append(metadata)
    print(json.dumps(published, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
