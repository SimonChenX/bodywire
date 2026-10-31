"""Map bodywire's 32 k4abt joints to JUMPWORK's 18-joint "Ske18" layout.

The layout was inferred from ``MotionDemo.SkeProcessSystem``:

====  ======================  =========================================
idx   JUMPWORK meaning        bodywire joint
====  ======================  =========================================
0     pelvis / spine base     PELVIS
1     thorax                  SPINE_CHEST
2     neck                    NECK
3     left shoulder           SHOULDER_LEFT
4     left elbow              ELBOW_LEFT
5     left wrist              WRIST_LEFT
6     right shoulder          SHOULDER_RIGHT
7     right elbow             ELBOW_RIGHT
8     right wrist             WRIST_RIGHT
9     left hip                HIP_LEFT
10    left knee               KNEE_LEFT
11    left ankle              ANKLE_LEFT
12    left foot               FOOT_LEFT
13    right hip               HIP_RIGHT
14    right knee              KNEE_RIGHT
15    right ankle             ANKLE_RIGHT
16    right foot              FOOT_RIGHT
17    head                    HEAD
====  ======================  =========================================

``SkeProcessSystem.Change18To21`` derives the 21-joint model from these and
uses ``(ske[12] + ske[16]) / 2`` as the root, which is the midpoint between the
feet — consistent with the table above.

Coordinates are converted from bodywire's right-handed, Y-down millimetres to
JUMPWORK/Unity's Y-up metres: ``(x, -y, z) / 1000``.
"""

from __future__ import annotations

import numpy as np

from ..skeleton.k4abt import ConfidenceLevel, Joint, Skeleton

JUMPWORK_JOINTS: tuple[Joint, ...] = (
    Joint.PELVIS,
    Joint.SPINE_CHEST,
    Joint.NECK,
    Joint.SHOULDER_LEFT,
    Joint.ELBOW_LEFT,
    Joint.WRIST_LEFT,
    Joint.SHOULDER_RIGHT,
    Joint.ELBOW_RIGHT,
    Joint.WRIST_RIGHT,
    Joint.HIP_LEFT,
    Joint.KNEE_LEFT,
    Joint.ANKLE_LEFT,
    Joint.FOOT_LEFT,
    Joint.HIP_RIGHT,
    Joint.KNEE_RIGHT,
    Joint.ANKLE_RIGHT,
    Joint.FOOT_RIGHT,
    Joint.HEAD,
)

JUMPWORK_JOINT_COUNT = len(JUMPWORK_JOINTS)


def k4abt_to_jumpwork(skeleton: Skeleton) -> tuple[list[list[float]], list[bool]]:
    """Return 18 ``[x, y, z]`` metres in JUMPWORK space plus a validity mask."""
    points: list[list[float]] = []
    valid: list[bool] = []
    for joint in JUMPWORK_JOINTS:
        x, y, z = skeleton.positions[int(joint)]
        finite = bool(np.isfinite(x) and np.isfinite(y) and np.isfinite(z))
        ok = finite and skeleton.confidence[int(joint)] != ConfidenceLevel.NONE
        if not finite:
            x = y = z = 0.0
        points.append([float(x) / 1000.0, float(-y) / 1000.0, float(z) / 1000.0])
        valid.append(ok)
    return points, valid


__all__ = ["JUMPWORK_JOINTS", "JUMPWORK_JOINT_COUNT", "k4abt_to_jumpwork"]