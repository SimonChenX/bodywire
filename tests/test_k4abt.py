import pytest

from bodywire.skeleton.k4abt import (
    JOINT_COUNT,
    JOINT_NAMES,
    BodyTrackingState,
    ConfidenceLevel,
    Joint,
    Skeleton,
    SkeletonBody,
)


def test_joint_count_and_names():
    assert JOINT_COUNT == 32
    assert len(set(JOINT_NAMES)) == 32
    assert len(JOINT_NAMES) == 32


def test_joint_order_matches_k4abt():
    # Spot-check the anchors that consumers rely on.
    assert Joint.PELVIS == 0
    assert Joint.NECK == 3
    assert Joint.CLAVICLE_RIGHT == 11
    assert Joint.HIP_LEFT == 18
    assert Joint.HEAD == 26
    assert Joint.EAR_RIGHT == 31
    assert JOINT_NAMES[7] == "WRIST_LEFT"
    assert JOINT_NAMES[22] == "HIP_RIGHT"


def test_skeleton_requires_full_joint_set():
    with pytest.raises(ValueError):
        Skeleton(positions=[(0.0, 0.0, 0.0)] * 31)
    with pytest.raises(ValueError):
        Skeleton(confidence=[ConfidenceLevel.HIGH] * 31)


def test_skeleton_from_pairs_and_lookup():
    positions = [(float(i), 1.0, 2.0) for i in range(JOINT_COUNT)]
    skel = Skeleton.from_pairs(positions)
    assert len(skel.positions) == JOINT_COUNT
    pos, conf = skel.joint(Joint.HEAD)
    assert pos == (26.0, 1.0, 2.0)
    assert conf == ConfidenceLevel.LOW


def test_skeleton_body_roundtrip_dict():
    skel = Skeleton.from_pairs([(0.0, 0.0, 0.0)] * JOINT_COUNT)
    body = SkeletonBody(body_id=3, skeleton=skel, tracking_state=BodyTrackingState.TRACKED)
    payload = skel.as_dict()
    assert len(payload["joints"]) == JOINT_COUNT
    assert payload["joints"][26]["name"] == "HEAD"
    assert body.body_id == 3