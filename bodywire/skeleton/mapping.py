"""Map MediaPipe's 33 pose + 21/hand landmarks onto k4abt's 32 joints.

Some k4abt joints have no direct MediaPipe counterpart (spine, clavicles,
palms, feet). They are derived geometrically here. When a source landmark is
unknown the derived joint is ``NaN`` and its confidence is ``NONE``; the
temporal filter decides whether to hold the previous value.
"""

from __future__ import annotations

import numpy as np

from ..pose.mediapipe_pose import (
    HAND_INDEX_MCP,
    HAND_MIDDLE_TIP,
    HAND_PINKY_MCP,
    HAND_THUMB_TIP,
    HAND_WRIST,
    LEFT_ANKLE,
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_EYE,
    LEFT_FOOT_INDEX,
    LEFT_HEEL,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_EYE,
    RIGHT_FOOT_INDEX,
    RIGHT_HEEL,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
)
from .k4abt import JOINT_COUNT, ConfidenceLevel, Joint, Skeleton
from .lift import LiftResult

_POSE_JOINTS = JOINT_COUNT


def confidence_level(value: float) -> ConfidenceLevel:
    if value >= 0.80:
        return ConfidenceLevel.HIGH
    if value >= 0.50:
        return ConfidenceLevel.MEDIUM
    if value > 0.10:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.NONE


def _valid(point: np.ndarray | None) -> bool:
    return point is not None and bool(np.isfinite(point).all())


def _mid(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) / 2.0


def _lerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return a * (1.0 - t) + b * t


def build_skeleton(lift: LiftResult) -> Skeleton:
    """Convert a :class:`LiftResult` into a k4abt-order :class:`Skeleton`."""
    pose = lift.pose_mm
    conf = lift.confidence

    def p(index: int) -> np.ndarray | None:
        if index >= pose.shape[0]:
            return None
        point = pose[index]
        return point if _valid(point) else None

    def c(index: int) -> float:
        return float(conf[index]) if index < conf.shape[0] else 0.0

    out = np.full((_POSE_JOINTS, 3), np.nan, dtype=np.float32)
    out_conf = np.zeros((_POSE_JOINTS,), dtype=np.float32)

    def put(joint: Joint, point: np.ndarray | None, score: float) -> None:
        if point is None or not np.isfinite(point).all():
            out_conf[int(joint)] = 0.0
            return
        out[int(joint)] = point
        out_conf[int(joint)] = max(0.0, min(1.0, score))

    def put_mid(joint: Joint, a: np.ndarray | None, b: np.ndarray | None, sa: float, sb: float) -> None:
        if _valid(a) and _valid(b):
            put(joint, _mid(a, b), min(sa, sb))
        elif _valid(a):
            put(joint, a, sa * 0.5)
        elif _valid(b):
            put(joint, b, sb * 0.5)

    l_shoulder, r_shoulder = p(LEFT_SHOULDER), p(RIGHT_SHOULDER)
    l_hip, r_hip = p(LEFT_HIP), p(RIGHT_HIP)
    l_ear, r_ear = p(LEFT_EAR), p(RIGHT_EAR)
    nose = p(NOSE)

    pelvis = None
    if _valid(l_hip) and _valid(r_hip):
        pelvis = _mid(l_hip, r_hip)
    elif _valid(l_hip):
        pelvis = l_hip
    elif _valid(r_hip):
        pelvis = r_hip

    chest = None
    if _valid(l_shoulder) and _valid(r_shoulder):
        chest = _mid(l_shoulder, r_shoulder)
    elif _valid(l_shoulder):
        chest = l_shoulder
    elif _valid(r_shoulder):
        chest = r_shoulder

    head = None
    if _valid(l_ear) and _valid(r_ear):
        ears = _mid(l_ear, r_ear)
        head = ears + 0.5 * (ears - nose) if _valid(nose) else ears
    elif _valid(nose):
        head = nose

    if _valid(chest) and _valid(head):
        neck = _lerp(chest, head, 0.35)
    else:
        neck = chest if _valid(chest) else head

    put(Joint.PELVIS, pelvis, min(c(LEFT_HIP), c(RIGHT_HIP)))
    put(Joint.SPINE_NAVEL, _lerp(pelvis, chest, 0.35) if _valid(pelvis) and _valid(chest) else None, min(c(LEFT_HIP), c(LEFT_SHOULDER)))
    put(Joint.SPINE_CHEST, chest, min(c(LEFT_SHOULDER), c(RIGHT_SHOULDER)))
    put(Joint.NECK, neck, min(c(LEFT_SHOULDER), c(RIGHT_SHOULDER)))

    # Clavicles sit halfway between the neck line and the shoulder.
    if _valid(chest) and _valid(l_shoulder):
        put(Joint.CLAVICLE_LEFT, _lerp(chest, l_shoulder, 0.5), min(c(LEFT_SHOULDER), c(RIGHT_SHOULDER)))
    if _valid(chest) and _valid(r_shoulder):
        put(Joint.CLAVICLE_RIGHT, _lerp(chest, r_shoulder, 0.5), min(c(LEFT_SHOULDER), c(RIGHT_SHOULDER)))

    put(Joint.SHOULDER_LEFT, l_shoulder, c(LEFT_SHOULDER))
    put(Joint.ELBOW_LEFT, p(LEFT_ELBOW), c(LEFT_ELBOW))
    put(Joint.WRIST_LEFT, p(LEFT_WRIST), c(LEFT_WRIST))
    put(Joint.SHOULDER_RIGHT, r_shoulder, c(RIGHT_SHOULDER))
    put(Joint.ELBOW_RIGHT, p(RIGHT_ELBOW), c(RIGHT_ELBOW))
    put(Joint.WRIST_RIGHT, p(RIGHT_WRIST), c(RIGHT_WRIST))

    put(Joint.HIP_LEFT, l_hip, c(LEFT_HIP))
    put(Joint.KNEE_LEFT, p(LEFT_KNEE), c(LEFT_KNEE))
    put(Joint.ANKLE_LEFT, p(LEFT_ANKLE), c(LEFT_ANKLE))
    put(Joint.HIP_RIGHT, r_hip, c(RIGHT_HIP))
    put(Joint.KNEE_RIGHT, p(RIGHT_KNEE), c(RIGHT_KNEE))
    put(Joint.ANKLE_RIGHT, p(RIGHT_ANKLE), c(RIGHT_ANKLE))

    # Feet: mid-point between heel and toe reads closer to k4abt FOOT.
    put_mid(
        Joint.FOOT_LEFT,
        p(LEFT_HEEL),
        p(LEFT_FOOT_INDEX),
        c(LEFT_HEEL),
        c(LEFT_FOOT_INDEX),
    )
    put_mid(
        Joint.FOOT_RIGHT,
        p(RIGHT_HEEL),
        p(RIGHT_FOOT_INDEX),
        c(RIGHT_HEEL),
        c(RIGHT_FOOT_INDEX),
    )

    put(Joint.HEAD, head, min(c(LEFT_EAR), c(RIGHT_EAR)) if _valid(l_ear) and _valid(r_ear) else c(NOSE))
    put(Joint.NOSE, nose, c(NOSE))
    put(Joint.EYE_LEFT, p(LEFT_EYE), c(LEFT_EYE))
    put(Joint.EYE_RIGHT, p(RIGHT_EYE), c(RIGHT_EYE))
    put(Joint.EAR_LEFT, l_ear, c(LEFT_EAR))
    put(Joint.EAR_RIGHT, r_ear, c(RIGHT_EAR))

    _fill_hands(out, out_conf, lift, l_shoulder, r_shoulder)

    positions = [tuple(float(v) for v in out[i]) for i in range(_POSE_JOINTS)]
    confidence = [confidence_level(float(out_conf[i])) for i in range(_POSE_JOINTS)]
    return Skeleton(positions=positions, confidence=confidence)


