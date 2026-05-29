#!/usr/bin/env python3
"""Scan refine reports, compute quality_score (0-100), grade, and select best variant.

Scans output/**/*_ball_refine_report.json, computes quality_score per the plan,
applies Green/Yellow/Red grading, selects best variant per video,
and writes output/ball_quality_summary.csv + .json.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Project root = two levels up from this script.
ROOT = Path(__file__).resolve().parent.parent.parent


def compute_quality_score(c: dict) -> float:
    """Compute 0-100 quality score from refine report counts."""
    frames = max(c.get("frames", 1), 1)
    raw_visible = max(c.get("raw_visible", 1), 1)
    final_visible = c.get("final_visible", 0)
    interpolated = c.get("interpolated", 0)
    max_missing_gap = c.get("max_missing_gap", 0)
    rejected_roi = c.get("rejected_roi", 0)
    rejected_static_lock = c.get("rejected_static_lock", 0)
    rejected_jump = c.get("rejected_jump", 0)

    vis_rate = final_visible / frames
    interp_rate = interpolated / max(final_visible, 1)
    roi_ratio = rejected_roi / raw_visible
    lock_ratio = rejected_static_lock / raw_visible
    jump_ratio = rejected_jump / raw_visible

    score_visible = min(1.0, vis_rate / 0.55)
    score_gap = 1.0 if max_missing_gap <= 75 else max(0.0, 1.0 - (max_missing_gap - 75) / 120.0)
    score_interp = max(0.0, 1.0 - interp_rate / 0.45)
    score_roi = max(0.0, 1.0 - roi_ratio)
    score_static = max(0.0, 1.0 - lock_ratio)
    score_jump = max(0.0, 1.0 - jump_ratio)

    total = (
        35.0 * score_visible
        + 20.0 * score_gap
        + 10.0 * score_interp
        + 15.0 * score_roi
        + 10.0 * score_static
        + 10.0 * score_jump
    )
    return round(total, 2)


def grade_with_score(report: dict) -> tuple[str, str, float]:
    """Return (quality_level, reason, quality_score) using score-based grading."""
    c = report.get("counts", {})
    frames = max(c.get("frames", 1), 1)
    final_visible = c.get("final_visible", 0)
    max_missing_gap = c.get("max_missing_gap", 0)

    vis_rate = final_visible / frames
    quality_score = compute_quality_score(c)

    reasons: list[str] = []

    # Green: score >= 75 AND vis >= 0.55 AND gap <= 75
    if quality_score >= 75.0 and vis_rate >= 0.55 and max_missing_gap <= 75:
        return "Green", "pass", quality_score

    # Yellow: score >= 55 AND vis >= 0.40 AND gap <= 120
    if vis_rate < 0.55:
        reasons.append(f"vis_rate={vis_rate:.2f}<0.55")
    if max_missing_gap > 75:
        reasons.append(f"max_gap={max_missing_gap}>75")
    if quality_score < 75.0:
        reasons.append(f"score={quality_score:.1f}<75")

    if quality_score >= 55.0 and vis_rate >= 0.40 and max_missing_gap <= 120:
        return "Yellow", "; ".join(reasons), quality_score

    # Red
    if vis_rate < 0.40:
        reasons.append(f"vis_rate={vis_rate:.2f}<0.40")
    if max_missing_gap > 120:
        reasons.append(f"max_gap={max_missing_gap}>120")
    return "Red", "; ".join(reasons), quality_score


def scan(output_root: Path) -> list[dict]:
    """Scan for *_ball_refine_report.json and return graded rows with quality_score."""
    rows: list[dict] = []
    for report_path in sorted(output_root.rglob("*_ball_refine_report.json")):
        # Skip stale analysis directory
        rel = report_path.relative_to(output_root)
        if rel.parts[0] == "analysis" and len(rel.parts) > 2 and rel.parts[1] == "_stale":
            continue

        with report_path.open("r", encoding="utf-8") as f:
            report = json.load(f)

        c = report.get("counts", {})
        frames = c.get("frames", 0)
        raw_visible = c.get("raw_visible", 0)
        final_visible = c.get("final_visible", 0)
        interpolated = c.get("interpolated", 0)
        max_missing_gap = c.get("max_missing_gap", 0)

        vis_rate = final_visible / frames if frames else 0
        interp_rate = interpolated / final_visible if final_visible > 0 else 1.0
        quality_score = compute_quality_score(c)

        level, reason, _ = grade_with_score(report)

        # Derive video_id from path: output/<video_id>/.../<file>
        parts = report_path.relative_to(output_root).parts
        video_id = parts[0] if parts else "unknown"
        # Detect try directory (e.g. try_default, try_thresh_010)
        variant = parts[1] if len(parts) > 1 and parts[1].startswith("try_") else ""

        rows.append({
            "video_id": video_id,
            "variant": variant,
            "report_path": str(report_path),
            "frames": frames,
            "raw_visible": raw_visible,
            "final_visible": final_visible,
            "visible_rate": round(vis_rate, 4),
            "rejected_roi": c.get("rejected_roi", 0),
            "rejected_static_lock": c.get("rejected_static_lock", 0),
            "rejected_jump": c.get("rejected_jump", 0),
            "interpolated": interpolated,
            "interp_rate": round(interp_rate, 4),
            "max_missing_gap": max_missing_gap,
            "inpaintnet_enabled": report.get("inpaintnet_enabled", False),
            "quality_score": quality_score,
            "quality_level": level,
            "reason": reason,
        })
    return rows


def select_best(rows: list[dict]) -> dict:
    """Select best variant per video. Returns {video_id: best_row}."""
    by_video: dict[str, list[dict]] = {}
    for r in rows:
        by_video.setdefault(r["video_id"], []).append(r)

    best = {}
    for vid, variants in by_video.items():
        # Prefer Green > Yellow > Red, then highest quality_score
        level_order = {"Green": 0, "Yellow": 1, "Red": 2}
        best_row = min(variants, key=lambda r: (level_order.get(r["quality_level"], 3), -r["quality_score"]))
        best[vid] = best_row
    return best


def main() -> None:
    output_root = ROOT / "output"
    if not output_root.is_dir():
        print(f"[ERROR] output directory not found: {output_root}")
        sys.exit(1)

    rows = scan(output_root)
    if not rows:
        print("[WARN] No *_ball_refine_report.json found under output/")
        sys.exit(0)

    best = select_best(rows)

    # Write CSV
    summary_csv = output_root / "ball_quality_summary.csv"
    fieldnames = [
        "video_id", "variant", "quality_level", "quality_score",
        "visible_rate", "max_missing_gap", "interp_rate",
        "rejected_static_lock", "rejected_jump", "frames",
        "raw_visible", "final_visible", "interpolated", "rejected_roi",
        "inpaintnet_enabled", "reason", "report_path",
    ]
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Write JSON with best selection
    summary_data = {
        "reports": rows,
        "best": {
            vid: {
                "video_id": vid,
                "variant": r["variant"],
                "quality_score": r["quality_score"],
                "quality_level": r["quality_level"],
                "visible_rate": r["visible_rate"],
                "max_missing_gap": r["max_missing_gap"],
                "report_path": r["report_path"],
            }
            for vid, r in sorted(best.items())
        },
    }
    summary_json = output_root / "ball_quality_summary.json"
    summary_json.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    green = [r for r in rows if r["quality_level"] == "Green"]
    yellow = [r for r in rows if r["quality_level"] == "Yellow"]
    red = [r for r in rows if r["quality_level"] == "Red"]

    print(f"\n{'='*80}")
    print(f"  Ball Tracking Quality Summary  ({len(rows)} reports)")
    print(f"{'='*80}")
    print(f"  Green: {len(green)}   Yellow: {len(yellow)}   Red: {len(red)}")
    print(f"{'='*80}")

    # Best variant per video
    print(f"\n  Best Variants:")
    for vid, r in sorted(best.items()):
        variant = f" ({r['variant']})" if r["variant"] else ""
        print(f"    {vid}{variant}: score={r['quality_score']:.1f}  {r['quality_level']}  "
              f"vis={r['visible_rate']:.0%}  gap={r['max_missing_gap']}")

    for level, group in [("Green", green), ("Yellow", yellow), ("Red", red)]:
        if not group:
            continue
        icon = {"Green": "OK", "Yellow": "WARN", "Red": "FAIL"}[level]
        print(f"\n  [{icon}] {level}:")
        for r in sorted(group, key=lambda x: -x["quality_score"]):
            variant = f" ({r['variant']})" if r["variant"] else ""
            print(f"    {r['video_id']}{variant}: "
                  f"score={r['quality_score']:.1f}  vis={r['visible_rate']:.0%}  gap={r['max_missing_gap']}  "
                  f"interp={r['interp_rate']:.0%}  lock={r['rejected_static_lock']}  "
                  f"jump={r['rejected_jump']}")
            if r["reason"] != "pass":
                print(f"      reason: {r['reason']}")

    print(f"\n  CSV:  {summary_csv}")
    print(f"  JSON: {summary_json}")


if __name__ == "__main__":
    main()
