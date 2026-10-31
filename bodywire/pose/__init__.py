"""Pose layer: 2D landmarks from MediaPipe Pose (33) plus Hands (21/hand).

Planned interface (M1)::

    detector = MediaPipePose()
    result = detector.detect(color_bgr)      # -> PoseResult | None
    points_3d = lift_to_3d(result, depth_mm, intrinsic)

Keeping the dataclasses here means the capture, skeleton and transport layers
never import MediaPipe directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Landmark:
    """Normalised image landmark, MediaPipe convention."""

    x: float
    y: float
    z: float
    visibility: float = 1.0


@dataclass(frozen=True)
class PoseResult:
    """One person: 33 pose landmarks + optional per-hand landmarks."""

    pose: tuple[Landmark, ...]
    left_hand: tuple[Landmark, ...] = ()
    right_hand: tuple[Landmark, ...] = ()
    score: float = 0.0

    def pixel(self, index: int, width: int, height: int) -> tuple[float, float]:
        lm = self.pose[index]
        return lm.x * width, lm.y * height


@dataclass
class PoseFrame:
    """Raw 2D result paired with the depth frame it belongs to."""

    result: PoseResult | None
    depth_mm: np.ndarray | None
    intrinsic: object | None = None


__all__ = ["Landmark", "PoseFrame", "PoseResult"]