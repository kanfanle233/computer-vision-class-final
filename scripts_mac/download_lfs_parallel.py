import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("rb") as f:
        return f.read(80).startswith(b"version https://git-lfs.github.com/spec")


def lfs_href(batch_url: str, oid: str, size: int) -> str:
    payload = json.dumps(
        {
            "operation": "download",
            "transfers": ["basic"],
            "objects": [{"oid": oid, "size": size}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        batch_url,
        data=payload,
        headers={
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["objects"][0]["actions"]["download"]["href"]


def run_curl_range(href: str, part: Path, start: int, end: int) -> None:
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--http1.1",
        "--retry",
        "3",
        "--retry-all-errors",
        "--connect-timeout",
        "30",
        "--range",
        f"{start}-{end}",
        "--output",
        str(part),
        href,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    expected = end - start + 1
    actual = part.stat().st_size
    if actual != expected:
        raise RuntimeError(f"{part.name}: expected {expected} bytes, got {actual}")


def download(args: argparse.Namespace) -> None:
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and not is_lfs_pointer(out) and out.stat().st_size == args.size:
        actual_sha = sha256_file(out)
        if actual_sha == args.oid:
            print(f"[OK] {out} already exists and sha256 matches")
            return
        print(f"[WARN] {out} exists but sha256={actual_sha}; redownloading")

    curl_bin = shutil.which("curl")
    if not curl_bin:
        raise SystemExit("curl is required for parallel LFS downloads")

    href = lfs_href(args.batch_url, args.oid, args.size)
    chunk_size = max(1024 * 1024, args.chunk_size)
    ranges = []
    for start in range(0, args.size, chunk_size):
        end = min(args.size - 1, start + chunk_size - 1)
        ranges.append((start, end))

    tmp_dir = Path(tempfile.mkdtemp(prefix="lfs_parts_", dir=str(out.parent)))
    try:
        print(f"[INFO] {out}: {len(ranges)} chunks, workers={args.workers}")
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            future_to_part = {}
            for idx, (start, end) in enumerate(ranges):
                part = tmp_dir / f"{idx:05d}.part"
                future = pool.submit(run_curl_range, href, part, start, end)
                future_to_part[future] = (idx, part)
            done = 0
            for future in as_completed(future_to_part):
                idx, _part = future_to_part[future]
                future.result()
                done += 1
                print(f"[INFO] chunk {done}/{len(ranges)} complete (idx={idx})")

        tmp_out = out.with_suffix(out.suffix + ".download")
        with tmp_out.open("wb") as w:
            for idx in range(len(ranges)):
                part = tmp_dir / f"{idx:05d}.part"
                with part.open("rb") as r:
                    shutil.copyfileobj(r, w)

        if tmp_out.stat().st_size != args.size:
            raise RuntimeError(f"{tmp_out} expected {args.size} bytes, got {tmp_out.stat().st_size}")
        actual_sha = sha256_file(tmp_out)
        if actual_sha != args.oid:
            raise RuntimeError(f"{tmp_out} expected sha256 {args.oid}, got {actual_sha}")
        tmp_out.replace(out)
        print(f"[OK] {out} ({args.size} bytes, sha256 verified)")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--oid", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--batch-url", required=True)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--chunk-size", type=int, default=4 * 1024 * 1024)
    args = parser.parse_args()
    download(args)


if __name__ == "__main__":
    main()
