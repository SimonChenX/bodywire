"""Command line entry point: ``bodywire <command>``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import __version__
from .capture import OrbbecCamera, OrbbecError, list_devices, sdk_version
from .daemon import DaemonConfig, run as run_daemon
from .pose.mediapipe_pose import (
    HAND_MODEL,
    POSE_MODEL,
    MediaPipeError,
    PoseEstimator,
    default_model_dir,
)
from .receiver import SkeletonReceiver
from .skeleton.k4abt import JOINT_NAMES, ConfidenceLevel
from .skeleton.pipeline import SkeletonPipeline


# --------------------------------------------------------------------------
# devices / check
# --------------------------------------------------------------------------
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


def _cmd_check(args: argparse.Namespace) -> int:
    ok = True
    try:
        print(f"OrbbecSDK      {sdk_version()}")
        devices = list_devices()
        print(f"devices        {len(devices)}")
        for dev in devices:
            print(f"               {dev}")
        if not devices:
            ok = False
    except OrbbecError as exc:
        print(f"OrbbecSDK      ERROR: {exc}")
        ok = False

    model_dir = Path(args.model_dir) if args.model_dir else default_model_dir()
    print(f"model dir      {model_dir}")
    for name in (POSE_MODEL, HAND_MODEL):
        path = model_dir / name
        status = f"ok ({path.stat().st_size / 1e6:.1f} MB)" if path.is_file() else "MISSING"
        print(f"  {name:<28} {status}")
        ok = ok and path.is_file()

    try:
        import cv2
        import mediapipe

        print(f"mediapipe      {mediapipe.__version__}")
        print(f"opencv         {cv2.__version__}")
    except ImportError as exc:
        print(f"python deps    ERROR: {exc}")
        ok = False
    print(f"numpy          {np.__version__}")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# probe
# --------------------------------------------------------------------------
def _save_frame(frame, out_dir: Path, stem: str, canvas=None) -> None:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    if frame.depth is not None:
        np.save(out_dir / f"{stem}_depth_mm.npy", frame.depth)
        depth = np.nan_to_num(frame.depth, nan=0.0)
        vis = np.clip((depth - 300.0) / (3000.0 - 300.0), 0.0, 1.0)
        cv2.imwrite(str(out_dir / f"{stem}_depth.png"), (vis * 255).astype(np.uint8))
    if frame.color_bgr is not None:
        cv2.imwrite(str(out_dir / f"{stem}_color.png"), frame.color_bgr)
    if canvas is not None:
        cv2.imwrite(str(out_dir / f"{stem}_annotated.png"), canvas)


def _cmd_probe(args: argparse.Namespace) -> int:
    try:
        version = sdk_version()
    except OrbbecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"OrbbecSDK {version}")

    estimator = None
    pipeline = None
    if args.pose:
        try:
            estimator = PoseEstimator(model_dir=args.model_dir)
            pipeline = SkeletonPipeline(estimator)
        except MediaPipeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        cam = OrbbecCamera()
        cam.open()
    except OrbbecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if estimator:
            estimator.close()
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
        last_ts = 0

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
                    parts.append(
                        f"depth={frame.depth.shape[1]}x{frame.depth.shape[0]} "
                        f"valid={ratio:.1%} med={float(np.nanmedian(frame.depth)):.0f}mm"
                    )
                else:
                    parts.append("depth=all-invalid")
            if frame.color_bgr is not None:
                parts.append(f"color={frame.color_bgr.shape[1]}x{frame.color_bgr.shape[0]}")

            canvas = None
            if pipeline is not None and frame.color_bgr is not None:
                ts = int(frame.depth_ts_us // 1000) if frame.depth_ts_us else int(time.monotonic() * 1000)
                ts = max(ts, last_ts + 1)
                last_ts = ts
                output = pipeline.process(frame, ts)
                if output is None:
                    parts.append("pose=none")
                else:
                    visible = sum(1 for c in output.skeleton.confidence if c != ConfidenceLevel.NONE)
                    hand = bool(output.pose.left_hand or output.pose.right_hand)
                    parts.append(f"pose=ok joints={visible}/32 hands={int(hand)}")
                    if args.show:
                        from .preview import compose

                        canvas = compose(
                            frame.color_bgr,
                            frame.depth,
                            output.pose,
                            output.skeleton,
                            output.camera,
                            show_depth=args.depth_view,
                        )
            elif frame.depth_intrinsic is not None:
                parts.append(f"K={frame.depth_intrinsic}")

            print("  ".join(parts))

            if out_dir is not None and not saved and frame.depth is not None:
                _save_frame(frame, out_dir, "bodywire_probe", canvas)
                saved = True
                print(f"saved sample to {out_dir.resolve()}")

            if args.show:
                import cv2

                if canvas is None:
                    canvas = frame.color_bgr if frame.color_bgr is not None else None
                if canvas is not None:
                    cv2.imshow("bodywire probe", canvas)
                if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                    break

        print(f"captured {count} frame(s)")
        return 0 if count else 1
    finally:
        cam.close()
        if estimator is not None:
            estimator.close()
        if args.show:
            try:
                import cv2

                cv2.destroyAllWindows()
            except Exception:  # pragma: no cover
                pass


# --------------------------------------------------------------------------
# run (daemon) / listen (receiver)
# --------------------------------------------------------------------------
def _cmd_run(args: argparse.Namespace) -> int:
    config = DaemonConfig(
        host=args.host,
        port=args.port,
        duration=args.duration,
        preview=args.preview,
        depth_view=args.depth_view,
        color=not args.no_color,
        width=args.width,
        height=args.height,
        fps=args.fps,
        num_poses=args.num_poses,
        model_dir=args.model_dir,
        calibration_every_s=args.calibration_interval,
        body_id=args.body_id,
        quiet=args.quiet,
    )
    try:
        return run_daemon(config)
    except (OrbbecError, MediaPipeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _cmd_jumpwork(args: argparse.Namespace) -> int:
    from .jumpwork.service import run as run_jumpwork

    return run_jumpwork(
        port=args.port,
        host=args.host,
        bodywire_port=args.bodywire_port,
        write_flag=not args.no_flag,
    )


def _cmd_listen(args: argparse.Namespace) -> int:
    receiver = SkeletonReceiver(port=args.port, host=args.bind, timeout=0.5)
    print(f"listening on udp {args.bind}:{receiver.port} (Ctrl+C to stop)")
    deadline = time.time() + args.duration if args.duration else None
    shown_calibration = False
    try:
        while True:
            if deadline is not None and time.time() >= deadline:
                break
            if not shown_calibration and receiver.state.calibration:
                cal = receiver.state.calibration
                print(
                    f"calibration: aligned={cal.get('aligned')} "
                    f"space={cal.get('coordinate_space')} "
                    f"device={cal.get('device', {}).get('name')}"
                )
                shown_calibration = True

            frame = receiver.poll(timeout=0.5)
            if frame is None:
                continue

            if args.json:
                payload = {
                    "frame_id": frame.frame_id,
                    "timestamp_us": frame.timestamp_us,
                    "bodies": [
                        {
                            "body_id": body.body_id,
                            "state": body.tracking_state,
                            "joints": {
                                name: {"x": x, "y": y, "z": z, "confidence": int(conf)}
                                for (x, y, z), conf, name in zip(
                                    body.joints_mm, body.confidence, JOINT_NAMES
                                )
                            },
                        }
                        for body in frame.bodies
                    ],
                }
                print(json.dumps(payload, ensure_ascii=False))
                continue

            if not frame.bodies:
                print(f"frame {frame.frame_id}: no body")
                continue
            for body in frame.bodies:
                head, head_conf = body.joint("HEAD")
                pelvis, _ = body.joint("PELVIS")
                print(
                    f"frame {frame.frame_id}: body={body.body_id} state={body.tracking_state} "
                    f"head=({head[0]},{head[1]},{head[2]})mm conf={head_conf} "
                    f"pelvis=({pelvis[0]},{pelvis[1]},{pelvis[2]})mm"
                )
        print(
            f"received {receiver.state.frames} frames, {receiver.state.controls} control packets, "
            f"{receiver.state.parse_errors} parse errors"
        )
        return 0
    finally:
        receiver.close()


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bodywire", description="Astra+ -> k4abt skeletons over UDP")
    parser.add_argument("--version", action="version", version=f"bodywire {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="list connected Orbbec devices").set_defaults(func=_cmd_devices)

    p_check = sub.add_parser("check", help="verify SDK, camera, models and python deps")
    p_check.add_argument("--model-dir", help="override the model directory")
    p_check.set_defaults(func=_cmd_check)

    p_probe = sub.add_parser("probe", help="open the camera and report frames")
    p_probe.add_argument("--frames", type=int, default=10, help="number of frames (0 = until duration)")
    p_probe.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = disabled)")
    p_probe.add_argument("--timeout", type=int, default=1000, help="frame timeout in ms")
    p_probe.add_argument("--width", type=int, default=640)
    p_probe.add_argument("--height", type=int, default=480)
    p_probe.add_argument("--fps", type=int, default=30)
    p_probe.add_argument("--no-color", action="store_true", help="depth only")
    p_probe.add_argument("--profiles", action="store_true", help="print every supported stream profile")
    p_probe.add_argument("--save", metavar="DIR", help="save a sample frame to DIR")
    p_probe.add_argument("--pose", action="store_true", help="run MediaPipe pose + skeleton (M1)")
    p_probe.add_argument("--model-dir", help="override the model directory")
    p_probe.add_argument("--show", action="store_true", help="show an OpenCV preview window")
    p_probe.add_argument("--depth-view", action="store_true", help="show depth beside colour in the preview")
    p_probe.set_defaults(func=_cmd_probe)

    p_run = sub.add_parser("run", help="capture + infer + publish over UDP")
    p_run.add_argument("--host", default="127.0.0.1", help="destination host")
    p_run.add_argument("--port", type=int, default=9871, help="destination UDP port")
    p_run.add_argument("--duration", type=float, default=0.0)
    p_run.add_argument("--width", type=int, default=640)
    p_run.add_argument("--height", type=int, default=480)
    p_run.add_argument("--fps", type=int, default=30)
    p_run.add_argument("--no-color", action="store_true")
    p_run.add_argument("--preview", action="store_true")
    p_run.add_argument("--depth-view", action="store_true")
    p_run.add_argument("--num-poses", type=int, default=1)
    p_run.add_argument("--model-dir", help="override the model directory")
    p_run.add_argument("--calibration-interval", type=float, default=2.0, help="seconds between calibration packets")
    p_run.add_argument("--body-id", type=int, default=1)
    p_run.add_argument("--quiet", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    p_listen = sub.add_parser("listen", help="receive and print bodywire packets")
    p_listen.add_argument("--port", type=int, default=9871)
    p_listen.add_argument("--bind", default="0.0.0.0")
    p_listen.add_argument("--duration", type=float, default=0.0)
    p_listen.add_argument("--json", action="store_true", help="print one JSON object per frame")
    p_listen.set_defaults(func=_cmd_listen)

    p_jump = sub.add_parser("jumpwork", help="serve JUMPWORK's pose-service protocol")
    p_jump.add_argument("--port", type=int, default=11102, help="WebSocket port JUMPWORK connects to")
    p_jump.add_argument("--host", default="0.0.0.0")
    p_jump.add_argument("--bodywire-port", type=int, default=9871, help="UDP port bodywire publishes to")
    p_jump.add_argument("--no-flag", action="store_true", help="do not write %%TEMP%%\\jumporin_shared_memory")
    p_jump.set_defaults(func=_cmd_jumpwork)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())