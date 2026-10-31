"""Lift 2D landmarks to 3D millimetres using the aligned depth map.

After software D2C the depth map shares the colour pixel grid, so a landmark's
depth can be sampled directly and back-projected with the colour intrinsics::

    X = (u - cx) * Z / fx
    Y = (v - cy) * Z / fy
    Z = depth(u, v)

Points without a valid depth sample are returned as ``NaN``; the temporal
filter fills them from the previous frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..pose import Landmark, PoseResult
from ..pose.mediapipe_pose import (
    HAND_WRIST,
    LEFT_WRIST,
    POSE_LANDMARKS,
    RIGHT_WRIST,
)


@dataclass(frozen=True)
class CameraModel:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @classmethod
    def from_intrinsic(cls, intrinsic) -> "CameraModel":  # noqa: ANN001
        return cls(
            fx=float(intrinsic.fx),
            fy=float(intrinsic.fy),
            cx=float(intrinsic.cx),
            cy=float(intrinsic.cy),
            width=int(intrinsic.width),
            height=int(intrinsic.height),
        )

    def project(self, point_mm: tuple[float, float, float]) -> tuple[float, float]:
        """Project a camera-space point back to pixel coordinates."""
        x, y, z = point_mm
        if z <= 0:
            return float("nan"), float("nan")
        return x / z * self.fx + self.cx, y / z * self.fy + self.cy


@dataclass
class LiftResult:
    """Camera-space landmarks in millimetres (``NaN`` where unknown)."""

    pose_mm: np.ndarray  # (33, 3) float32
    confidence: np.ndarray  # (33,) float32 in 0..1
    left_hand_mm: np.ndarray | None = None  # (21, 3)
    right_hand_mm: np.ndarray | None = None
    left_hand_confidence: np.ndarray | None = None
    right_hand_confidence: np.ndarray | None = None

    def valid(self, index: int) -> bool:
        return bool(np.isfinite(self.pose_mm[index]).all())


def sample_depth(
    depth_mm: np.ndarray,
    u: float,
    v: float,
    window: int = 5,
    min_valid: int = 1,
) -> float | None:
    """Median of valid depth pixels around ``(u, v)``.

    A median over a small window rejects speckle and edges better than a single
    pixel. Returns ``None`` when fewer than ``min_valid`` finite pixels exist.
    """
    if depth_mm is None or depth_mm.size == 0:
        return None
    h, w = depth_mm.shape[:2]
    if not (np.isfinite(u) and np.isfinite(v)):
        return None
    ui = int(round(u))
    vi = int(round(v))
    if ui < 0 or vi < 0 or ui >= w or vi >= h:
        return None
    half = max(0, window // 2)
    patch = depth_mm[max(0, vi - half) : min(h, vi + half + 1), max(0, ui - half) : min(w, ui + half + 1)]
    values = patch[np.isfinite(patch)]
    if values.size < max(1, min_valid):
        return None
    return float(np.median(values))


def _lift(
    landmark: Landmark,
    depth_mm: np.ndarray,
    cam: CameraModel,
    window: int,
    fallback_mm: float | None = None,
) -> tuple[np.ndarray, float]:
    u = landmark.x * cam.width
    v = landmark.y * cam.height
    d = sample_depth(depth_mm, u, v, window)
    if d is None:
        d = fallback_mm
    score = float(landmark.score)
    if d is None or score <= 0.05:
        return np.array([np.nan, np.nan, np.nan], dtype=np.float32), score
    point = np.array(
        [
            (u - cam.cx) * d / cam.fx,
            (v - cam.cy) * d / cam.fy,
            d,
        ],
        dtype=np.float32,
    )
    return point, score


def _depth_of(point: np.ndarray | None) -> float | None:
    if point is None:
        return None
    if not np.isfinite(point[2]):
        return None
    return float(point[2])


def lift_pose(
    result: PoseResult,
    depth_mm: np.ndarray,
    cam: CameraModel,
    window: int = 5,
) -> LiftResult:
    """Back-project pose and hand landmarks into camera space (mm)."""
    pose_mm = np.full((POSE_LANDMARKS, 3), np.nan, dtype=np.float32)
    confidence = np.zeros((POSE_LANDMARKS,), dtype=np.float32)

    for i, lm in enumerate(result.pose[:POSE_LANDMARKS]):
        point, score = _lift(lm, depth_mm, cam, window)
        pose_mm[i] = point
        confidence[i] = score

    left_hand_mm = right_hand_mm = None
    left_conf = right_conf = None

    if result.left_hand:
        wrist_depth = _depth_of(pose_mm[LEFT_WRIST]) if pose_mm.shape[0] > LEFT_WRIST else None
        left_hand_mm, left_conf = _lift_hand(result.left_hand, depth_mm, cam, window, wrist_depth)
    if result.right_hand:
        wrist_depth = _depth_of(pose_mm[RIGHT_WRIST]) if pose_mm.shape[0] > RIGHT_WRIST else None
        right_hand_mm, right_conf = _lift_hand(result.right_hand, depth_mm, cam, window, wrist_depth)

    return LiftResult(
        pose_mm=pose_mm,
        confidence=confidence,
        left_hand_mm=left_hand_mm,
        right_hand_mm=right_hand_mm,
        left_hand_confidence=left_conf,
        right_hand_confidence=right_conf,
    )


def _lift_hand(
    hand: tuple[Landmark, ...],
    depth_mm: np.ndarray,
    cam: CameraModel,
    window: int,
    wrist_depth: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(hand)
    points = np.full((n, 3), np.nan, dtype=np.float32)
    conf = np.zeros((n,), dtype=np.float32)
    # Hands are small; sample their own pixels but fall back to the wrist depth
    # when a fingertip has no return (very common for thin fingers).
    hand_depth = sample_depth(
        depth_mm,
        hand[HAND_WRIST].x * cam.width,
        hand[HAND_WRIST].y * cam.height,
        window,
    )
    fallback = hand_depth or wrist_depth
    for i, lm in enumerate(hand):
        point, score = _lift(lm, depth_mm, cam, window, fallback_mm=fallback)
        points[i] = point
        conf[i] = score
    return points, conf


__all__ = ["CameraModel", "LiftResult", "lift_pose", "sample_depth"]