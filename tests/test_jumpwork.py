import asyncio
import base64

import pytest

from bodywire.jumpwork.mapping import JUMPWORK_JOINT_COUNT, k4abt_to_jumpwork
from bodywire.jumpwork.protocol import (
    DEFAULT_IV,
    DEFAULT_KEY,
    SessionState,
    decrypt_json,
    encrypt_json,
    handle_request,
)
from bodywire.skeleton.k4abt import JOINT_COUNT, ConfidenceLevel, Joint, Skeleton


def _snapshot():
    return [[float(i), 0.5, 2.0] for i in range(JUMPWORK_JOINT_COUNT)], 0.012


def test_aes_roundtrip():
    payload = {"request": "Init Camera", "requestId": 7, "camera_mode": 1}
    text = encrypt_json(payload)
    assert isinstance(text, str)
    assert decrypt_json(text) == payload


def test_random_iv_switches_after_response():
    state = SessionState()
    response, new_iv = handle_request(
        {"request": "Request Random IV", "requestId": 1}, state, _snapshot
    )
    assert response["response"] == "finish"
    assert new_iv is not None and len(new_iv) == 16
    assert base64.b64decode(response["new_iv"]) == new_iv

    # the client decrypts with the old IV first
    decoded = decrypt_json(encrypt_json(response), DEFAULT_KEY, DEFAULT_IV)
    assert decoded["new_iv"] == response["new_iv"]

    state.iv = new_iv
    ok, _ = handle_request({"request": "Init Camera", "requestId": 2, "camera_mode": 1}, state, _snapshot)
    assert ok["status"] == "ok" and ok["requestId"] == 2 and ok["request_id"] == 2
    assert state.camera_mode == 1


def test_camera_and_stream_lifecycle():
    state = SessionState()
    assert handle_request({"request": "Start Camera", "requestId": 1}, state, _snapshot)[0]["status"] == "ok"
    assert state.started
    assert handle_request({"request": "Send Ske Data", "requestId": 2}, state, _snapshot)[0]["status"] == "ok"
    assert state.streaming

    frame, _ = handle_request({"request": "Get Ske Data", "requestId": 3}, state, _snapshot)
    assert frame["requestId"] == 3
    assert len(frame["ske_data"]) == JUMPWORK_JOINT_COUNT
    assert all(len(point) == 3 for point in frame["ske_data"])
    assert frame["delay"] == pytest.approx(0.012)
    assert isinstance(frame["timestamp"], int)

    assert handle_request({"request": "Stop Camera", "requestId": 4}, state, _snapshot)[0]["status"] == "ok"
    assert not state.started and not state.streaming


def test_unknown_request_is_acknowledged():
    response, new_iv = handle_request({"request": "Three Point Align", "requestId": 9}, SessionState(), _snapshot)
    assert response["status"] == "ok" and response["requestId"] == 9
    assert new_iv is None


def test_mapping_converts_to_unity_metres():
    positions = [(0.0, 0.0, 0.0)] * JOINT_COUNT
    positions[int(Joint.PELVIS)] = (100.0, 200.0, 2000.0)
    positions[int(Joint.HEAD)] = (0.0, -100.0, 1800.0)
    confidence = [ConfidenceLevel.HIGH] * JOINT_COUNT
    skel = Skeleton(positions=positions, confidence=confidence)

    points, valid = k4abt_to_jumpwork(skel)
    assert len(points) == JUMPWORK_JOINT_COUNT
    assert points[0] == [0.1, -0.2, 2.0]
    assert points[17] == [0.0, 0.1, 1.8]
    assert all(valid)


def test_mapping_marks_missing_joints():
    positions = [(0.0, 0.0, 0.0)] * JOINT_COUNT
    confidence = [ConfidenceLevel.NONE] * JOINT_COUNT
    points, valid = k4abt_to_jumpwork(Skeleton(positions=positions, confidence=confidence))
    assert not any(valid)
    assert all(point == [0.0, 0.0, 0.0] for point in points)


def test_websocket_handshake_end_to_end():
    import websockets

    from bodywire.jumpwork.service import _handler

    async def scenario():
        async with websockets.serve(lambda ws: _handler(ws, _Store(), verbose=False), "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(encrypt_json({"request": "Request Random IV", "requestId": 1}))
                iv = DEFAULT_IV
                reply = decrypt_json(await ws.recv(), DEFAULT_KEY, iv)
                assert reply["response"] == "finish"
                iv = base64.b64decode(reply["new_iv"])

                await ws.send(encrypt_json({"request": "Get Ske Data", "requestId": 2}, DEFAULT_KEY, iv))
                frame = decrypt_json(await ws.recv(), DEFAULT_KEY, iv)
                assert frame["requestId"] == 2
                assert len(frame["ske_data"]) == JUMPWORK_JOINT_COUNT

    class _Store:
        def snapshot(self):
            return _snapshot()

    asyncio.run(scenario())