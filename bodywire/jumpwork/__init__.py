"""JUMPWORK pose-service protocol (``jumpworker_pose.exe`` replacement).

JUMPWORK does not read the camera directly. It starts a local service, waits
for ``%TEMP%\\jumporin_shared_memory`` to contain ``python service is ok``, then
talks JSON-over-WebSocket with AES-128-CBC encrypted text frames.

This package implements the server side of that protocol on top of bodywire's
UDP skeleton stream, so JUMPWORK can run on an Astra+ without ``k4a``.
"""

from .mapping import JUMPWORK_JOINTS, k4abt_to_jumpwork
from .protocol import DEFAULT_IV, DEFAULT_KEY, decrypt_json, encrypt_json, handle_request

__all__ = [
    "DEFAULT_IV",
    "DEFAULT_KEY",
    "JUMPWORK_JOINTS",
    "decrypt_json",
    "encrypt_json",
    "handle_request",
    "k4abt_to_jumpwork",
]