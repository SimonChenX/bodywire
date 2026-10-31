"""Serve JUMPWORK's pose-service protocol from bodywire's UDP stream.

Typical use::

    bodywire run --host 127.0.0.1 --port 9871
    bodywire jumpwork --port 11102 --bodywire-port 9871

``bodywire jumpwork`` writes ``%TEMP%\\jumporin_shared_memory`` so JUMPWORK
stops waiting and connects to ``ws://localhost:11102``.
"""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
from pathlib import Path

from ..receiver import SkeletonReceiver
from ..skeleton.k4abt import Skeleton
from .mapping import JUMPWORK_JOINT_COUNT, k4abt_to_jumpwork
from .protocol import (
    DEFAULT_KEY,
    SessionState,
    decrypt_json,
    encrypt_json,
    handle_request,
)

FLAG_TEXT = "python service is ok"


def flag_path() -> Path:
    return Path(tempfile.gettempdir()) / "jumporin_shared_memory"


class SkeletonStore:
    """Latest 18-joint snapshot, fed by a bodywire UDP receiver thread."""

    def __init__(
        self,
        bodywire_port: int = 9871,
        host: str = "0.0.0.0",
        hold_s: float = 0.5,
        stale_s: float = 2.0,
    ) -> None:
        self.bodywire_port = bodywire_port
        self.host = host
        self.hold_s = hold_s
        self.stale_s = stale_s
        self._points = [[0.0, 0.0, 0.0] for _ in range(JUMPWORK_JOINT_COUNT)]
        self._seen = [0.0] * JUMPWORK_JOINT_COUNT
        self._last_update = 0.0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.frames = 0
        self.bodies = 0
        self.update_time_ms = 0.0
        self._last_ingest = 0.0

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="bodywire-udp", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    # -- receive loop ----------------------------------------------------
    def _loop(self) -> None:
        receiver = SkeletonReceiver(port=self.bodywire_port, host=self.host, timeout=0.5)
        try:
            while not self._stop.is_set():
                frame = receiver.poll(timeout=0.5)
                if frame is None:
                    continue
                self.frames += 1
                if not frame.bodies:
                    continue
                self.bodies += 1
                skeleton = frame.bodies[0].to_skeleton().skeleton
                self._ingest(skeleton)
        except OSError:
            pass
        finally:
            receiver.close()

    def _ingest(self, skeleton: Skeleton) -> None:
        points, valid = k4abt_to_jumpwork(skeleton)
        now = time.perf_counter()
        if self._last_update:
            dt_ms = (now - self._last_update) * 1000.0
            self.update_time_ms = 0.9 * self.update_time_ms + 0.1 * dt_ms
        with self._lock:
            for i, (point, ok) in enumerate(zip(points, valid)):
                if ok:
                    self._points[i] = point
                    self._seen[i] = now
            self._last_update = now

    # -- snapshot --------------------------------------------------------
    def snapshot(self) -> tuple[list[list[float]], float]:
        """Return ``(18 x [x,y,z], delay_seconds)``."""
        now = time.perf_counter()
        with self._lock:
            age = now - self._last_update if self._last_update else self.stale_s
            points = []
            for i, point in enumerate(self._points):
                if self._last_update and (now - self._seen[i]) <= self.hold_s:
                    points.append(list(point))
                else:
                    points.append([0.0, 0.0, 0.0])
        return points, age


async def _handler(websocket, store: SkeletonStore, verbose: bool = True) -> None:
    state = SessionState()
    peer = getattr(websocket, "remote_address", None)
    if verbose:
        print(f"[jumpwork] client connected: {peer}", flush=True)
    try:
        async for message in websocket:
            try:
                request = decrypt_json(message, DEFAULT_KEY, state.iv)
            except Exception as exc:  # noqa: BLE001 - bad frame must not kill the session
                print(f"[jumpwork] decrypt error: {exc}", flush=True)
                continue

            response, new_iv = handle_request(request, state, store.snapshot)
            await websocket.send(encrypt_json(response, DEFAULT_KEY, state.iv))
            if new_iv is not None:
                state.iv = new_iv
            if verbose and request.get("request") not in ("Get Ske Data",):
                print(f"[jumpwork] {request.get('request')} -> {response.get('status', response.get('response'))}", flush=True)
    except Exception as exc:  # noqa: BLE001 - connection closed
        if verbose:
            print(f"[jumpwork] session ended: {exc}", flush=True)
    finally:
        if verbose:
            print(f"[jumpwork] client disconnected: {peer}", flush=True)


async def serve(
    port: int = 11102,
    host: str = "0.0.0.0",
    bodywire_port: int = 9871,
    write_flag: bool = True,
    verbose: bool = True,
) -> None:
    import websockets

    store = SkeletonStore(bodywire_port=bodywire_port, host="0.0.0.0")
    store.start()

    path = flag_path()
    if write_flag:
        path.write_text(FLAG_TEXT, encoding="utf-8")
        if verbose:
            print(f"[jumpwork] flag written: {path}", flush=True)

    async def handler(websocket):
        await _handler(websocket, store, verbose=verbose)

    try:
        async with websockets.serve(handler, host, port, max_size=None):
            if verbose:
                print(
                    f"[jumpwork] listening ws://{host}:{port} "
                    f"(bodywire udp {bodywire_port})",
                    flush=True,
                )
            await asyncio.Future()
    finally:
        store.stop()
        if write_flag:
            try:
                path.unlink()
            except OSError:
                pass


def run(
    port: int = 11102,
    host: str = "0.0.0.0",
    bodywire_port: int = 9871,
    write_flag: bool = True,
    verbose: bool = True,
) -> int:
    try:
        asyncio.run(serve(port=port, host=host, bodywire_port=bodywire_port, write_flag=write_flag, verbose=verbose))
    except KeyboardInterrupt:
        print("\n[jumpwork] stopped", flush=True)
    return 0


__all__ = ["FLAG_TEXT", "SkeletonStore", "flag_path", "run", "serve"]