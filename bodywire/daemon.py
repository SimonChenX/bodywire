"""``bodywired``: capture, infer, publish.

The daemon owns the camera and the pose estimator, then publishes one
``bodywire/1`` datagram per captured frame plus periodic calibration and
heartbeat control datagrams. It is deliberately single-process and
single-threaded: MediaPipe, UDP send and the optional preview all fit in one
30 fps loop on a modern desktop.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field


from .capture import OrbbecCamera
from .capture.orbbec import CameraIntrinsic
from .pose.mediapipe_pose import PoseEstimator
from .preview import compose
from .skeleton.k4abt import BodyTrackingState, SkeletonBody
from .skeleton.pipeline import SkeletonPipeline
from .transport.protocol import (
    Body,
    ControlType,
    SkeletonFrame,
    pack_control,
    pack_frame,
)


@dataclass
class DaemonConfig:
    host: str = "127.0.0.1"
    port: int = 9871
    duration: float = 0.0
    preview: bool = False
    depth_view: bool = False
    color: bool = True
    width: int = 640
    height: int = 480
    fps: int = 30
    num_poses: int = 1
    model_dir: str | None = None
    calibration_every_s: float = 2.0
    heartbeat_every_s: float = 1.0
    stats_every_s: float = 5.0
    body_id: int = 1
    quiet: bool = False


@dataclass
class DaemonStats:
    frames: int = 0
    published: int = 0
    detections: int = 0
    started_at: float = field(default_factory=time.perf_counter)

    @property
    def fps(self) -> float:
        elapsed = max(1e-6, time.perf_counter() - self.started_at)
        return self.frames / elapsed

    @property
    def detection_rate(self) -> float:
        return self.detections / self.frames if self.frames else 0.0


class BodywireDaemon:
    def __init__(self, config: DaemonConfig | None = None) -> None:
        self.config = config or DaemonConfig()
        self.stats = DaemonStats()
        self._sock: socket.socket | None = None
        self._frame_id = 0

    # -- helpers ---------------------------------------------------------
    def _log(self, message: str) -> None:
        if not self.config.quiet:
            print(message, flush=True)

    def _send(self, packet: bytes) -> None:
        assert self._sock is not None
        self._sock.sendto(packet, (self.config.host, self.config.port))

    def _calibration_payload(self, cam: OrbbecCamera) -> dict:
        depth_k, color_k = cam.intrinsics()

        def k(value: CameraIntrinsic | None) -> dict | None:
            return value.as_dict() if value is not None else None

        return {
            "type": "calibration",
            "protocol": "bodywire/1",
            "device": {
                "name": cam.info.name if cam.info else None,
                "pid": cam.info.pid if cam.info else None,
                "serial_number": cam.info.serial_number if cam.info else None,
                "firmware": cam.info.firmware_version if cam.info else None,
            },
            "aligned": bool(cam.aligned),
            "coordinate_space": "color" if cam.aligned else "depth",
            "units": "mm",
            "color": k(color_k),
            "depth": k(depth_k),
            "depth_profile": str(cam.depth_profile) if cam.depth_profile else None,
            "color_profile": str(cam.color_profile) if cam.color_profile else None,
        }

    # -- main loop -------------------------------------------------------
    def run(self) -> int:
        cfg = self.config
        cam = OrbbecCamera()
        cam.open()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        estimator = PoseEstimator(
            model_dir=cfg.model_dir,
            num_poses=cfg.num_poses,
            use_hands=True,
        )
        pipeline = SkeletonPipeline(estimator)

        deadline = time.perf_counter() + cfg.duration if cfg.duration else None
        last_calibration = 0.0
        last_heartbeat = 0.0
        last_stats = time.perf_counter()
        last_ts_ms = 0
        preview_enabled = cfg.preview and cfg.color
        if cfg.preview and not cfg.color:
            self._log("preview disabled: --no-color leaves nothing to draw")

        self._log(f"publishing to {cfg.host}:{cfg.port}")
        try:
            cam.start(
                depth=(cfg.width, cfg.height, cfg.fps),
                color=(cfg.width, cfg.height, cfg.fps) if cfg.color else None,
            )
            self._log(f"depth={cam.depth_profile} color={cam.color_profile} aligned={cam.aligned}")
            self._send_control(ControlType.CALIBRATION, self._calibration_payload(cam))

            while True:
                now = time.perf_counter()
                if deadline is not None and now >= deadline:
                    break

                frame = cam.read(timeout_ms=1000)
                if frame is None:
                    continue

                # MediaPipe needs a strictly increasing millisecond clock.
                ts_ms = int(frame.depth_ts_us // 1000) if frame.depth_ts_us else int(now * 1000)
                if ts_ms <= last_ts_ms:
                    ts_ms = last_ts_ms + 1
                last_ts_ms = ts_ms

                output = pipeline.process(frame, ts_ms)
                self.stats.frames += 1
                body = None
                if output is not None:
                    self.stats.detections += 1
                    body = Body.from_skeleton(
                        SkeletonBody(
                            body_id=cfg.body_id,
                            skeleton=output.skeleton,
                            tracking_state=BodyTrackingState.TRACKED,
                        )
                    )

                out_frame = SkeletonFrame(
                    frame_id=self._frame_id,
                    timestamp_us=int(frame.depth_ts_us or ts_ms * 1000),
                    bodies=(body,) if body is not None else (),
                )
                self._send(pack_frame(out_frame))
                self._frame_id += 1
                self.stats.published += 1

                if now - last_calibration >= cfg.calibration_every_s:
                    self._send_control(ControlType.CALIBRATION, self._calibration_payload(cam))
                    last_calibration = now
                if now - last_heartbeat >= cfg.heartbeat_every_s:
                    self._send_control(
                        ControlType.HEARTBEAT,
                        {
                            "type": "heartbeat",
                            "fps": round(self.stats.fps, 2),
                            "detection_rate": round(self.stats.detection_rate, 3),
                        },
                    )
                    last_heartbeat = now

                if preview_enabled:
                    if not self._draw_preview(frame, output):
                        preview_enabled = False

                if now - last_stats >= cfg.stats_every_s:
                    self._log(
                        f"frames={self.stats.frames} fps={self.stats.fps:.1f} "
                        f"detections={self.stats.detection_rate:.0%}"
                    )
                    last_stats = now
        finally:
            estimator.close()
            cam.close()
            if self._sock is not None:
                self._sock.close()
                self._sock = None
            self._log(
                f"stopped: {self.stats.published} packets, {self.stats.fps:.1f} fps, "
                f"{self.stats.detection_rate:.0%} detected"
            )
        return 0

    def _send_control(self, kind: ControlType, payload: dict) -> None:
        self._send(pack_control(kind, payload))

    def _draw_preview(self, frame, output) -> bool:  # noqa: ANN001
        try:
            import cv2
        except ImportError:  # pragma: no cover
            return False
        pose = output.pose if output else None
        skeleton = output.skeleton if output else None
        camera = output.camera if output else None
        canvas = compose(
            frame.color_bgr,
            frame.depth,
            pose,
            skeleton,
            camera,
            show_depth=self.config.depth_view,
        )
        cv2.imshow("bodywire", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            return False
        return True


def run(config: DaemonConfig | None = None) -> int:
    return BodywireDaemon(config).run()


__all__ = ["BodywireDaemon", "DaemonConfig", "DaemonStats", "run"]