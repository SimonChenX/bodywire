"""MediaPipe Tasks wrapper: PoseLandmarker (33) + HandLandmarker (21/hand).

Both landmarkers run in ``VIDEO`` mode so MediaPipe can track between frames.
The wrapper is deliberately small - it returns plain :class:`PoseResult`
objects and knows nothing about depth or k4abt.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from . import Landmark, PoseResult

try:  # imported lazily by callers that only need the types
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        HandLandmarker,
        HandLandmarkerOptions,
        PoseLandmarker,
        PoseLandmarkerOptions,
        RunningMode,
    )
except ImportError:  # pragma: no cover - optional dependency
    mp = None  # type: ignore[assignment]
    BaseOptions = None  # type: ignore[assignment]
    HandLandmarker = None  # type: ignore[assignment]
    PoseLandmarker = None  # type: ignore[assignment]


POSE_MODEL = "pose_landmarker_lite.task"
HAND_MODEL = "hand_landmarker.task"

# MediaPipe Pose landmark indices, named for readability.
NOSE = 0
LEFT_EYE = 2
LEFT_EAR = 7
RIGHT_EYE = 5
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32
POSE_LANDMARKS = 33

# Hand landmark indices (MediaPipe Hands).
HAND_WRIST = 0
HAND_THUMB_TIP = 4
HAND_INDEX_MCP = 5
HAND_MIDDLE_TIP = 12
HAND_PINKY_MCP = 17
HAND_LANDMARKS = 21


class MediaPipeError(RuntimeError):
    pass


def default_model_dir() -> Path:
    """Resolve the model directory: env, repo ``models/``, then cwd ``models/``."""
    env = os.environ.get("BODYWIRE_MODEL_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "models"
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "models"


class PoseEstimator:
    """Pose + hands estimator backed by MediaPipe Tasks."""

    def __init__(
        self,
        model_dir: str | Path | None = None,
        num_poses: int = 1,
        use_hands: bool = True,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        if mp is None:  # pragma: no cover - dependency check
            raise MediaPipeError(
                "mediapipe is not installed; run `pip install -e .[pose]`"
            )

        root = Path(model_dir) if model_dir else default_model_dir()
        pose_model = root / POSE_MODEL
        hand_model = root / HAND_MODEL
        if not pose_model.is_file():
            raise MediaPipeError(
                f"missing {pose_model}; run `python tools/download_models.py`"
            )
        if use_hands and not hand_model.is_file():
            raise MediaPipeError(
                f"missing {hand_model}; run `python tools/download_models.py`"
            )

        self._pose = PoseLandmarker.create_from_options(
            PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(pose_model)),
                running_mode=RunningMode.VIDEO,
                num_poses=num_poses,
                min_pose_detection_confidence=min_detection_confidence,
                min_pose_presence_confidence=min_presence_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
        )
        self._hands = None
        if use_hands:
            self._hands = HandLandmarker.create_from_options(
                HandLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(hand_model)),
                    running_mode=RunningMode.VIDEO,
                    num_hands=2,
                    min_hand_detection_confidence=min_detection_confidence,
                    min_hand_presence_confidence=min_presence_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                )
            )
        self._last_ts = -1

    # -- lifecycle -------------------------------------------------------
    def close(self) -> None:
        if self._pose is not None:
            self._pose.close()
            self._pose = None
        if self._hands is not None:
            self._hands.close()
            self._hands = None

    def __enter__(self) -> "PoseEstimator":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- inference -------------------------------------------------------
    def detect(self, color_bgr: np.ndarray, timestamp_ms: int) -> PoseResult | None:
        """Run pose + hands on one BGR frame.

        ``timestamp_ms`` must be monotonically increasing (MediaPipe VIDEO
        mode requirement). Returns ``None`` when no pose is detected.
        """
        if self._pose is None:
            raise MediaPipeError("estimator is closed")
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        rgb = np.ascontiguousarray(color_bgr[:, :, ::-1])
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        pose_result = self._pose.detect_for_video(image, timestamp_ms)
        if not pose_result.pose_landmarks:
            return None

        pose = tuple(_to_landmark(lm) for lm in pose_result.pose_landmarks[0])
        world = ()
        if pose_result.pose_world_landmarks:
            world = tuple(_to_landmark(lm) for lm in pose_result.pose_world_landmarks[0])

        left_hand: tuple[Landmark, ...] = ()
        right_hand: tuple[Landmark, ...] = ()
        if self._hands is not None:
            hand_result = self._hands.detect_for_video(image, timestamp_ms)
            left_hand, right_hand = _split_hands(hand_result, pose)

        score = float(np.mean([lm.visibility for lm in pose[:11]])) if pose else 0.0
        return PoseResult(
            pose=pose,
            world=world,
            left_hand=left_hand,
            right_hand=right_hand,
            score=score,
        )


def _to_landmark(lm) -> Landmark:  # noqa: ANN001 - MediaPipe protobuf type
    return Landmark(
        x=float(lm.x),
        y=float(lm.y),
        z=float(lm.z),
        visibility=float(getattr(lm, "visibility", 1.0) or 1.0),
        presence=float(getattr(lm, "presence", 1.0) or 1.0),
    )


def _distance(a: Landmark, b: Landmark) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _split_hands(
    hand_result,
    pose: tuple[Landmark, ...],
) -> tuple[tuple[Landmark, ...], tuple[Landmark, ...]]:  # noqa: ANN001
    """Assign detected hands to left/right using handedness, with a wrist
    proximity fallback for mirrored or ambiguous frames."""
    left: tuple[Landmark, ...] = ()
    right: tuple[Landmark, ...] = ()
    if not hand_result.hand_landmarks:
        return left, right

    p_left_wrist = pose[LEFT_WRIST] if len(pose) > LEFT_WRIST else None
    p_right_wrist = pose[RIGHT_WRIST] if len(pose) > RIGHT_WRIST else None

    for i, landmarks in enumerate(hand_result.hand_landmarks):
        lm = tuple(_to_landmark(m) for m in landmarks)
        label = ""
        if i < len(hand_result.handedness) and hand_result.handedness[i]:
            label = (hand_result.handedness[i][0].category_name or "").lower()

        is_left = label == "left"
        if label not in ("left", "right") and p_left_wrist and p_right_wrist and lm:
            is_left = _distance(lm[HAND_WRIST], p_left_wrist) <= _distance(
                lm[HAND_WRIST], p_right_wrist
            )
        elif label not in ("left", "right") and p_left_wrist:
            is_left = True

        if is_left:
            if not left:
                left = lm
        else:
            if not right:
                right = lm
    return left, right


__all__ = [
    "HAND_LANDMARKS",
    "HAND_MODEL",
    "MediaPipeError",
    "PoseEstimator",
    "POSE_LANDMARKS",
    "POSE_MODEL",
    "default_model_dir",
]