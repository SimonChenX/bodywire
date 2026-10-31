import numpy as np
import pytest

from bodywire.pose import Landmark, PoseResult
from bodywire.skeleton.k4abt import JOINT_COUNT, ConfidenceLevel, Joint
from bodywire.skeleton.lift import CameraModel, lift_pose, sample_depth
from bodywire.skeleton.mapping import build_skeleton


def make_pose() -> PoseResult:
    """A synthetic upright person in a 640x480 frame."""
    coords = [(0.5, 0.5)] * 33
    coords[0] = (0.50, 0.12)   # nose
    coords[2] = (0.47, 0.10)   # left eye
    coords[5] = (0.53, 0.10)   # right eye
    coords[7] = (0.42, 0.12)   # left ear
    coords[8] = (0.58, 0.12)   # right ear
    coords[11] = (0.25, 0.25)  # left shoulder
    coords[12] = (0.75, 0.25)  # right shoulder
    coords[13] = (0.20, 0.40)  # left elbow
    coords[14] = (0.80, 0.40)  # right elbow
    coords[15] = (0.15, 0.55)  # left wrist
    coords[16] = (0.85, 0.55)  # right wrist
    coords[23] = (0.40, 0.60)  # left hip
    coords[24] = (0.60, 0.60)  # right hip
    coords[25] = (0.40, 0.75)  # left knee
    coords[26] = (0.60, 0.75)  # right knee
    coords[27] = (0.40, 0.90)  # left ankle
    coords[28] = (0.60, 0.90)  # right ankle
    coords[29] = (0.38, 0.93)  # left heel
    coords[30] = (0.62, 0.93)  # right heel
    coords[31] = (0.42, 0.95)  # left foot index
    coords[32] = (0.58, 0.95)  # right foot index
    return PoseResult(pose=tuple(Landmark(x=x, y=y, visibility=1.0) for x, y in coords))


CAM = CameraModel(fx=500.0, fy=500.0, cx=320.0, cy=240.0, width=640, height=480)


def test_sample_depth_median_and_bounds():
    depth = np.full((480, 640), np.nan, dtype=np.float32)
    depth[100:105, 200:205] = 2000.0
    assert sample_depth(depth, 202, 102, window=5) == 2000
    assert sample_depth(depth, 10, 10, window=5) is None
    assert sample_depth(depth, -5, 10) is None


def test_lift_backprojects_using_intrinsics():
    depth = np.full((480, 640), 2000.0, dtype=np.float32)
    lift = lift_pose(make_pose(), depth, CAM)
    # left shoulder at pixel (160, 120)
    x, y, z = lift.pose_mm[11]
    assert z == pytest.approx(2000.0)
    assert x == pytest.approx((160 - 320) * 2000 / 500)
    assert y == pytest.approx((120 - 240) * 2000 / 500)


def test_lift_marks_missing_depth_as_nan():
    depth = np.full((480, 640), np.nan, dtype=np.float32)
    lift = lift_pose(make_pose(), depth, CAM)
    assert not np.isfinite(lift.pose_mm).any()


def test_build_skeleton_has_32_joints_and_derived_positions():
    depth = np.full((480, 640), 2000.0, dtype=np.float32)
    lift = lift_pose(make_pose(), depth, CAM)
    skel = build_skeleton(lift)
    assert len(skel.positions) == JOINT_COUNT
    assert len(skel.confidence) == JOINT_COUNT

    pelvis = np.array(skel.positions[int(Joint.PELVIS)])
    assert pelvis[0] == pytest.approx(0.0, abs=1e-3)
    assert pelvis[2] == pytest.approx(2000.0, abs=1e-3)

    chest = np.array(skel.positions[int(Joint.SPINE_CHEST)])
    assert chest[1] < pelvis[1]  # chest is above the pelvis (Y is down)

    for joint in (Joint.NECK, Joint.HEAD, Joint.NOSE, Joint.CLAVICLE_LEFT, Joint.FOOT_LEFT):
        assert np.isfinite(skel.positions[int(joint)]).all()


def test_build_skeleton_hand_fallback_has_no_confidence():
    depth = np.full((480, 640), 2000.0, dtype=np.float32)
    skel = build_skeleton(lift_pose(make_pose(), depth, CAM))
    assert skel.confidence[int(Joint.HAND_LEFT)] == ConfidenceLevel.NONE
    # but the position falls back to the wrist so the array stays valid
    assert np.isfinite(skel.positions[int(Joint.WRIST_LEFT)]).all()


def test_all_nan_lift_produces_empty_skeleton():
    depth = np.full((480, 640), np.nan, dtype=np.float32)
    skel = build_skeleton(lift_pose(make_pose(), depth, CAM))
    assert all(c == ConfidenceLevel.NONE for c in skel.confidence)