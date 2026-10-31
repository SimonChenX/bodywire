import socket

import pytest

from bodywire.receiver import SkeletonReceiver
from bodywire.skeleton.k4abt import JOINT_COUNT
from bodywire.transport.protocol import (
    CONTROL_MAGIC,
    Body,
    ControlType,
    SkeletonFrame,
    is_control,
    pack_control,
    pack_frame,
    unpack_control,
)


def test_control_roundtrip():
    payload = {
        "type": "calibration",
        "aligned": True,
        "coordinate_space": "color",
        "color": {"fx": 479.32, "fy": 479.32, "cx": 320.46, "cy": 236.52, "width": 640, "height": 480},
    }
    data = pack_control(ControlType.CALIBRATION, payload)
    assert data[:4] == CONTROL_MAGIC
    assert is_control(data)
    kind, decoded = unpack_control(data)
    assert kind == ControlType.CALIBRATION
    assert decoded == payload


def test_control_rejects_bad_magic():
    data = bytearray(pack_control(ControlType.HEARTBEAT, {"fps": 30}))
    data[0:4] = b"XXXX"
    with pytest.raises(ValueError, match="bad control magic"):
        unpack_control(bytes(data))


def test_control_rejects_truncated_payload():
    data = pack_control(ControlType.CALIBRATION, {"a": "b"})
    with pytest.raises(ValueError, match="truncated"):
        unpack_control(data[:-1])


def test_receiver_handles_control_and_frames():
    receiver = SkeletonReceiver(port=0, host="127.0.0.1", timeout=0.1)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        target = ("127.0.0.1", receiver.port)
        calibration = {"type": "calibration", "aligned": True}
        sender.sendto(pack_control(ControlType.CALIBRATION, calibration), target)
        assert receiver.poll(timeout=0.5) is None
        assert receiver.state.calibration == calibration

        body = Body(
            body_id=1,
            joints_mm=tuple((0, 0, 0) for _ in range(JOINT_COUNT)),
            confidence=tuple(0 for _ in range(JOINT_COUNT)),
        )
        sender.sendto(pack_frame(SkeletonFrame(frame_id=7, timestamp_us=9, bodies=(body,))), target)
        frame = receiver.poll(timeout=0.5)
        assert frame is not None
        assert frame.frame_id == 7
        assert len(frame.bodies) == 1
        assert receiver.state.frames == 1
        assert receiver.state.controls == 1

        # A malformed datagram is counted, not raised.
        sender.sendto(b"garbage", target)
        assert receiver.poll(timeout=0.5) is None
        assert receiver.state.parse_errors == 1
    finally:
        sender.close()
        receiver.close()