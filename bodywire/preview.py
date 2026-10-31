"""OpenCV preview: pose landmarks, projected k4abt skeleton and depth map."""

from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

from .pose import PoseResult
from .skeleton.k4abt import ConfidenceLevel, Joint, Skeleton
from .skeleton.lift import CameraModel

POSE_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
)

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)

K4ABT_CONNECTIONS = (
    (Joint.PELVIS, Joint.SPINE_NAVEL),
    (Joint.SPINE_NAVEL, Joint.SPINE_CHEST),
    (Joint.SPINE_CHEST, Joint.NECK),
    (Joint.NECK, Joint.HEAD),
    (Joint.HEAD, Joint.NOSE),
    (Joint.NOSE, Joint.EYE_LEFT),
    (Joint.NOSE, Joint.EYE_RIGHT),
    (Joint.EYE_LEFT, Joint.EAR_LEFT),
    (Joint.EYE_RIGHT, Joint.EAR_RIGHT),
    (Joint.SPINE_CHEST, Joint.CLAVICLE_LEFT),
    (Joint.CLAVICLE_LEFT, Joint.SHOULDER_LEFT),
    (Joint.SHOULDER_LEFT, Joint.ELBOW_LEFT),
    (Joint.ELBOW_LEFT, Joint.WRIST_LEFT),
    (Joint.WRIST_LEFT, Joint.HAND_LEFT),
    (Joint.HAND_LEFT, Joint.HANDTIP_LEFT),
    (Joint.HAND_LEFT, Joint.THUMB_LEFT),
    (Joint.SPINE_CHEST, Joint.CLAVICLE_RIGHT),
    (Joint.CLAVICLE_RIGHT, Joint.SHOULDER_RIGHT),
    (Joint.SHOULDER_RIGHT, Joint.ELBOW_RIGHT),
    (Joint.ELBOW_RIGHT, Joint.WRIST_RIGHT),
    (Joint.WRIST_RIGHT, Joint.HAND_RIGHT),
    (Joint.HAND_RIGHT, Joint.HANDTIP_RIGHT),
    (Joint.HAND_RIGHT, Joint.THUMB_RIGHT),
    (Joint.PELVIS, Joint.HIP_LEFT),
    (Joint.HIP_LEFT, Joint.KNEE_LEFT),
    (Joint.KNEE_LEFT, Joint.ANKLE_LEFT),
    (Joint.ANKLE_LEFT, Joint.FOOT_LEFT),
    (Joint.PELVIS, Joint.HIP_RIGHT),
    (Joint.HIP_RIGHT, Joint.KNEE_RIGHT),
    (Joint.KNEE_RIGHT, Joint.ANKLE_RIGHT),
    (Joint.ANKLE_RIGHT, Joint.FOOT_RIGHT),
)


def _require_cv2() -> None:
    if cv2 is None:  # pragma: no cover
        raise RuntimeError("opencv-python is required for preview")


def draw_pose(image: np.ndarray, result: PoseResult, color=(0, 255, 0)) -> None:
    _require_cv2()
    h, w = image.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in result.pose]
    for a, b in POSE_CONNECTIONS:
        if a < len(pts) and b < len(pts):
            cv2.line(image, pts[a], pts[b], color, 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(image, p, 3, color, -1, cv2.LINE_AA)
    for hand in (result.left_hand, result.right_hand):
        if not hand:
            continue
        hpts = [(int(lm.x * w), int(lm.y * h)) for lm in hand]
        for a, b in HAND_CONNECTIONS:
            if a < len(hpts) and b < len(hpts):
                cv2.line(image, hpts[a], hpts[b], (0, 200, 255), 1, cv2.LINE_AA)
        for p in hpts:
            cv2.circle(image, p, 2, (0, 200, 255), -1, cv2.LINE_AA)


def draw_skeleton_3d(
    image: np.ndarray,
    skeleton: Skeleton,
    camera: CameraModel,
    color=(255, 120, 0),
) -> None:
    """Project the 3D skeleton back onto the image (validates the lift)."""
    _require_cv2()
    def projected(joint: Joint) -> tuple[int, int] | None:
        x, y, z = skeleton.positions[int(joint)]
        if not (np.isfinite(x) and np.isfinite(y) and np.isfinite(z)) or z <= 0:
            return None
        if skeleton.confidence[int(joint)] == ConfidenceLevel.NONE and abs(x) + abs(y) + abs(z) == 0:
            return None
        u, v = camera.project((x, y, z))
        if not (np.isfinite(u) and np.isfinite(v)):
            return None
        return int(u), int(v)

    for a, b in K4ABT_CONNECTIONS:
        pa, pb = projected(a), projected(b)
        if pa and pb:
            cv2.line(image, pa, pb, color, 2, cv2.LINE_AA)
    for joint in Joint:
        p = projected(joint)
        if p:
            cv2.circle(image, p, 3, color, -1, cv2.LINE_AA)


def depth_color(depth_mm: np.ndarray, near: float = 300.0, far: float = 4000.0) -> np.ndarray:
    _require_cv2()
    depth = np.nan_to_num(depth_mm, nan=0.0)
    norm = np.clip((depth - near) / (far - near), 0.0, 1.0)
    vis = (norm * 255).astype(np.uint8)
    vis[depth <= 0] = 0
    return cv2.applyColorMap(vis, cv2.COLORMAP_JET)


def compose(
    frame_bgr: np.ndarray,
    depth_mm: np.ndarray | None,
    pose: PoseResult | None,
    skeleton: Skeleton | None,
    camera: CameraModel | None,
    show_depth: bool = True,
) -> np.ndarray:
    """Build the preview canvas (colour on the left, depth on the right)."""
    _require_cv2()
    canvas = frame_bgr.copy()
    if pose is not None:
        draw_pose(canvas, pose)
    if skeleton is not None and camera is not None:
        draw_skeleton_3d(canvas, skeleton, camera)

    if not show_depth or depth_mm is None:
        return canvas
    d = depth_color(depth_mm)
    if d.shape[:2] != canvas.shape[:2]:
        d = cv2.resize(d, (canvas.shape[1], canvas.shape[0]))
    return np.hstack([canvas, d])


__all__ = [
    "HAND_CONNECTIONS",
    "K4ABT_CONNECTIONS",
    "POSE_CONNECTIONS",
    "compose",
    "depth_color",
    "draw_pose",
    "draw_skeleton_3d",
]