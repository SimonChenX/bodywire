"""Minimal ctypes binding for the OrbbecSDK C API.

Only the surface needed by bodywire is bound: enumerating devices, starting a
depth + colour pipeline, optional hardware/software D2C alignment, and pulling
frames as NumPy arrays.

The binding is deliberately dependency-free (``ctypes`` only) because the
Orbbec Python SDK has no wheel for the Python versions we run here.

Tested against OrbbecSDK 1.10.37 with an Astra+ (PID 0x0536 / 0x0636).
"""

from __future__ import annotations

import ctypes as C
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np

try:  # cv2 is only needed to decode colour frames
    import cv2
except ImportError:  # pragma: no cover - optional at import time
    cv2 = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# Enums (values mirror libobsensor/h/ObTypes.h)
# --------------------------------------------------------------------------
OB_SENSOR_DEPTH = 3
OB_SENSOR_COLOR = 2

OB_FORMAT_YUYV = 0
OB_FORMAT_YUY2 = 1
OB_FORMAT_UYVY = 2
OB_FORMAT_NV12 = 3
OB_FORMAT_NV21 = 4
OB_FORMAT_MJPG = 5
OB_FORMAT_Y16 = 8
OB_FORMAT_Y8 = 9
OB_FORMAT_RGB = 22
OB_FORMAT_BGR = 23
OB_FORMAT_BGRA = 25
OB_FORMAT_RGBA = 31
OB_FORMAT_Z16 = 28

ALIGN_DISABLE = 0
ALIGN_D2C_HW_MODE = 1
ALIGN_D2C_SW_MODE = 2

_FORMAT_NAMES = {
    OB_FORMAT_YUYV: "YUYV",
    OB_FORMAT_YUY2: "YUY2",
    OB_FORMAT_UYVY: "UYVY",
    OB_FORMAT_NV12: "NV12",
    OB_FORMAT_NV21: "NV21",
    OB_FORMAT_MJPG: "MJPG",
    OB_FORMAT_Y16: "Y16",
    OB_FORMAT_Y8: "Y8",
    OB_FORMAT_RGB: "RGB",
    OB_FORMAT_BGR: "BGR",
    OB_FORMAT_BGRA: "BGRA",
    OB_FORMAT_RGBA: "RGBA",
    OB_FORMAT_Z16: "Z16",
}


class OrbbecError(RuntimeError):
    """Raised when the OrbbecSDK reports an error."""


# --------------------------------------------------------------------------
# Structs
# --------------------------------------------------------------------------
class CameraIntrinsic(C.Structure):
    """``ob_camera_intrinsic`` - 20 bytes, returned by value."""

    _fields_ = [
        ("fx", C.c_float),
        ("fy", C.c_float),
        ("cx", C.c_float),
        ("cy", C.c_float),
        ("width", C.c_int16),
        ("height", C.c_int16),
    ]

    def as_dict(self) -> dict[str, float | int]:
        return {
            "fx": float(self.fx),
            "fy": float(self.fy),
            "cx": float(self.cx),
            "cy": float(self.cy),
            "width": int(self.width),
            "height": int(self.height),
        }

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"CameraIntrinsic(fx={self.fx:.2f}, fy={self.fy:.2f}, "
            f"cx={self.cx:.2f}, cy={self.cy:.2f}, "
            f"{self.width}x{self.height})"
        )


class CameraDistortion(C.Structure):
    """``ob_camera_distortion`` - eight floats."""

    _fields_ = [
        ("k1", C.c_float),
        ("k2", C.c_float),
        ("k3", C.c_float),
        ("k4", C.c_float),
        ("k5", C.c_float),
        ("k6", C.c_float),
        ("p1", C.c_float),
        ("p2", C.c_float),
    ]


class D2CTransform(C.Structure):
    """``ob_d2c_transform`` - rot[9] + trans[3], millimetres."""

    _fields_ = [("rot", C.c_float * 9), ("trans", C.c_float * 3)]


