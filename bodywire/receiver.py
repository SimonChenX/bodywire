"""Reference Python receiver for the ``bodywire/1`` UDP protocol."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Iterator

from .transport.protocol import (
    DEFAULT_PORT,
    ControlType,
    SkeletonFrame,
    is_control,
    unpack_control,
    unpack_frame,
)


@dataclass
class ReceiverState:
    calibration: dict | None = None
    heartbeat: dict | None = None
    frames: int = 0
    controls: int = 0
    parse_errors: int = 0
    last_sender: tuple[str, int] | None = None
    peer_calibrations: dict[tuple[str, int], dict] = field(default_factory=dict)


class SkeletonReceiver:
    """Listens for skeleton + control datagrams on one UDP port."""

    def __init__(self, port: int = DEFAULT_PORT, host: str = "0.0.0.0", timeout: float = 1.0) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.settimeout(timeout)
        self.state = ReceiverState()

    @property
    def port(self) -> int:
        return int(self._sock.getsockname()[1])

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "SkeletonReceiver":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def poll(self, timeout: float | None = None) -> SkeletonFrame | None:
        """Return the next skeleton frame, updating calibration state.

        Control datagrams are consumed transparently. Returns ``None`` on
        timeout; malformed datagrams are counted and skipped.
        """
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            data, addr = self._sock.recvfrom(65535)
        except socket.timeout:
            return None
        except OSError:
            return None

        self.state.last_sender = addr
        if is_control(data):
            try:
                kind, payload = unpack_control(data)
            except ValueError:
                self.state.parse_errors += 1
                return None
            self.state.controls += 1
            if kind == ControlType.CALIBRATION:
                self.state.calibration = payload
                self.state.peer_calibrations[addr] = payload
            elif kind == ControlType.HEARTBEAT:
                self.state.heartbeat = payload
            return None

        try:
            frame = unpack_frame(data)
        except ValueError:
            self.state.parse_errors += 1
            return None
        self.state.frames += 1
        return frame

    def frames(self) -> Iterator[SkeletonFrame]:
        while True:
            frame = self.poll()
            if frame is not None:
                yield frame


__all__ = ["ReceiverState", "SkeletonReceiver"]