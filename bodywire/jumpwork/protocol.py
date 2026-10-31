"""Wire protocol spoken by JUMPWORK's ``jumpworker_pose.exe``.

Reverse-engineered from ``Assembly-CSharp.dll`` (``MotionDemo`` namespace):

* transport: WebSocket, text frames
* each frame is ``base64(AES-128-CBC(UTF-8 JSON, PKCS#7))``
* initial key/IV: ``1234567890202473`` / ``1234567890123456``
* handshake: client sends ``Request Random IV``; server replies
  ``{"response": "finish", "new_iv": "<base64>"}`` (encrypted with the **old**
  IV), then both sides switch to the new IV
* every response echoes the request's ``requestId``

The message set used in motion-capture mode is small: ``Init Camera``,
``Start Camera``, ``Stop Camera``, ``Send Ske Data``, ``Get Ske Data`` and
``Get Update Count And Time``.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_KEY = b"1234567890202473"
DEFAULT_IV = b"1234567890123456"

Snapshot = Callable[[], tuple[list[list[float]], float]]


def _cipher(key: bytes, iv: bytes):
    return Cipher(algorithms.AES(key), modes.CBC(iv))


def encrypt_json(payload: dict[str, Any], key: bytes = DEFAULT_KEY, iv: bytes = DEFAULT_IV) -> str:
    """JSON -> AES-CBC/PKCS7 -> base64 (the exact client format)."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    encryptor = _cipher(key, iv).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")


def decrypt_json(text: str, key: bytes = DEFAULT_KEY, iv: bytes = DEFAULT_IV) -> dict[str, Any]:
    """base64 -> AES-CBC/PKCS7 -> JSON."""
    raw = base64.b64decode(text)
    decryptor = _cipher(key, iv).decryptor()
    padded = decryptor.update(raw) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    raw_json = unpadder.update(padded) + unpadder.finalize()
    return json.loads(raw_json.decode("utf-8"))


@dataclass
class SessionState:
    """Per-connection state."""

    iv: bytes = DEFAULT_IV
    camera_mode: int = 0
    started: bool = False
    streaming: bool = False
    requests: int = 0
    connected_at: float = field(default_factory=time.perf_counter)

    def reset(self) -> None:
        self.iv = DEFAULT_IV
        self.camera_mode = 0
        self.started = False
        self.streaming = False


def _ok(request_id: Any) -> dict[str, Any]:
    return {"status": "ok", "requestId": request_id}


def handle_request(
    request: dict[str, Any],
    state: SessionState,
    snapshot: Snapshot,
) -> tuple[dict[str, Any], bytes | None]:
    """Handle one decrypted request.

    Returns ``(response, new_iv)``. ``new_iv`` is set only for
    ``Request Random IV``; the response itself must be encrypted with the old
    IV before the session switches.
    """
    state.requests += 1
    # The client adds "request_id" but matches responses on "requestId"; echo both.
    rid = request.get("requestId", request.get("request_id"))
    name = str(request.get("request", ""))

    def out(payload: dict[str, Any], new_iv: bytes | None = None):
        payload["requestId"] = rid
        payload["request_id"] = rid
        return payload, new_iv

    if name == "Request Random IV":
        new_iv = os.urandom(16)
        return out(
            {"response": "finish", "new_iv": base64.b64encode(new_iv).decode("ascii")},
            new_iv,
        )

    if name == "Init Camera":
        state.camera_mode = int(request.get("camera_mode", 0) or 0)
        return out(_ok(rid))

    if name == "Start Camera":
        state.started = True
        return out(_ok(rid))

    if name == "Stop Camera":
        state.started = False
        state.streaming = False
        return out(_ok(rid))

    if name == "Send Ske Data":
        state.streaming = True
        return out(_ok(rid))

    if name == "Get Ske Data":
        joints, delay = snapshot()
        return out(
            {
                "timestamp": int(time.time() * 1000),
                "delay": float(delay),
                "ske_data": joints,
            }
        )

    if name == "Get Update Count And Time":
        _, delay = snapshot()
        return out(
            {
                "update_count": state.requests,
                "update_time": float(delay * 1000.0),
            }
        )

    # VR / alignment / tracker requests are accepted but not implemented.
    return out(_ok(rid))


__all__ = [
    "DEFAULT_IV",
    "DEFAULT_KEY",
    "SessionState",
    "decrypt_json",
    "encrypt_json",
    "handle_request",
]