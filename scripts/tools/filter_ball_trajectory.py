#!/usr/bin/env python3
"""Select a temporally plausible shuttle path from TrackNet heatmap candidates."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    x: float
    y: float
    confidence: float
    area: float


@dataclass
class Hypothesis:
    score: float
    path: list[Candidate | None]
    previous: Candidate | None
    prior: Candidate | None
    static_run: int


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_candidates(path: Path, frame_count: int) -> dict[int, list[Candidate]]:
    grouped = {frame: [] for frame in range(frame_count)}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frame = int(_float(row.get("Frame", row.get("frame", 0))))
            if frame not in grouped:
                continue
            grouped[frame].append(
                Candidate(
                    _float(row.get("X", row.get("x_px", 0))),
                    _float(row.get("Y", row.get("y_px", 0))),
                    _float(row.get("Confidence", row.get("confidence", 0.2)), 0.2),
                    _float(row.get("Area", row.get("area", 1.0)), 1.0),
                )
            )
    return grouped


def load_raw_as_candidates(path: Path, frame_count: int) -> dict[int, list[Candidate]]:
    grouped = {frame: [] for frame in range(frame_count)}
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frame = int(_float(row.get("Frame", row.get("frame", 0))))
            if frame in seen:
                raise ValueError(f"duplicate frame in raw prediction: {frame}")
            seen.add(frame)
            if frame not in grouped:
                raise ValueError(f"prediction frame outside video: {frame}")
            visible = int(_float(row.get("Visibility", row.get("visibility", 0)))) > 0
            x = _float(row.get("X", row.get("x_px", 0)))
            y = _float(row.get("Y", row.get("y_px", 0)))
            if visible and (x != 0 or y != 0):
                grouped[frame].append(Candidate(x, y, _float(row.get("Confidence", 0.25), 0.25), _float(row.get("Area", 1), 1)))
    if seen != set(range(frame_count)):
        raise ValueError("raw prediction does not contain exactly one row for every video frame")
    return grouped


def _transition_score(previous, prior, candidate, static_run, args):
    if candidate is None:
        return -args.missing_penalty, 0
    score = args.confidence_weight * candidate.confidence + args.area_weight * min(math.sqrt(candidate.area), 8.0)
    next_static = 0
    if previous is not None:
        movement = math.hypot(candidate.x - previous.x, candidate.y - previous.y)
        score -= args.motion_weight * max(0.0, movement - args.free_move_px) ** 2 / max(args.free_move_px, 1.0) ** 2
        next_static = static_run + 1 if movement <= args.static_radius_px else 0
        if next_static > args.static_frames:
            score -= args.static_penalty * (next_static - args.static_frames)
        if prior is not None:
            vx0, vy0 = previous.x - prior.x, previous.y - prior.y
            vx1, vy1 = candidate.x - previous.x, candidate.y - previous.y
            acceleration = math.hypot(vx1 - vx0, vy1 - vy0)
            score -= args.acceleration_weight * max(0.0, acceleration - args.free_accel_px) ** 2 / max(args.free_accel_px, 1.0) ** 2
    return score, next_static


def select_path(grouped: dict[int, list[Candidate]], args) -> list[Candidate | None]:
    hypotheses = [Hypothesis(0.0, [], None, None, 0)]
    for frame in range(args.frame_count):
        options = sorted(grouped.get(frame, []), key=lambda c: (-c.confidence, -c.area))[: args.max_candidates] + [None]
        expanded = []
        for hypothesis in hypotheses:
            for candidate in options:
                delta, static_run = _transition_score(
                    hypothesis.previous, hypothesis.prior, candidate, hypothesis.static_run, args
                )
                previous = candidate if candidate is not None else hypothesis.previous
                prior = hypothesis.previous if candidate is not None else hypothesis.prior
                expanded.append(
                    Hypothesis(
                        hypothesis.score + delta,
                        hypothesis.path + [candidate],
                        previous,
                        prior,
                        static_run if candidate is not None else 0,
                    )
                )
        hypotheses = sorted(expanded, key=lambda hypothesis: hypothesis.score, reverse=True)[: args.beam_width]
    return hypotheses[0].path


def interpolate_short_gaps(path: list[Candidate | None], max_gap: int):
    sources = ["model" if candidate else "missing" for candidate in path]
    start = 0
    while start < len(path):
        if path[start] is not None:
            start += 1
            continue
        end = start
        while end < len(path) and path[end] is None:
            end += 1
        gap = end - start
        if start > 0 and end < len(path) and gap <= max_gap:
            left, right = path[start - 1], path[end]
            for offset in range(gap):
                ratio = (offset + 1) / (gap + 1)
                path[start + offset] = Candidate(
                    left.x + (right.x - left.x) * ratio,
                    left.y + (right.y - left.y) * ratio,
                    0.0,
                    0.0,
                )
                sources[start + offset] = "interp"
        start = end
    return path, sources


def write_filtered(path: Path, selected: list[Candidate | None], sources: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Frame", "Visibility", "X", "Y", "Source", "Confidence", "Area"])
        writer.writeheader()
        for frame, (candidate, source) in enumerate(zip(selected, sources)):
            writer.writerow(
                {
                    "Frame": frame,
                    "Visibility": int(candidate is not None),
                    "X": "" if candidate is None else f"{candidate.x:.3f}",
                    "Y": "" if candidate is None else f"{candidate.y:.3f}",
                    "Source": source,
                    "Confidence": "" if candidate is None else f"{candidate.confidence:.6f}",
                    "Area": "" if candidate is None else f"{candidate.area:.3f}",
                }
            )


def build_parser():
    parser = argparse.ArgumentParser(description="Filter TrackNet trajectory candidates with temporal continuity.")
    parser.add_argument("--candidate-csv", type=Path)
    parser.add_argument("--raw-csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--frame-count", type=int, required=True)
    parser.add_argument("--max-gap", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--beam-width", type=int, default=80)
    parser.add_argument("--confidence-weight", type=float, default=14.0)
    parser.add_argument("--area-weight", type=float, default=0.05)
    parser.add_argument("--missing-penalty", type=float, default=1.6)
    parser.add_argument("--motion-weight", type=float, default=0.10)
    parser.add_argument("--acceleration-weight", type=float, default=0.16)
    parser.add_argument("--free-move-px", type=float, default=70.0)
    parser.add_argument("--free-accel-px", type=float, default=55.0)
    parser.add_argument("--static-radius-px", type=float, default=2.5)
    parser.add_argument("--static-frames", type=int, default=8)
    parser.add_argument("--static-penalty", type=float, default=2.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.candidate_csv and not args.raw_csv:
        raise SystemExit("Provide --candidate-csv or --raw-csv.")
    grouped = load_candidates(args.candidate_csv, args.frame_count) if args.candidate_csv else load_raw_as_candidates(args.raw_csv, args.frame_count)
    selected = select_path(grouped, args)
    selected, sources = interpolate_short_gaps(selected, args.max_gap)
    write_filtered(args.output, selected, sources)
    metadata = {
        "source_type": "filtered_prediction",
        "candidate_csv": str(args.candidate_csv) if args.candidate_csv else None,
        "raw_csv": str(args.raw_csv) if args.raw_csv else None,
        "frame_count": args.frame_count,
        "selected_model_frames": sources.count("model"),
        "interpolated_frames": sources.count("interp"),
        "missing_frames": sources.count("missing"),
        "parameters": {key: value for key, value in vars(args).items() if not isinstance(value, Path)},
    }
    if args.metadata_output:
        args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_output.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
