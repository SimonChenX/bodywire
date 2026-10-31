"""k4abt-compatible skeleton primitives.

The ordering, naming and coordinate conventions deliberately mirror the Azure
Kinect Body Tracking SDK so that consumers written against ``k4abt`` can be
re-pointed at bodywire with minimal changes:

* 32 joints, index order identical to ``k4abt_joint_id_t``.
* Positions are millimetres in a right-handed frame: +X right, +Y down,
  +Z forward, origin at the active camera (depth camera after alignment).
* ``ConfidenceLevel`` uses the same 0..3 scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Sequence


class Joint(IntEnum):
    """``k4abt_joint_id_t`` in the same order."""

    PELVIS = 0
    SPINE_NAVEL = 1
    SPINE_CHEST = 2
    NECK = 3
    CLAVICLE_LEFT = 4
    SHOULDER_LEFT = 5
    ELBOW_LEFT = 6
    WRIST_LEFT = 7
    HAND_LEFT = 8
    HANDTIP_LEFT = 9
    THUMB_LEFT = 10
    CLAVICLE_RIGHT = 11
    SHOULDER_RIGHT = 12
    ELBOW_RIGHT = 13
    WRIST_RIGHT = 14
    HAND_RIGHT = 15
    HANDTIP_RIGHT = 16
    THUMB_RIGHT = 17
    HIP_LEFT = 18
    KNEE_LEFT = 19
    ANKLE_LEFT = 20
    FOOT_LEFT = 21
    HIP_RIGHT = 22
    KNEE_RIGHT = 23
    ANKLE_RIGHT = 24
    FOOT_RIGHT = 25
    HEAD = 26
    NOSE = 27
    EYE_LEFT = 28
    EAR_LEFT = 29
    EYE_RIGHT = 30
    EAR_RIGHT = 31


JOINT_COUNT = len(Joint)
JOINT_NAMES: tuple[str, ...] = tuple(j.name for j in Joint)


class ConfidenceLevel(IntEnum):
    """``k4abt_joint_confidence_level_t``."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class Skeleton:
    """Single-person skeleton: one position in mm and confidence per joint."""

    positions: Sequence[tuple[float, float, float]] = field(default_factory=lambda: [(0.0, 0.0, 0.0)] * JOINT_COUNT)
    confidence: Sequence[ConfidenceLevel] = field(default_factory=lambda: [ConfidenceLevel.NONE] * JOINT_COUNT)

    def __post_init__(self) -> None:
        if len(self.positions) != JOINT_COUNT:
            raise ValueError(f"expected {JOINT_COUNT} joint positions, got {len(self.positions)}")
        if len(self.confidence) != JOINT_COUNT:
            raise ValueError(f"expected {JOINT_COUNT} confidence values, got {len(self.confidence)}")

    @classmethod
    def from_pairs(
        cls,
        positions: Iterable[Sequence[float]],
        confidence: Iterable[int] | None = None,
    ) -> "Skeleton":
        pos = [tuple(float(v) for v in p) for p in positions]
        if confidence is None:
            conf = [ConfidenceLevel.LOW] * len(pos)
        else:
            conf = [ConfidenceLevel(int(c)) for c in confidence]
        return cls(positions=pos, confidence=conf)

    def joint(self, joint: Joint) -> tuple[tuple[float, float, float], ConfidenceLevel]:
        i = int(joint)
        return self.positions[i], self.confidence[i]

    def as_dict(self) -> dict:
        return {
            "joints": [
                {
                    "id": int(j),
                    "name": j.name,
                    "x": round(self.positions[int(j)][0], 3),
                    "y": round(self.positions[int(j)][1], 3),
                    "z": round(self.positions[int(j)][2], 3),
                    "confidence": int(self.confidence[int(j)]),
                }
                for j in Joint
            ]
        }


class BodyTrackingState(IntEnum):
    """``k4abt_body_tracking_state_t``."""

    NOT_TRACKED = 0
    INFERRED = 1
    TRACKED = 2


@dataclass(frozen=True)
class SkeletonBody:
    """One tracked body inside a frame (k4abt ``k4abt_body_t``-like)."""

    body_id: int
    skeleton: Skeleton
    tracking_state: BodyTrackingState = BodyTrackingState.TRACKED


__all__ = [
    "BodyTrackingState",
    "ConfidenceLevel",
    "JOINT_COUNT",
    "JOINT_NAMES",
    "Joint",
    "Skeleton",
    "SkeletonBody",
]