"""Temporal filtering and short-term hold for skeletons.

Raw per-frame landmarks jitter by several centimetres. A One Euro filter
removes jitter while staying responsive during fast motion (it lowers the
cutoff when the signal is slow). Joints that disappear for a few frames keep
their last value, then drop to ``NONE`` confidence.
"""

from __future__ import annotations

import math
import time

import numpy as np

from .k4abt import JOINT_COUNT, ConfidenceLevel, Skeleton


class OneEuroFilter:
    """Scalar One Euro filter (Casiez et al. 2012)."""

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x_prev: float | None = None
        self._dx_prev = 0.0
        self._t_prev: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, x: float, t: float | None = None) -> float:
        t = time.perf_counter() if t is None else t
        if self._t_prev is None or self._x_prev is None:
            self._t_prev = t
            self._x_prev = x
            self._dx_prev = 0.0
            return x
        dt = max(1e-3, t - self._t_prev)
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


class SkeletonFilter:
    """Per-joint One Euro filter with a short hold on dropped joints."""

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        hold_ms: float = 250.0,
        reset_after_s: float = 1.0,
    ) -> None:
        self.hold_s = hold_ms / 1000.0
        self.reset_after_s = reset_after_s
        self._filters = [
            [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(3)]
            for _ in range(JOINT_COUNT)
        ]
        self._last = np.full((JOINT_COUNT, 3), np.nan, dtype=np.float32)
        self._last_seen = np.full((JOINT_COUNT,), -1e9, dtype=np.float64)

    def reset(self) -> None:
        for row in self._filters:
            for f in row:
                f.reset()
        self._last.fill(np.nan)
        self._last_seen.fill(-1e9)

    def update(self, skeleton: Skeleton, timestamp_s: float | None = None) -> Skeleton:
        t = time.perf_counter() if timestamp_s is None else float(timestamp_s)
        positions: list[tuple[float, float, float]] = []
        confidence: list[ConfidenceLevel] = []

        for j in range(JOINT_COUNT):
            point = np.asarray(skeleton.positions[j], dtype=np.float64)
            conf = skeleton.confidence[j]
            seen = bool(np.isfinite(point).all()) and conf != ConfidenceLevel.NONE

            if seen:
                filtered = np.array(
                    [self._filters[j][axis](float(point[axis]), t) for axis in range(3)],
                    dtype=np.float32,
                )
                self._last[j] = filtered
                self._last_seen[j] = t
                positions.append((float(filtered[0]), float(filtered[1]), float(filtered[2])))
                confidence.append(conf)
                continue

            age = t - float(self._last_seen[j])
            if age <= self.hold_s and np.isfinite(self._last[j]).all():
                held = self._last[j]
                positions.append((float(held[0]), float(held[1]), float(held[2])))
                confidence.append(ConfidenceLevel.NONE)
            else:
                self._last[j] = np.nan
                positions.append((0.0, 0.0, 0.0))
                confidence.append(ConfidenceLevel.NONE)

        return Skeleton(positions=positions, confidence=confidence)

    def visible_ratio(self, skeleton: Skeleton) -> float:
        return sum(1 for c in skeleton.confidence if c != ConfidenceLevel.NONE) / JOINT_COUNT


__all__ = ["OneEuroFilter", "SkeletonFilter"]