def _fill_hands(
    out: np.ndarray,
    out_conf: np.ndarray,
    lift: LiftResult,
    l_shoulder: np.ndarray | None,
    r_shoulder: np.ndarray | None,
) -> None:
    for side, hand, hand_conf, wrist_index, shoulder in (
        ("L", lift.left_hand_mm, lift.left_hand_confidence, LEFT_WRIST, l_shoulder),
        ("R", lift.right_hand_mm, lift.right_hand_confidence, RIGHT_WRIST, r_shoulder),
    ):
        wrist = lift.pose_mm[wrist_index]
        wrist_ok = _valid(wrist)
        if hand is None or hand.shape[0] < 21:
            # Without a hand model the wrist is the best proxy; confidence is
            # forced to NONE so receivers do not draw a fake hand.
            if wrist_ok:
                for joint in (
                    Joint.HAND_LEFT if side == "L" else Joint.HAND_RIGHT,
                    Joint.HANDTIP_LEFT if side == "L" else Joint.HANDTIP_RIGHT,
                    Joint.THUMB_LEFT if side == "L" else Joint.THUMB_RIGHT,
                ):
                    out[int(joint)] = wrist
                    out_conf[int(joint)] = 0.0
            continue

        palm = None
        if all(np.isfinite(hand[i]).all() for i in (HAND_WRIST, HAND_INDEX_MCP, HAND_PINKY_MCP)):
            palm = (hand[HAND_WRIST] + hand[HAND_INDEX_MCP] + hand[HAND_PINKY_MCP]) / 3.0
        elif wrist_ok:
            palm = wrist

        values = [
            (Joint.HAND_LEFT if side == "L" else Joint.HAND_RIGHT, palm),
            (Joint.HANDTIP_LEFT if side == "L" else Joint.HANDTIP_RIGHT, hand[HAND_MIDDLE_TIP]),
            (Joint.THUMB_LEFT if side == "L" else Joint.THUMB_RIGHT, hand[HAND_THUMB_TIP]),
        ]
        for joint, point in values:
            if point is not None and np.isfinite(point).all():
                out[int(joint)] = point
                out_conf[int(joint)] = float(hand_conf[HAND_MIDDLE_TIP]) if hand_conf is not None else 0.5


__all__ = ["build_skeleton", "confidence_level"]