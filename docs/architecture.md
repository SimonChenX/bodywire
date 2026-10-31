# Architecture

bodywire turns an Orbbec Astra+ into a markerless body-tracking source whose
output looks like Azure Kinect Body Tracking (`k4abt`) output, but without the
Azure depth engine.

## Layers

```
Astra+ (UVC: depth + colour)
   │  OrbbecSDK 1.10.37 (ctypes)            bodywire/capture
   ▼
depth Y16 + colour MJPG + intrinsics + software D2C
   │
   ▼  bodywire/pose
MediaPipe Pose (33) + Hands (21/hand)  →  PoseResult
   │  bodywire/skeleton/lift
aligned depth sampling + back-projection  →  landmarks in mm
   │  bodywire/skeleton/mapping
geometric derivation + hand merge         →  32 k4abt joints
   │  bodywire/skeleton/filter
One Euro + short hold                     →  stable skeleton
   │  bodywire/transport
bodywire/1 UDP datagram (+ BWC1 control)
   ▼
Unity / Unreal / Python receivers
```

## Why not replace `k4a.dll`?

`k4abt` depends on Microsoft's closed-source `depthengine_2_0.dll`, which is
bound to Azure Kinect calibration. Feeding it Astra+ frames produces wrong
geometry — that is exactly why the Orbbec K4A wrapper filters Astra+ out and
reports zero devices. bodywire keeps the **data contract** compatible instead:

- 32 joints in `k4abt_joint_id_t` order
- millimetres, right-handed, +X right, +Y down, +Z forward
- confidence levels 0..3 (none / low / medium / high)
- stable `body_id` for the lifetime of a track

The binary API is not compatible, and that is a deliberate trade-off.

## Coordinate spaces

| Stage | Space | Units |
| --- | --- | --- |
| Orbbec depth frame (native) | depth camera, X right / Y down / Z forward | mm |
| After software D2C | colour camera pixel grid | mm |
| `LiftResult.pose_mm` | colour camera space | mm |
| k4abt skeleton | colour camera space (documented in calibration) | mm |
| Wire format | same as k4abt | mm (int32) |
| Unity receiver | (x, -y, z) / 1000 | m |
| Unreal receiver | (z, x, -y) / 100 | cm |

The active camera is the **colour** camera whenever `aligned = true`. The
calibration datagram states this explicitly in `coordinate_space`.

## Why MediaPipe Pose + Hands

- Pose gives 33 landmarks including heels, foot index, ears and eyes, which map
  cleanly onto most of the k4abt joint set.
- Hands fill `HAND`, `HANDTIP` and `THUMB`; without a hand result those joints
  are sent with `confidence = 0` (never dropped, so the array stays fixed).
- MediaPipe Tasks is Apache-2.0 and runs on CPU at interactive rates; no GPU
  runtime is required.

## Filtering

Each joint axis runs through a One Euro filter (`min_cutoff = 1.0`,
`beta = 0.007`). The filter reacts fast during motion and smooths heavily when
still. A joint that disappears keeps its last position for `hold_ms = 250` with
`confidence = NONE`, then snaps to zero. Receivers should treat `NONE` as
"hold, do not draw".

## Threading

The daemon is single-threaded: capture, inference, UDP send and the optional
preview all run in the capture loop. This keeps latency predictable and avoids
MediaPipe thread-safety questions. Receivers run their own socket loop; the
Unity receiver parses on a background thread and swaps frames on `Update`.

## Known limits

- **One person.** `num_poses` can be raised, but the wire format and mapping are
  single-body, and the first pose wins.
- **No finger articulation.** MediaPipe Hands gives 21 points; only palm, middle
  fingertip and thumb tip are mapped.
- **No segmentation / depth-only mode.** The pipeline needs colour; depth is
  used only to lift landmarks.
- **Structured-light caveats.** Direct sunlight, reflective floors and very dark
  clothing reduce depth validity; those frames fall back to held joints.