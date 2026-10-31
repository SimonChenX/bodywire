# bodywire

Markerless full-body tracking from an **Orbbec Astra+** (depth + RGB), streamed
as **k4abt-compatible skeletons over UDP**.

Any app written around Azure Kinect Body Tracking (`k4abt`) can consume
bodywire with a thin receiver — no Azure depth engine, no Kinect, no `k4a.dll`
replacement.

```
Astra+ ──► OrbbecSDK ──► MediaPipe Pose/Hands ──► 3D lift ──► 32 joints ──► UDP
```

## Status

| Layer | Package | Status |
| --- | --- | --- |
| Capture (depth + colour + D2C) | `bodywire.capture` | ✅ tested on Astra+ |
| Pose (33 + 21/hand) | `bodywire.pose` | ✅ MediaPipe 1.2 |
| 3D lift + mapping + filter | `bodywire.skeleton` | ✅ unit-tested |
| Wire format + control packets | `bodywire.transport` | ✅ unit-tested |
| Daemon (`bodywire run`) | `bodywire.daemon` | ✅ end-to-end on hardware |
| Python receiver | `bodywire.receiver` | ✅ tested |
| Unity receiver | `receivers/unity` | ⚠️ source only (no Unity here) |
| Unreal receiver | `receivers/unreal` | ⚠️ source only (no UE here) |

Not a goal: replacing `k4a.dll`/`k4abt.dll` as binaries. See
[`docs/architecture.md`](docs/architecture.md#why-not-replace-k4adll).

## Quick start

```powershell
git clone git@github.com:SimonChenX/bodywire.git
cd bodywire
python -m pip install -e ".[pose,dev]"
python tools\download_models.py

$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
bodywire check
bodywire probe --pose --show --depth-view
```

Publish to a receiver:

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire listen --port 9871
```

## Commands

| Command | Purpose |
| --- | --- |
| `bodywire devices` | list Orbbec devices |
| `bodywire check` | SDK, camera, models, python deps |
| `bodywire probe` | raw depth/colour stats, `--profiles` for the full list |
| `bodywire probe --pose --show` | live pose + skeleton preview |
| `bodywire run` | daemon: capture → infer → publish |
| `bodywire listen` | reference receiver / debug print |

## Output contract

32 joints in `k4abt_joint_id_t` order, millimetres, right-handed, **+X right,
+Y down, +Z forward**, confidence `0..3`. One UDP datagram per frame:

```
BWR1 | ver | flags | body_count | joint_count=32 | frame_id u64 | ts_us u64
body_id | state | 32 × (x i32, y i32, z i32, conf u8)
```

`BWC1` control datagrams carry calibration (intrinsics, D2C state) and
heartbeats. Full spec: [`proto/bodywire-v1.md`](proto/bodywire-v1.md).

## Receivers

```text
bodywire (mm): +X right, +Y down, +Z forward
Unity   (m):   ( x, -y,  z) / 1000
Unreal  (cm):  ( z,  x, -y) / 100
```

See [`docs/receivers.md`](docs/receivers.md). Unity needs two `.cs` files;
Unreal is a small runtime plugin; Python is built in.

## Performance

Measured on the development machine (RTX 3090, Astra+ on **USB 2.0**):

```
depth 640x480@30 Y16 + colour 640x480@30 MJPG, D2C aligned
bodywire run: ~21 fps, MediaPipe Pose Lite on CPU
```

Capture alone runs at 30 fps. A USB 3.0 link and a lower colour resolution help.

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/install.md`](docs/install.md) | SDK layout, env vars, models, verification |
| [`docs/running.md`](docs/running.md) | commands, daemon flags, preview, performance |
| [`docs/architecture.md`](docs/architecture.md) | layers, coordinates, filtering, limits |
| [`docs/receivers.md`](docs/receivers.md) | Unity / Unreal / Python integration |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | device, depth, pose and network issues |
| [`proto/bodywire-v1.md`](proto/bodywire-v1.md) | wire format |

## Development

```powershell
python -m pip install -e ".[pose,dev]"
pytest
```

Tests cover packet round-trips, control datagrams, the UDP receiver, joint
ordering, 3D lift math, mapping and the temporal filter. They do not need a
camera.

## Limitations

- one tracked body (format supports more; pipeline does not yet)
- no finger articulation beyond palm / middle tip / thumb tip
- requires colour; depth-only mode has no pose
- structured-light depth is noisy on glass, sunlight and black clothing

## License

Not chosen yet.