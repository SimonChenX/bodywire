"""End-to-end: capture frame -> MediaPipe pose -> 3D lift -> k4abt skeleton."""

from __future__ import annotations

from dataclasses import dataclass

from ..capture.orbbec import Frame
from ..pose import PoseResult
from ..pose.mediapipe_pose import PoseEstimator
from .filter import SkeletonFilter
from .k4abt import Skeleton
from .lift import CameraModel, LiftResult, lift_pose
from .mapping import build_skeleton


@dataclass
class PipelineOutput:
    skeleton: Skeleton
    pose: PoseResult
    lift: LiftResult
    camera: CameraModel
    timestamp_ms: int


class SkeletonPipeline:
    """Stateful pose-to-skeleton pipeline (one person)."""

    def __init__(
        self,
        estimator: PoseEstimator,
        filter: SkeletonFilter | None = None,
        depth_window: int = 5,
    ) -> None:
        self.estimator = estimator
        self.filter = filter or SkeletonFilter()
        self.depth_window = int(depth_window)

    def process(self, frame: Frame, timestamp_ms: int) -> PipelineOutput | None:
        if frame.color_bgr is None or frame.depth is None or frame.depth_intrinsic is None:
            return None

        result = self.estimator.detect(frame.color_bgr, timestamp_ms)
        if result is None:
            return None

        camera = CameraModel.from_intrinsic(frame.depth_intrinsic)
        lift = lift_pose(result, frame.depth, camera, window=self.depth_window)
        skeleton = build_skeleton(lift)

        timestamp_s = frame.depth_ts_us / 1e6 if frame.depth_ts_us else timestamp_ms / 1000.0
        skeleton = self.filter.update(skeleton, timestamp_s)
        return PipelineOutput(
            skeleton=skeleton,
            pose=result,
            lift=lift,
            camera=camera,
            timestamp_ms=timestamp_ms,
        )


__all__ = ["PipelineOutput", "SkeletonPipeline"]