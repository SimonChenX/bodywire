import struct

import pytest

from bodywire.skeleton.k4abt import JOINT_COUNT, ConfidenceLevel, Joint, Skeleton, SkeletonBody
from bodywire.transport.protocol import (
    MAGIC,
    VERSION,
    Body,
    SkeletonFrame,
    pack_frame,
    unpack_frame,
)


def _body(body_id: int = 1, z: int = 2000) -> Body:
    joints = [(0, 0, 0)] * JOINT_COUNT
    joints[int(Joint.HEAD)] = (10, -20, z)
    conf = [int(ConfidenceLevel.LOW)] * JOINT_COUNT
    conf[int(Joint.HEAD)] = int(ConfidenceLevel.HIGH)
    return Body(body_id=body_id, joints_mm=tuple(joints), confidence=tuple(conf))


def test_one_body_packet_size():
    frame = SkeletonFrame(frame_id=1, timestamp_us=123, bodies=(_body(),))
    packet = pack_frame(frame)
    assert len(packet) == 24 + 4 + 32 * 16 == 540


def test_roundtrip_single_body():
    original = SkeletonFrame(frame_id=42, timestamp_us=1_700_000_000_000, bodies=(_body(z=2345),))
    decoded = unpack_frame(pack_frame(original))
    assert decoded.frame_id == 42
    assert decoded.timestamp_us == 1_700_000_000_000
    assert len(decoded.bodies) == 1
    body = decoded.bodies[0]
    assert body.body_id == 1
    assert body.joint("HEAD")[0] == (10, -20, 2345)
    assert body.joint("HEAD")[1] == int(ConfidenceLevel.HIGH)


def test_header_fields():
    packet = pack_frame(SkeletonFrame(frame_id=7, timestamp_us=8, bodies=()))
    magic, version, flags, body_count, joint_count, frame_id, ts = struct.unpack_from("<4sBBBBQQ", packet)
    assert magic == MAGIC
    assert version == VERSION
    assert body_count == 0
    assert joint_count == JOINT_COUNT
    assert frame_id == 7
    assert ts == 8


def test_roundtrip_empty_frame():
    decoded = unpack_frame(pack_frame(SkeletonFrame(frame_id=1, timestamp_us=2)))
    assert decoded.bodies == ()


def test_roundtrip_multiple_bodies():
    frame = SkeletonFrame(frame_id=3, timestamp_us=4, bodies=(_body(1, 1000), _body(2, 1500)))
    decoded = unpack_frame(pack_frame(frame))
    assert [b.body_id for b in decoded.bodies] == [1, 2]
    assert decoded.bodies[1].joint("HEAD")[0][2] == 1500


def test_reject_bad_magic():
    packet = bytearray(pack_frame(SkeletonFrame(frame_id=1, timestamp_us=1)))
    packet[0:4] = b"XXXX"
    with pytest.raises(ValueError, match="bad magic"):
        unpack_frame(bytes(packet))


def test_reject_truncated():
    packet = pack_frame(SkeletonFrame(frame_id=1, timestamp_us=1, bodies=(_body(),)))
    with pytest.raises(ValueError):
        unpack_frame(packet[:-1])


def test_reject_short():
    with pytest.raises(ValueError, match="too short"):
        unpack_frame(b"BWR1")


def test_reject_trailing_bytes():
    packet = pack_frame(SkeletonFrame(frame_id=1, timestamp_us=1)) + b"\x00"
    with pytest.raises(ValueError, match="trailing"):
        unpack_frame(packet)


def test_body_from_skeleton():
    skel = Skeleton.from_pairs([(1.4, -2.6, 3000.0)] * JOINT_COUNT)
    body = Body.from_skeleton(SkeletonBody(body_id=9, skeleton=skel))
    assert body.joints_mm[0] == (1, -3, 3000)  # round-to-nearest
    restored = body.to_skeleton()
    assert restored.body_id == 9
    assert restored.skeleton.positions[0] == (1.0, -3.0, 3000.0)


def test_body_from_skeleton_sanitises_non_finite():
    positions = [(0.0, 0.0, 0.0)] * JOINT_COUNT
    positions[0] = (float("nan"), float("inf"), 1234.6)
    skel = Skeleton.from_pairs(positions)
    body = Body.from_skeleton(SkeletonBody(body_id=1, skeleton=skel))
    assert body.joints_mm[0] == (0, 0, 1235)