class CameraParam(C.Structure):
    """``ob_camera_param`` - returned by value from the pipeline."""

    _fields_ = [
        ("depthIntrinsic", CameraIntrinsic),
        ("rgbIntrinsic", CameraIntrinsic),
        ("depthDistortion", CameraDistortion),
        ("rgbDistortion", CameraDistortion),
        ("transform", D2CTransform),
        ("isMirrored", C.c_bool),
    ]


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    pid: int
    vid: int
    uid: str
    serial_number: str
    firmware_version: str
    connection_type: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"{self.name} (pid=0x{self.pid:04x}, vid=0x{self.vid:04x}, "
            f"sn={self.serial_number}, fw={self.firmware_version}, "
            f"usb={self.connection_type})"
        )


@dataclass(frozen=True)
class StreamProfileInfo:
    sensor: int
    width: int
    height: int
    fps: int
    format: int
    _profile: int = 0  # opaque ob_stream_profile* kept for enabling

    @property
    def format_name(self) -> str:
        return _FORMAT_NAMES.get(self.format, f"0x{self.format:02x}")

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        sensor = "depth" if self.sensor == OB_SENSOR_DEPTH else "color"
        return f"{sensor} {self.width}x{self.height}@{self.fps} {self.format_name}"


@dataclass
class Frame:
    """One synchronised depth/colour pair.

    ``depth`` is float32 millimetres with invalid pixels set to ``nan``.
    ``color_bgr`` is HxWx3 uint8, or ``None`` when colour is disabled.
    """

    depth: np.ndarray | None
    color_bgr: np.ndarray | None
    depth_ts_us: int
    color_ts_us: int
    depth_index: int
    color_index: int
    depth_intrinsic: CameraIntrinsic | None
    color_intrinsic: CameraIntrinsic | None
    aligned: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def depth_shape(self) -> tuple[int, int]:
        return (0, 0) if self.depth is None else self.depth.shape[:2]


# --------------------------------------------------------------------------
# Library loading
# --------------------------------------------------------------------------
_DLL: C.CDLL | None = None
_DLL_PATH: Path | None = None


def _candidate_libraries() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("BODYWIRE_ORBBEC_SDK")
    if env:
        p = Path(env)
        candidates.append(p if p.suffix.lower() == ".dll" else p / "OrbbecSDK.dll")

    here = Path(__file__).resolve()
    # Repo-local vendored copy (not committed by default).
    for parent in here.parents:
        candidates.append(parent / "vendor" / "orbbec" / "OrbbecSDK.dll")

    candidates.extend(
        [
            Path(r"D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib\OrbbecSDK.dll"),
            Path(r"C:\Program Files\Orbbec\OrbbecSDK\lib\OrbbecSDK.dll"),
        ]
    )
    return candidates


def _load_library() -> C.CDLL:
    global _DLL, _DLL_PATH
    if _DLL is not None:
        return _DLL

    tried: list[str] = []
    for path in _candidate_libraries():
        tried.append(str(path))
        if not path.is_file():
            continue
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(path.parent))
            except OSError:
                pass
        try:
            _DLL = C.WinDLL(str(path))
            _DLL_PATH = path
            return _DLL
        except OSError as exc:  # pragma: no cover - platform specific
            raise OrbbecError(f"failed to load {path}: {exc}") from exc

    raise OrbbecError(
        "OrbbecSDK.dll not found. Set BODYWIRE_ORBBEC_SDK to the SDK lib "
        "directory. Tried:\n  " + "\n  ".join(tried)
    )


def _quiet_config() -> Path | None:
    """Return a patched SDK config that only logs warnings and errors.

    The stock config prints every INFO line to the console, which drowns the
    CLI and would flood a daemon's stdout. We copy the SDK XML once into
    ``%LOCALAPPDATA%\\bodywire`` with the log levels raised to ``WARN``.
    """
    if _DLL_PATH is None:
        return None
    for candidate in (
        _DLL_PATH.parent / "OrbbecSDKConfig_v1.0.xml",
        _DLL_PATH.parent.parent / "config" / "OrbbecSDKConfig_v1.0.xml",
    ):
        if candidate.is_file():
            src = candidate
            break
    else:
        return None

    try:
        text = src.read_text(encoding="utf-8", errors="ignore")
        for tag in ("LogLevel", "FileLogLevel", "ConsoleLogLevel"):
            text = re.sub(rf"<{tag}>\s*\d+\s*</{tag}>", f"<{tag}>3</{tag}>", text)
        cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "bodywire"
        cache.mkdir(parents=True, exist_ok=True)
        out = cache / "OrbbecSDKConfig_v1.0.xml"
        if not out.is_file() or out.read_text(encoding="utf-8", errors="ignore") != text:
            out.write_text(text, encoding="utf-8")
        return out
    except OSError:  # pragma: no cover - best effort
        return None


