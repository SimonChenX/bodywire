"""Download the MediaPipe task models used by bodywire.

Models are not committed (see ``.gitignore``); run this once after cloning::

    python tools/download_models.py

The files land in ``models/`` by default and can be overridden with
``--model-dir`` or the ``BODYWIRE_MODEL_DIR`` environment variable.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

MODELS = {
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
}

MIN_BYTES = 1_000_000


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {dest.name} ...", flush=True)
    with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {pct:3d}%  {done / 1e6:6.2f}/{total / 1e6:.2f} MB", end="", flush=True)
    print()
    if tmp.stat().st_size < MIN_BYTES:
        raise RuntimeError(f"{dest.name} looks truncated ({tmp.stat().st_size} bytes)")
    tmp.replace(dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download MediaPipe task models")
    parser.add_argument(
        "--model-dir",
        default=os.environ.get("BODYWIRE_MODEL_DIR", "models"),
        help="target directory (default: models)",
    )
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args(argv)

    out = Path(args.model_dir)
    for name, url in MODELS.items():
        dest = out / name
        if dest.is_file() and dest.stat().st_size >= MIN_BYTES and not args.force:
            print(f"{name} already present ({dest.stat().st_size / 1e6:.2f} MB)")
            continue
        download(url, dest)
        print(f"  saved {dest} ({dest.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI surface
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)