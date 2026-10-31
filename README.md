# bodywire

Markerless full-body tracking from an **Orbbec Astra+** (depth + RGB), streamed
as **k4abt-compatible skeletons over UDP**.

The goal is simple: any app that was written around Azure Kinect Body Tracking
(`k4abt`) should be able to consume bodywire with a thin receiver, without the
Azure depth engine and without a Kinect.

> Status: **M0 — capture layer**. Depth/colour acquisition and the wire format
> are implemented and tested against an Astra+ on Windows. Pose inference and
> engine receivers land in M1/M2.

## Why not just replace `k4a.dll`?

Because `k4abt` depends on Microsoft's closed-source `depthengine_2_0.dll`,
which is bound to Azure Kinect calibration. Feeding it Astra+ frames produces
wrong geometry, not a drop-in replacement. bodywire therefore keeps the
**data contract** k4abt-compatible (32 joints, mm, right-handed +Y down, 0..3
confidence) and stays out of the binary-compatibility trap.

## Architecture

```
Astra+ (UVC)
   │  OrbbecSDK 1.10.37 — raw depth + colour + intrinsics
   ▼
capture   depth Y16 + colour MJPG + optional D2C alignment
   ▼
pose      MediaPipe Pose (33) + Hands  →  2D landmarks            [M1]
   ▼
skeleton  lift to 3D (mm) → filter → k4abt 32 joints             [M1]
   ▼
transport bodywire/1 UDP datagram, one per frame                  [M0 done]
   ▼
receivers Unity C# / Unreal LiveLink                             [M3]
```

| Layer | Package | Status |
| --- | --- | --- |
| Capture | `bodywire.capture` | ✅ M0 |
| Wire format | `bodywire.transport` | ✅ M0 |
| Skeleton model | `bodywire.skeleton` | ✅ M0 (schema) |
| Pose | `bodywire.pose` | 🚧 M1 |
| Receivers | `receivers/` | 🚧 M3 |

## Requirements

- Windows x64
- Orbbec Astra+ (PID `0x0536` / `0x0636`) — no driver needed, UVC
- OrbbecSDK **1.10.37** (`OrbbecSDK.dll` + `ob_usb.dll` + config XML)
- Python 3.10+
- `numpy`, `opencv-python`

Point the loader at the SDK if it is not in a default location:

```powershell
$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
```

## Quick start

```powershell
python -m pip install -e .

bodywire devices
bodywire probe --frames 10 --save captures\probe
```

`probe` prints every stream profile, starts depth + colour with software D2C,
then reports per-frame depth validity, median distance and intrinsics. `--save`
writes a colour PNG and a depth PNG/NPY for inspection.

## Wire format

See [`proto/bodywire-v1.md`](proto/bodywire-v1.md).

One UDP datagram per frame, 24-byte header + 516 bytes per body:

```
BWR1 | ver=1 | flags | body_count | joint_count=32 | frame_id u64 | ts_us u64
body_id u8 | state u8 | 32 × (x i32, y i32, z i32, conf u8)
```

## Roadmap

- **M0** capture + protocol + schema ← *done*
- **M1** MediaPipe Pose/Hands → 3D lift → 32-joint mapping, preview window
- **M2** `bodywired` daemon: UDP publisher, calibration packet, multi-body
- **M3** Unity receiver + avatar IK, Unreal LiveLink
- **M4** optional `k4abt.dll` shim (not a goal; evaluated last)

## Development

```powershell
python -m pip install -e ".[dev]"
pytest
```

## License

Not chosen yet.