def _bind(lib: C.CDLL, name: str, restype, *argtypes) -> C._CFuncPtr:
    fn = getattr(lib, name)
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


class _Sdk:
    """Thin typed facade over the handful of C entry points we use."""

    def __init__(self, lib: C.CDLL) -> None:
        P = C.POINTER(C.c_void_p)
        V = C.c_void_p

        self.get_major = _bind(lib, "ob_get_major_version", C.c_int)
        self.get_minor = _bind(lib, "ob_get_minor_version", C.c_int)
        self.get_patch = _bind(lib, "ob_get_patch_version", C.c_int)
        self.get_stage = _bind(lib, "ob_get_stage_version", C.c_char_p)

        self.create_context = _bind(lib, "ob_create_context", V, P)
        self.create_context_with_config = _bind(lib, "ob_create_context_with_config", V, C.c_char_p, P)
        self.delete_context = _bind(lib, "ob_delete_context", None, V, P)
        self.query_device_list = _bind(lib, "ob_query_device_list", V, V, P)
        self.delete_device_list = _bind(lib, "ob_delete_device_list", None, V, P)
        self.device_list_count = _bind(lib, "ob_device_list_device_count", C.c_int, V, P)
        self.device_list_get = _bind(lib, "ob_device_list_get_device", V, V, C.c_int, P)
        self.delete_device = _bind(lib, "ob_delete_device", None, V, P)

        self.get_device_info = _bind(lib, "ob_device_get_device_info", V, V, P)
        self.delete_device_info = _bind(lib, "ob_delete_device_info", None, V, P)
        self.device_info_name = _bind(lib, "ob_device_info_name", C.c_char_p, V, P)
        self.device_info_pid = _bind(lib, "ob_device_info_pid", C.c_int, V, P)
        self.device_info_vid = _bind(lib, "ob_device_info_vid", C.c_int, V, P)
        self.device_info_uid = _bind(lib, "ob_device_info_uid", C.c_char_p, V, P)
        self.device_info_sn = _bind(lib, "ob_device_info_serial_number", C.c_char_p, V, P)
        self.device_info_fw = _bind(lib, "ob_device_info_firmware_version", C.c_char_p, V, P)
        self.device_info_usb = _bind(lib, "ob_device_info_connection_type", C.c_char_p, V, P)

        self.create_pipeline_with_device = _bind(lib, "ob_create_pipeline_with_device", V, V, P)
        self.delete_pipeline = _bind(lib, "ob_delete_pipeline", None, V, P)
        self.pipeline_get_config = _bind(lib, "ob_pipeline_get_config", V, V, P)
        self.pipeline_get_profile_list = _bind(lib, "ob_pipeline_get_stream_profile_list", V, V, C.c_int, P)
        self.pipeline_start_with_config = _bind(lib, "ob_pipeline_start_with_config", None, V, V, P)
        self.pipeline_stop = _bind(lib, "ob_pipeline_stop", None, V, P)
        self.pipeline_wait_for_frameset = _bind(lib, "ob_pipeline_wait_for_frameset", V, V, C.c_uint32, P)

        self.profile_list_count = _bind(lib, "ob_stream_profile_list_count", C.c_uint32, V, P)
        self.profile_list_get = _bind(lib, "ob_stream_profile_list_get_profile", V, V, C.c_int, P)
        self.profile_width = _bind(lib, "ob_video_stream_profile_width", C.c_uint32, V, P)
        self.profile_height = _bind(lib, "ob_video_stream_profile_height", C.c_uint32, V, P)
        self.profile_fps = _bind(lib, "ob_video_stream_profile_fps", C.c_uint32, V, P)
        self.profile_format = _bind(lib, "ob_stream_profile_format", C.c_int, V, P)
        self.pipeline_get_camera_param = _bind(lib, "ob_pipeline_get_camera_param", CameraParam, V, P)

        self.config_enable_stream = _bind(lib, "ob_config_enable_stream", None, V, V, P)
        self.config_set_align_mode = _bind(lib, "ob_config_set_align_mode", None, V, C.c_int, P)
        self.config_set_depth_scale = _bind(lib, "ob_config_set_depth_scale_require", None, V, C.c_bool, P)

        self.frameset_depth_frame = _bind(lib, "ob_frameset_depth_frame", V, V, P)
        self.frameset_color_frame = _bind(lib, "ob_frameset_color_frame", V, V, P)
        self.delete_frame = _bind(lib, "ob_delete_frame", None, V, P)
        self.frame_data = _bind(lib, "ob_frame_data", V, V, P)
        self.frame_data_size = _bind(lib, "ob_frame_data_size", C.c_uint32, V, P)
        self.frame_width = _bind(lib, "ob_video_frame_width", C.c_uint32, V, P)
        self.frame_height = _bind(lib, "ob_video_frame_height", C.c_uint32, V, P)
        self.frame_format = _bind(lib, "ob_frame_format", C.c_int, V, P)
        self.frame_ts_us = _bind(lib, "ob_frame_time_stamp_us", C.c_uint64, V, P)
        self.frame_index = _bind(lib, "ob_frame_index", C.c_uint64, V, P)
        self.depth_value_scale = _bind(lib, "ob_depth_frame_get_value_scale", C.c_float, V, P)

        self.error_message = _bind(lib, "ob_error_message", C.c_char_p, V)
        self.error_function = _bind(lib, "ob_error_function", C.c_char_p, V)
        self.error_args = _bind(lib, "ob_error_args", C.c_char_p, V)
        self.delete_error = _bind(lib, "ob_delete_error", None, V)

    # -- helpers ---------------------------------------------------------
    def check(self, err: C.c_void_p) -> None:
        if not err.value:
            return
        msg = self.error_message(err)
        fn = self.error_function(err)
        args = self.error_args(err)
        text = msg.decode("utf-8", "replace") if msg else "unknown error"
        where = fn.decode("utf-8", "replace") if fn else "?"
        argv = args.decode("utf-8", "replace") if args else ""
        self.delete_error(err)
        raise OrbbecError(f"{where}({argv}): {text}")

    def call(self, fn, *args):
        err = C.c_void_p()
        out = fn(*args, C.byref(err))
        self.check(err)
        return out

    def new_context(self) -> int:
        cfg = _quiet_config()
        if cfg is not None:
            try:
                return self.call(self.create_context_with_config, str(cfg).encode("utf-8"))
            except OrbbecError:
                pass
        return self.call(self.create_context)

    def version(self) -> str:
        stage = self.get_stage() or b""
        return (
            f"{self.get_major()}.{self.get_minor()}.{self.get_patch()}"
            f"-{stage.decode('utf-8', 'replace')}"
        )


