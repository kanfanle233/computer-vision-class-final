import argparse
import os
import shutil
import subprocess
from pathlib import Path

import cv2


BROWSER_CODECS = ("avc1", "H264", "h264")


def _fourcc_name(value: float) -> str:
    code = int(value)
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip()


def video_codec(path: Path) -> str:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return ""
    codec = _fourcc_name(cap.get(cv2.CAP_PROP_FOURCC))
    cap.release()
    return codec


def _open_h264_writer(path: Path, fps: float, size: tuple[int, int]) -> tuple[cv2.VideoWriter, str]:
    for codec in BROWSER_CODECS:
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            return writer, codec
        writer.release()
    raise RuntimeError("OpenCV cannot open an H.264/AVC writer on this machine.")


def _transcode_with_ffmpeg(input_path: Path, output_path: Path) -> dict | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        return None
    cap = cv2.VideoCapture(str(output_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    return {
        "input": str(input_path),
        "output": str(output_path),
        "codec": "ffmpeg/libx264",
        "frames": frames,
        "fps": fps,
        "size": f"{width}x{height}",
        "output_codec": video_codec(output_path),
    }


def transcode_to_h264(input_path: Path, output_path: Path, overwrite: bool = False) -> dict:
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(output_path)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open input video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError(f"Cannot read video size: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f"{output_path.stem}.h264_tmp{output_path.suffix}")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        writer, codec = _open_h264_writer(tmp_path, fps, (width, height))
    except RuntimeError as exc:
        cap.release()
        if tmp_path.exists():
            tmp_path.unlink()
        ffmpeg_result = _transcode_with_ffmpeg(input_path, output_path)
        if ffmpeg_result:
            return ffmpeg_result
        raise RuntimeError(f"{exc} Install ffmpeg with libx264 for browser video export.") from exc
    frame_count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
            writer.write(frame)
            frame_count += 1
    finally:
        cap.release()
        writer.release()

    if frame_count <= 0 or not tmp_path.exists() or tmp_path.stat().st_size <= 0:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"No frames were transcoded from {input_path}")

    os.replace(tmp_path, output_path)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "codec": codec,
        "frames": frame_count,
        "fps": fps,
        "size": f"{width}x{height}",
        "output_codec": video_codec(output_path),
    }


def frontend_video_paths(data_root: Path, include_original: bool = False) -> list[Path]:
    labels = ["overlay.mp4", "final.mp4"]
    if include_original:
        labels.append("original.mp4")
    paths: list[Path] = []
    for label in labels:
        paths.extend(sorted((data_root / "videos").glob(f"*/{label}")))
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcode MP4 files to browser-friendly H.264/AVC using OpenCV.")
    parser.add_argument("videos", nargs="*", help="Input videos to transcode.")
    parser.add_argument("--output", type=str, default="", help="Output path for a single input video.")
    parser.add_argument("--in-place", action="store_true", help="Overwrite each input video with the H.264 copy.")
    parser.add_argument("--all-frontend", action="store_true", help="Transcode frontend/public/data overlay/final videos in place.")
    parser.add_argument("--data-root", type=str, default="frontend/public/data", help="Frontend data root for --all-frontend.")
    parser.add_argument("--include-original", action="store_true", help="Also transcode original.mp4 files in frontend data.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    targets = [Path(p) for p in args.videos]
    if args.all_frontend:
        targets.extend(frontend_video_paths(Path(args.data_root), include_original=args.include_original))
    if not targets:
        raise SystemExit("No videos provided. Use paths or --all-frontend.")
    if args.output and len(targets) != 1:
        raise SystemExit("--output can only be used with one input video.")
    if args.output and args.in_place:
        raise SystemExit("--output and --in-place are mutually exclusive.")
    if not args.output and not args.in_place and not args.all_frontend:
        raise SystemExit("Use --output, --in-place, or --all-frontend.")

    for input_path in targets:
        output_path = input_path if (args.in_place or args.all_frontend) else Path(args.output)
        result = transcode_to_h264(input_path, output_path, overwrite=True)
        print(
            f"[OK] {result['output']} codec={result['output_codec'] or result['codec']} "
            f"frames={result['frames']} size={result['size']} fps={result['fps']:.2f}"
        )


if __name__ == "__main__":
    main()
