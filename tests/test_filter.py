import numpy as np

from bodywire.skeleton.filter import OneEuroFilter, SkeletonFilter
from bodywire.skeleton.k4abt import JOINT_COUNT, ConfidenceLevel, Joint, Skeleton


def _skeleton(positions=None, confidence=None) -> Skeleton:
    pos = positions or [(0.0, 0.0, 0.0)] * JOINT_COUNT
    conf = confidence or [ConfidenceLevel.NONE] * JOINT_COUNT
    return Skeleton(positions=pos, confidence=conf)


def test_one_euro_passthrough_then_smooths():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    assert f(10.0, t=0.0) == 10.0
    out = f(20.0, t=0.1)
    assert 10.0 < out < 20.0


def test_skeleton_filter_holds_missing_joint():
    sf = SkeletonFilter(hold_ms=500.0)
    pos = [(0.0, 0.0, 0.0)] * JOINT_COUNT
    pos[int(Joint.HEAD)] = (100.0, 200.0, 2000.0)
    conf = [ConfidenceLevel.NONE] * JOINT_COUNT
    conf[int(Joint.HEAD)] = ConfidenceLevel.HIGH

    first = sf.update(_skeleton(pos, conf), timestamp_s=0.0)
    assert first.confidence[int(Joint.HEAD)] == ConfidenceLevel.HIGH
    held_position = first.positions[int(Joint.HEAD)]

    missing = sf.update(_skeleton(), timestamp_s=0.1)
    assert missing.positions[int(Joint.HEAD)] == held_position
    assert missing.confidence[int(Joint.HEAD)] == ConfidenceLevel.NONE

    expired = sf.update(_skeleton(), timestamp_s=1.0)
    assert expired.positions[int(Joint.HEAD)] == (0.0, 0.0, 0.0)
    assert expired.confidence[int(Joint.HEAD)] == ConfidenceLevel.NONE


def test_skeleton_filter_reset():
    sf = SkeletonFilter()
    pos = [(1.0, 2.0, 3.0)] * JOINT_COUNT
    conf = [ConfidenceLevel.HIGH] * JOINT_COUNT
    sf.update(_skeleton(pos, conf), timestamp_s=0.0)
    sf.reset()
    out = sf.update(_skeleton(), timestamp_s=0.1)
    assert all(c == ConfidenceLevel.NONE for c in out.confidence)