def _sdk() -> _Sdk:
    return _Sdk(_load_library())


def _decode(ptr: int | None, size: int) -> bytes:
    if not ptr:
        return b""
    return C.string_at(ptr, size)


def _decode_cstr(value: bytes | None) -> str:
    return value.decode("utf-8", "replace") if value else ""


# --------------------------------------------------------------------------
# Public helpers
# --------------------------------------------------------------------------
def list_devices() -> list[DeviceInfo]:
    """Return the devices currently visible to the SDK (without opening one)."""
    sdk = _sdk()
    ctx = sdk.new_context()
    dev_list = sdk.call(sdk.query_device_list, ctx)
    try:
        count = sdk.call(sdk.device_list_count, dev_list)
        out: list[DeviceInfo] = []
        for i in range(count):
            dev = sdk.call(sdk.device_list_get, dev_list, i)
            info = sdk.call(sdk.get_device_info, dev)
            try:
                out.append(
                    DeviceInfo(
                        name=_decode_cstr(sdk.call(sdk.device_info_name, info)),
                        pid=sdk.call(sdk.device_info_pid, info),
                        vid=sdk.call(sdk.device_info_vid, info),
                        uid=_decode_cstr(sdk.call(sdk.device_info_uid, info)),
                        serial_number=_decode_cstr(sdk.call(sdk.device_info_sn, info)),
                        firmware_version=_decode_cstr(sdk.call(sdk.device_info_fw, info)),
                        connection_type=_decode_cstr(sdk.call(sdk.device_info_usb, info)),
                    )
                )
            finally:
                sdk.call(sdk.delete_device_info, info)
                sdk.call(sdk.delete_device, dev)
        return out
    finally:
        sdk.call(sdk.delete_device_list, dev_list)
        sdk.call(sdk.delete_context, ctx)


