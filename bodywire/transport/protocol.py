"""``bodywire/1`` UDP wire format.

One datagram per frame. All integers are little-endian.

Header (24 bytes)
-----------------
======  ====  =====================================================
offset  size  field
======  ====  =====================================================
0       4     magic ``BWR1``
4       1     version (1)
5       1     flags (reserved, 0)
6       1     body_count
7       1     joint_count (32)
8       8     frame_id (u64)
16      8     timestamp_us (u64, device clock)
======  ====  =====================================================

Body record, repeated ``body_count`` times
------------------------------------------
======  ====  =====================================================
offset  size  field
======  ====  =====================================================
0       1     body_id
1       1     tracking_state (0 not tracked, 1 inferred, 2 tracked)
2       1     joint_count
3       1     reserved
4       16*N  joints, see below
======  ====  =====================================================

Joint, 16 bytes, k4abt order
----------------------------
======  ====  =====================================================
offset  size  field
======  ====  =====================================================
0       4     x_mm (i32)
4       4     y_mm (i32)
8       4     z_mm (i32)
12      1     confidence (0..3)
13      3     reserved
======  ====  =====================================================

Coordinates are millimetres in a right-handed frame with +X right, +Y down and
+Z forward, origin at the active camera. A packet with one body is 540 bytes,
comfortably below the typical 1472-byte payload limit.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable

from ..skeleton.k4abt import (
    JOINT_COUNT,
    BodyTrackingState,
    ConfidenceLevel,
    JOINT_NAMES,
    Skeleton,
    SkeletonBody,
)

MAGIC = b"BWR1"
CONTROL_MAGIC = b"BWC1"
VERSION = 1
DEFAULT_PORT = 9871
_MAX_BODIES = 255

_HEADER = struct.Struct("<4sBBBBQQ")
_JOINT = struct.Struct("<iiiB3x")
_BODY_HEADER = struct.Struct("<BBBB")
_CONTROL = struct.Struct("<4sBBH")

assert _HEADER.size == 24
assert _JOINT.size == 16
assert _CONTROL.size == 8


class ControlType(IntEnum):
    CALIBRATION = 1
    HEARTBEAT = 2


def _mm(value: float) -> int:
    """Round to millimetres, mapping NaN/inf to 0 (invalid joint)."""
    if value != value or value in (float("inf"), float("-inf")):
        return 0
    return int(round(value))


@dataclass(frozen=True)
class Body:
    """Wire representation of one body (decoded positions only)."""

    body_id: int
    joints_mm: tuple[tuple[int, int, int], ...]
    confidence: tuple[int, ...]
    tracking_state: int = int(BodyTrackingState.TRACKED)

    def __post_init__(self) -> None:
        if len(self.joints_mm) != JOINT_COUNT:
            raise ValueError(f"expected {JOINT_COUNT} joints, got {len(self.joints_mm)}")
        if len(self.confidence) != JOINT_COUNT:
            raise ValueError(f"expected {JOINT_COUNT} confidence values, got {len(self.confidence)}")

    @classmethod
    def from_skeleton(cls, body: SkeletonBody) -> "Body":
        joints = tuple((_mm(x), _mm(y), _mm(z)) for x, y, z in body.skeleton.positions)
        confidence = tuple(int(c) for c in body.skeleton.confidence)
        return cls(
            body_id=int(body.body_id),
            joints_mm=joints,
            confidence=confidence,
            tracking_state=int(body.tracking_state),
        )

    def to_skeleton(self) -> SkeletonBody:
        return SkeletonBody(
            body_id=self.body_id,
            skeleton=Skeleton(
                positions=[(float(x), float(y), float(z)) for x, y, z in self.joints_mm],
                confidence=[ConfidenceLevel(c) for c in self.confidence],
            ),
            tracking_state=BodyTrackingState(self.tracking_state),
        )

    def joint(self, name: str) -> tuple[tuple[int, int, int], int]:
        """Look a joint up by k4abt name, e.g. ``"HAND_LEFT"``."""
        index = JOINT_NAMES.index(name)
        return self.joints_mm[index], self.confidence[index]


@dataclass(frozen=True)
class SkeletonFrame:
    frame_id: int
    timestamp_us: int
    bodies: tuple[Body, ...] = field(default_factory=tuple)
    flags: int = 0

    def __post_init__(self) -> None:
        if not 0 <= len(self.bodies) <= _MAX_BODIES:
            raise ValueError(f"body count must be 0..{_MAX_BODIES}, got {len(self.bodies)}")


def pack_frame(frame: SkeletonFrame) -> bytes:
    """Serialise a frame to a single UDP payload."""
    if len(frame.bodies) > _MAX_BODIES:
        raise ValueError("too many bodies")
    parts = [
        _HEADER.pack(
            MAGIC,
            VERSION,
            frame.flags & 0xFF,
            len(frame.bodies),
            JOINT_COUNT,
            frame.frame_id & 0xFFFFFFFFFFFFFFFF,
            frame.timestamp_us & 0xFFFFFFFFFFFFFFFF,
        )
    ]
    for body in frame.bodies:
        parts.append(
            _BODY_HEADER.pack(
                body.body_id & 0xFF,
                body.tracking_state & 0xFF,
                len(body.joints_mm),
                0,
            )
        )
        for (x, y, z), conf in zip(body.joints_mm, body.confidence):
            parts.append(_JOINT.pack(int(x), int(y), int(z), int(conf) & 0xFF))
    return b"".join(parts)


def unpack_frame(data: bytes) -> SkeletonFrame:
    """Parse a datagram previously produced by :func:`pack_frame`."""
    if len(data) < _HEADER.size:
        raise ValueError("packet too short")
    magic, version, flags, body_count, joint_count, frame_id, timestamp_us = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"bad magic: {magic!r}")
    if version != VERSION:
        raise ValueError(f"unsupported version: {version}")
    if joint_count != JOINT_COUNT:
        raise ValueError(f"expected {JOINT_COUNT} joints, packet declares {joint_count}")

    offset = _HEADER.size
    bodies: list[Body] = []
    for _ in range(body_count):
        if offset + _BODY_HEADER.size > len(data):
            raise ValueError("truncated body header")
        body_id, state, n_joints, _reserved = _BODY_HEADER.unpack_from(data, offset)
        offset += _BODY_HEADER.size
        if n_joints != JOINT_COUNT:
            raise ValueError(f"body declares {n_joints} joints")
        need = n_joints * _JOINT.size
        if offset + need > len(data):
            raise ValueError("truncated joint payload")
        joints: list[tuple[int, int, int]] = []
        confidence: list[int] = []
        for _ in range(n_joints):
            x, y, z, conf = _JOINT.unpack_from(data, offset)
            offset += _JOINT.size
            joints.append((x, y, z))
            confidence.append(conf)
        bodies.append(
            Body(
                body_id=body_id,
                joints_mm=tuple(joints),
                confidence=tuple(confidence),
                tracking_state=state,
            )
        )
    if offset != len(data):
        raise ValueError(f"trailing bytes: {len(data) - offset}")
    return SkeletonFrame(
        frame_id=frame_id,
        timestamp_us=timestamp_us,
        bodies=tuple(bodies),
        flags=flags,
    )


def pack_control(kind: int | ControlType, payload: dict[str, Any] | None = None) -> bytes:
    """Serialise a ``BWC1`` control datagram (calibration / heartbeat)."""
    body = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > 0xFFFF:
        raise ValueError("control payload too large")
    return _CONTROL.pack(CONTROL_MAGIC, VERSION, int(kind), len(body)) + body


def unpack_control(data: bytes) -> tuple[ControlType, dict[str, Any]]:
    """Parse a ``BWC1`` control datagram."""
    if len(data) < _CONTROL.size:
        raise ValueError("control packet too short")
    magic, version, kind, length = _CONTROL.unpack_from(data, 0)
    if magic != CONTROL_MAGIC:
        raise ValueError(f"bad control magic: {magic!r}")
    if version != VERSION:
        raise ValueError(f"unsupported control version: {version}")
    body = data[_CONTROL.size : _CONTROL.size + length]
    if len(body) != length:
        raise ValueError("truncated control payload")
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid control JSON: {exc}") from exc
    return ControlType(kind), payload


def is_control(data: bytes) -> bool:
    return data[:4] == CONTROL_MAGIC


__all__ = [
    "CONTROL_MAGIC",
    "DEFAULT_PORT",
    "MAGIC",
    "VERSION",
    "Body",
    "ControlType",
    "SkeletonFrame",
    "is_control",
    "pack_control",
    "pack_frame",
    "unpack_control",
    "unpack_frame",
]