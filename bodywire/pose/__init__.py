"""Pose layer: 2D landmarks from MediaPipe Pose (33) plus Hands (21 per hand).

The data classes here are the boundary between MediaPipe and the rest of
bodywire; ``skeleton`` and ``transport`` never import MediaPipe directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Landmark:
    """One landmark, MediaPipe convention.

    ``x``/``y``/``z`` are normalised image coordinates (``z`` is roughly the
    depth relative to the hips, in the same scale as ``x``). ``visibility`` and
    ``presence`` are MediaPipe confidences in ``0..1``.
    """

    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0
    presence: float = 1.0

    @property
    def score(self) -> float:
        return min(self.visibility, self.presence)


@dataclass(frozen=True)
class PoseResult:
    """One person: 33 pose landmarks, optional world landmarks and hands."""

    pose: tuple[Landmark, ...]
    world: tuple[Landmark, ...] = ()
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