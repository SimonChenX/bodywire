"""bodywire - markerless full-body tracking from an Orbbec Astra+.

The package is organised in four layers:

``bodywire.capture``
    Depth/colour acquisition through the OrbbecSDK C API.
``bodywire.pose``
    2D landmark estimation (MediaPipe Pose + Hands).
``bodywire.skeleton``
    k4abt-compatible 32-joint skeleton model.
``bodywire.transport``
    The ``bodywire/1`` UDP wire format.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]