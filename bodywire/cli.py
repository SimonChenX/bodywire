"""Command line entry point: ``bodywire <command>``."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from . import __version__
from .capture import OrbbecCamera, OrbbecError, list_devices, sdk_version


def _cmd_devices(_args: argparse.Namespace) -> int:
    try:
        version = sdk_version()
    except OrbbecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"OrbbecSDK {version}")
    devices = list_devices()
    if not devices:
        print("no devices found")
        return 1
    for i, dev in enumerate(devices):
        print(f"[{i}] {dev}")
    return 0


def _save_frame(frame, out_dir: Path, stem: str) -> None:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    if frame.depth is not None:
        depth = np.nan_to_num(frame.depth, nan=0.0)
        np.save(out_dir / f"{stem}_depth_mm.npy", frame.depth)
        vis = np.clip((depth - 300.0) / (3000.0 - 300.0), 0.0, 1.0)
        cv2.imwrite(str(out_dir / f"{stem}_depth.png"), (vis * 255).astype(np.uint8))
    if frame.color_bgr is not None:
        cv2.imwrite(str(out_dir / f"{stem}_color.png"), frame.color_bgr)


def _cmd_probe(args: argparse.Namespace) -> int:
    try:
        version = sdk_version()
    except OrbbecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"OrbbecSDK {version}")

    try:
        cam = OrbbecCamera()
        cam.open()
    except OrbbecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        print(f"device: {cam.info}")
        if args.profiles:
            for sensor, label in ((3, "depth"), (2, "color")):
                print(f"{label} profiles:")
                for p in cam.stream_profiles(sensor):
                    print(f"  {p}")
        else:
            print(
                f"profiles: depth={len(cam.stream_profiles(3))}, "
                f"color={len(cam.stream_profiles(2))} (use --profiles to list)"
            )

        cam.start(
            depth=(args.width, args.height, args.fps),
            color=None if args.no_color else (args.width, args.height, args.fps),
        )
        print(f"depth profile: {cam.depth_profile}")
        print(f"color profile: {cam.color_profile}")
        print(f"aligned (D2C): {cam.aligned}")

        out_dir = Path(args.save) if args.save else None
        deadline = time.time() + args.duration if args.duration else None
        count = 0
        saved = False
        while True:
            if args.frames and count >= args.frames:
                break
            if deadline is not None and time.time() >= deadline:
                break

            frame = cam.read(timeout_ms=args.timeout)
            if frame is None:
                print("timeout waiting for frameset")
                continue

            count += 1
            parts = [f"#{count}", f"idx={frame.depth_index}"]
            if frame.depth is not None:
                valid = np.isfinite(frame.depth)
                ratio = float(valid.mean()) if valid.size else 0.0
                if valid.any():
                    med = float(np.nanmedian(frame.depth))
                    lo = float(np.nanmin(frame.depth))
                    hi = float(np.nanmax(frame.depth))
                    parts.append(
                        f"depth={frame.depth.shape[1]}x{frame.depth.shape[0]} "
                        f"valid={ratio:.1%} med={med:.0f}mm range={lo:.0f}..{hi:.0f}mm"
                    )
                else:
                    parts.append("depth=all-invalid")
            if frame.color_bgr is not None:
                parts.append(f"color={frame.color_bgr.shape[1]}x{frame.color_bgr.shape[0]}")
            if frame.depth_intrinsic is not None:
                parts.append(f"K={frame.depth_intrinsic}")
            print("  ".join(parts))

            if out_dir is not None and not saved and frame.depth is not None:
                _save_frame(frame, out_dir, "bodywire_probe")
                saved = True
                print(f"saved sample to {out_dir.resolve()}")

        print(f"captured {count} frame(s)")
        return 0 if count else 1
    finally:
        cam.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bodywire", description=__doc__)
    parser.add_argument("--version", action="version", version=f"bodywire {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dev = sub.add_parser("devices", help="list connected Orbbec devices")
    p_dev.set_defaults(func=_cmd_devices)

    p_probe = sub.add_parser("probe", help="open the camera and report frames")
    p_probe.add_argument("--frames", type=int, default=10, help="number of frames (0 = until duration)")
    p_probe.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = disabled)")
    p_probe.add_argument("--timeout", type=int, default=1000, help="frame timeout in ms")
    p_probe.add_argument("--width", type=int, default=640)
    p_probe.add_argument("--height", type=int, default=480)
    p_probe.add_argument("--fps", type=int, default=30)
    p_probe.add_argument("--no-color", action="store_true", help="depth only")
    p_probe.add_argument("--profiles", action="store_true", help="print every supported stream profile")
    p_probe.add_argument("--save", metavar="DIR", help="save the first frame to DIR")
    p_probe.set_defaults(func=_cmd_probe)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())