def sdk_version() -> str:
    return _sdk().version()


def _pick_profile(
    profiles: Sequence[StreamProfileInfo],
    want_w: int,
    want_h: int,
    want_fps: int = 30,
    want_formats: Sequence[int] = (),
) -> StreamProfileInfo | None:
    if not profiles:
        return None

    def score(p: StreamProfileInfo) -> tuple:
        format_ok = 0 if (not want_formats or p.format in want_formats) else 1
        res = abs(p.width - want_w) + abs(p.height - want_h) * 2
        return (format_ok, res, abs(p.fps - want_fps))

    return min(profiles, key=score)


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
class OrbbecCamera:
    """Owns an ``ob_device`` + ``ob_pipeline`` for one sensor.

    Example
    -------
    >>> with OrbbecCamera().open() as cam:          # doctest: +SKIP
    ...     for frame in cam.frames():              # doctest: +SKIP
    ...         print(frame.depth.shape)            # doctest: +SKIP
    """

    def __init__(self, device_index: int = 0) -> None:
        self._sdk = _sdk()
        self._index = device_index
        self._ctx: int | None = None
        self._dev_list: int | None = None
        self._dev: int | None = None
        self._pipeline: int | None = None
        self._config: int | None = None
        self.info: DeviceInfo | None = None
        self.depth_profile: StreamProfileInfo | None = None
        self.color_profile: StreamProfileInfo | None = None
        self.camera_param: CameraParam | None = None
        self.aligned = False
        self._started = False

    # -- lifecycle -------------------------------------------------------
    def open(self) -> "OrbbecCamera":
        s = self._sdk
        self._ctx = s.new_context()
        self._dev_list = s.call(s.query_device_list, self._ctx)
        count = s.call(s.device_list_count, self._dev_list)
        if count == 0:
            self.close()
            raise OrbbecError("no Orbbec device found (is the camera connected?)")
        if self._index >= count:
            self.close()
            raise OrbbecError(f"device index {self._index} out of range (found {count})")

        self._dev = s.call(s.device_list_get, self._dev_list, self._index)
        info = s.call(s.get_device_info, self._dev)
        try:
            self.info = DeviceInfo(
                name=_decode_cstr(s.call(s.device_info_name, info)),
                pid=s.call(s.device_info_pid, info),
                vid=s.call(s.device_info_vid, info),
                uid=_decode_cstr(s.call(s.device_info_uid, info)),
                serial_number=_decode_cstr(s.call(s.device_info_sn, info)),
                firmware_version=_decode_cstr(s.call(s.device_info_fw, info)),
                connection_type=_decode_cstr(s.call(s.device_info_usb, info)),
            )
        finally:
            s.call(s.delete_device_info, info)

        self._pipeline = s.call(s.create_pipeline_with_device, self._dev)
        self._config = s.call(s.pipeline_get_config, self._pipeline)
        return self

    def close(self) -> None:
        s = self._sdk
        if self._started:
            try:
                s.call(s.pipeline_stop, self._pipeline)
            except OrbbecError:
                pass
            self._started = False
        if self._pipeline:
            s.call(s.delete_pipeline, self._pipeline)
            self._pipeline = None
        if self._dev:
            s.call(s.delete_device, self._dev)
            self._dev = None
        if self._dev_list:
            s.call(s.delete_device_list, self._dev_list)
            self._dev_list = None
        if self._ctx:
            s.call(s.delete_context, self._ctx)
            self._ctx = None

    def __enter__(self) -> "OrbbecCamera":
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- profiles --------------------------------------------------------
    def stream_profiles(self, sensor: int) -> list[StreamProfileInfo]:
        assert self._pipeline is not None
        s = self._sdk
        plist = s.call(s.pipeline_get_profile_list, self._pipeline, sensor)
        count = s.call(s.profile_list_count, plist)
        out: list[StreamProfileInfo] = []
        for i in range(count):
            prof = s.call(s.profile_list_get, plist, i)
            out.append(
                StreamProfileInfo(
                    sensor=sensor,
                    width=int(s.call(s.profile_width, prof)),
                    height=int(s.call(s.profile_height, prof)),
                    fps=int(s.call(s.profile_fps, prof)),
                    format=int(s.call(s.profile_format, prof)),
                    _profile=int(prof or 0),
                )
            )
        return out

    # -- streaming -------------------------------------------------------
    def start(
        self,
        depth: tuple[int, int, int] = (640, 480, 30),
        color: tuple[int, int, int] | None = (640, 480, 30),
        align: bool = True,
        depth_scale_required: bool = True,
    ) -> None:
        assert self._pipeline is not None and self._config is not None
        s = self._sdk

        self.depth_profile = _pick_profile(
            self.stream_profiles(OB_SENSOR_DEPTH), *depth[:2], depth[2], (OB_FORMAT_Y16, OB_FORMAT_Z16)
        )
        if self.depth_profile is None:
            raise OrbbecError("no depth stream profile available")

        if color is not None:
            self.color_profile = _pick_profile(
                self.stream_profiles(OB_SENSOR_COLOR), *color[:2], color[2]
            )
        self.aligned = bool(align and self.color_profile is not None)

        s.call(s.config_enable_stream, self._config, self.depth_profile._profile)
        if self.color_profile is not None:
            s.call(s.config_enable_stream, self._config, self.color_profile._profile)

        if depth_scale_required:
            try:
                s.call(s.config_set_depth_scale, self._config, True)
            except OrbbecError:
                # Older UVC firmwares do not implement it; the frame scale
                # accessor still reports the correct unit.
                pass

        try:
            self._start(ALIGN_D2C_SW_MODE if self.aligned else ALIGN_DISABLE)
        except OrbbecError:
            if not self.aligned:
                raise
            # Some Astra+ firmwares reject software D2C; fall back to native
            # depth and let the caller align with intrinsics if needed.
            self.aligned = False
            self._start(ALIGN_DISABLE)

        try:
            self.camera_param = s.call(s.pipeline_get_camera_param, self._pipeline)
        except OrbbecError:
            self.camera_param = None

    def _start(self, align_mode: int) -> None:
        s = self._sdk
        s.call(s.config_set_align_mode, self._config, align_mode)
        try:
            s.call(s.pipeline_start_with_config, self._pipeline, self._config)
        except OrbbecError:
            try:
                s.call(s.pipeline_stop, self._pipeline)
            except OrbbecError:
                pass
            raise
        self._started = True

    def intrinsics(self) -> tuple[CameraIntrinsic | None, CameraIntrinsic | None]:
        """Return ``(depth_intrinsic, color_intrinsic)`` for the active mode."""
        cp = self.camera_param
        if cp is None:
            return None, None
        color = cp.rgbIntrinsic if cp.rgbIntrinsic.width else None
        if self.aligned:
            # The aligned depth map lives in the colour pixel grid.
            return color, color
        depth = cp.depthIntrinsic if cp.depthIntrinsic.width else None
        return depth, color

    def read(self, timeout_ms: int = 1000) -> Frame | None:
        """Wait for the next frameset. Returns ``None`` on timeout."""
        if not self._started:
            raise OrbbecError("camera not started; call start() first")
        s = self._sdk
        frameset = s.call(s.pipeline_wait_for_frameset, self._pipeline, timeout_ms)
        if not frameset:
            return None

        depth_frame = color_frame = None
        try:
            depth_frame = s.call(s.frameset_depth_frame, frameset)
            color_frame = s.call(s.frameset_color_frame, frameset)

            depth = color = None
            depth_ts = color_ts = 0
            depth_idx = color_idx = 0
            depth_scale = 1.0

            if depth_frame:
                w = int(s.call(s.frame_width, depth_frame))
                h = int(s.call(s.frame_height, depth_frame))
                raw = _decode(
                    s.call(s.frame_data, depth_frame),
                    int(s.call(s.frame_data_size, depth_frame)),
                )
                try:
                    depth_scale = float(s.call(s.depth_value_scale, depth_frame))
                except OrbbecError:
                    depth_scale = 1.0
                if w and h and len(raw) >= w * h * 2:
                    arr = np.frombuffer(raw, dtype=np.uint16, count=w * h).reshape(h, w)
                    depth = arr.astype(np.float32) * (depth_scale if depth_scale > 0 else 1.0)
                    depth[depth == 0] = np.nan
                depth_ts = int(s.call(s.frame_ts_us, depth_frame))
                depth_idx = int(s.call(s.frame_index, depth_frame))

            if color_frame:
                w = int(s.call(s.frame_width, color_frame))
                h = int(s.call(s.frame_height, color_frame))
                fmt = int(s.call(s.frame_format, color_frame))
                raw = _decode(
                    s.call(s.frame_data, color_frame),
                    int(s.call(s.frame_data_size, color_frame)),
                )
                color = _decode_color(raw, w, h, fmt)
                color_ts = int(s.call(s.frame_ts_us, color_frame))
                color_idx = int(s.call(s.frame_index, color_frame))

            depth_intrinsic, color_intrinsic = self.intrinsics()

            return Frame(
                depth=depth,
                color_bgr=color,
                depth_ts_us=depth_ts,
                color_ts_us=color_ts,
                depth_index=depth_idx,
                color_index=color_idx,
                depth_intrinsic=depth_intrinsic,
                color_intrinsic=color_intrinsic,
                aligned=self.aligned,
                extra={"depth_scale": depth_scale},
            )
        finally:
            for f in (depth_frame, color_frame):
                if f:
                    s.call(s.delete_frame, f)
            s.call(s.delete_frame, frameset)

    def frames(self, timeout_ms: int = 1000) -> Iterator[Frame]:
        while True:
            frame = self.read(timeout_ms)
            if frame is None:
                continue
            yield frame


