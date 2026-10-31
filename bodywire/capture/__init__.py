"""Capture layer: Orbbec Astra+ depth + colour via the OrbbecSDK C API."""

from .orbbec import (
    CameraIntrinsic,
    DeviceInfo,
    Frame,
    OrbbecCamera,
    OrbbecError,
    StreamProfileInfo,
    list_devices,
    sdk_version,
)

__all__ = [
    "CameraIntrinsic",
    "DeviceInfo",
    "Frame",
    "OrbbecCamera",
    "OrbbecError",
    "StreamProfileInfo",
    "list_devices",
    "sdk_version",
]