def _decode_color(raw: bytes, w: int, h: int, fmt: int) -> np.ndarray | None:
    if not raw or not w or not h:
        return None
    if fmt == OB_FORMAT_MJPG:
        if cv2 is None:
            raise OrbbecError("opencv is required to decode MJPG colour frames")
        buf = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        return img if img is not None else None
    if fmt in (OB_FORMAT_YUYV, OB_FORMAT_YUY2):
        img = np.frombuffer(raw, dtype=np.uint8, count=w * h * 2).reshape(h, w, 2)
        return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUYV) if cv2 else None
    if fmt == OB_FORMAT_UYVY:
        img = np.frombuffer(raw, dtype=np.uint8, count=w * h * 2).reshape(h, w, 2)
        return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_UYVY) if cv2 else None
    if fmt == OB_FORMAT_BGR:
        return np.frombuffer(raw, dtype=np.uint8, count=w * h * 3).reshape(h, w, 3).copy()
    if fmt == OB_FORMAT_RGB:
        img = np.frombuffer(raw, dtype=np.uint8, count=w * h * 3).reshape(h, w, 3)
        return img[:, :, ::-1].copy()
    if fmt == OB_FORMAT_BGRA:
        img = np.frombuffer(raw, dtype=np.uint8, count=w * h * 4).reshape(h, w, 4)
        return img[:, :, :3].copy()
    if fmt == OB_FORMAT_RGBA:
        img = np.frombuffer(raw, dtype=np.uint8, count=w * h * 4).reshape(h, w, 4)
        return img[:, :, 2::-1].copy()
    raise OrbbecError(f"unsupported colour format: {fmt}")


__all__ = [
    "ALIGN_D2C_HW_MODE",
    "ALIGN_D2C_SW_MODE",
    "ALIGN_DISABLE",
    "CameraIntrinsic",
    "DeviceInfo",
    "Frame",
    "OB_SENSOR_COLOR",
    "OB_SENSOR_DEPTH",
    "OrbbecCamera",
    "OrbbecError",
    "StreamProfileInfo",
    "list_devices",
    "sdk_version",
]

