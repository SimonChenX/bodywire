# bodywire/1 wire format

Status: **draft, implemented in `bodywire.transport.protocol`**

Transport: **UDP**, one datagram per frame, unicast (default port `9871`).
All integers are **little-endian**. Sender may emit a datagram per captured
frame; receivers should tolerate dropped datagrams (no retransmission).

## Why datagrams, not a stream

A skeleton is a state sample, not a byte stream. Losing a frame is harmless;
blocking on a lost packet is not. One datagram per frame keeps latency at
roughly one frame and removes head-of-line blocking.

## Coordinate system

Right-handed, origin at the active camera:

| Axis | Direction |
| --- | --- |
| +X | right |
| +Y | down |
| +Z | forward (away from the camera) |

Units: **millimetres**, `int32`. This matches `k4abt_joint_t.position`
(k4a's coordinate system), so `+Y` points down and a person standing 2 m away
has `z ≈ 2000`.

When software D2C alignment is enabled, the origin is the **colour** camera
(the depth map lives in the colour pixel grid). Document this in the
calibration packet if precise depth-camera coordinates are required.

## Datagram layout

### Header (24 bytes)

| Offset | Size | Field | Notes |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | ASCII `BWR1` |
| 4 | 1 | `version` | `1` |
| 5 | 1 | `flags` | reserved, `0` |
| 6 | 1 | `body_count` | `0..255` |
| 7 | 1 | `joint_count` | `32` |
| 8 | 8 | `frame_id` | `u64`, monotonically increasing |
| 16 | 8 | `timestamp_us` | `u64`, device clock, microseconds |

### Body record (`4 + 16 × joint_count` bytes)

| Offset | Size | Field | Notes |
| --- | --- | --- | --- |
| 0 | 1 | `body_id` | stable while a body is tracked |
| 1 | 1 | `tracking_state` | `0` not tracked, `1` inferred, `2` tracked |
| 2 | 1 | `joint_count` | `32` |
| 3 | 1 | `reserved` | `0` |
| 4 | 16×N | `joints` | see below |

### Joint (16 bytes)

| Offset | Size | Field | Notes |
| --- | --- | --- | --- |
| 0 | 4 | `x_mm` | `i32` |
| 4 | 4 | `y_mm` | `i32` |
| 8 | 4 | `z_mm` | `i32` |
| 12 | 1 | `confidence` | `0..3` = none/low/medium/high |
| 13 | 3 | `reserved` | `0` |

Joint order is exactly `k4abt_joint_id_t`:

```
 0 PELVIS           8 HAND_LEFT       16 HANDTIP_RIGHT   24 ANKLE_RIGHT
 1 SPINE_NAVEL      9 HANDTIP_LEFT    17 THUMB_RIGHT     25 FOOT_RIGHT
 2 SPINE_CHEST     10 THUMB_LEFT      18 HIP_LEFT        26 HEAD
 3 NECK            11 CLAVICLE_RIGHT  19 KNEE_LEFT       27 NOSE
 4 CLAVICLE_LEFT   12 SHOULDER_RIGHT  20 ANKLE_LEFT      28 EYE_LEFT
 5 SHOULDER_LEFT   13 ELBOW_RIGHT     21 FOOT_LEFT       29 EAR_LEFT
 6 ELBOW_LEFT      14 WRIST_RIGHT     22 HIP_RIGHT       30 EYE_RIGHT
 7 WRIST_LEFT      15 HAND_RIGHT      23 KNEE_RIGHT      31 EAR_RIGHT
```

`confidence` follows `k4abt_joint_confidence_level_t`. Joints a model cannot
observe (e.g. `THUMB_*` without a hand model) must be sent with
`confidence = 0` rather than dropped, so the array size stays fixed.

## Sizes

| Payload | Bytes |
| --- | --- |
| header | 24 |
| one body | 4 + 32×16 = 516 |
| one body total | 540 |
| 4 bodies total | 2088 |

With 4 bodies the datagram exceeds a typical 1500-byte MTU and will be
IP-fragmented. For strict MTU safety keep `body_count ≤ 2`, or enable the
future fragmentation flag.

## Receiver rules

1. Reject datagrams whose `magic` is not `BWR1` or `version` is not `1`.
2. Reject `joint_count != 32`.
3. Ignore bodies with `tracking_state == 0`.
4. Sort/merge by `frame_id`; drop frames older than the last rendered one.
5. On `confidence == 0`, hold the previous position briefly (≤ 250 ms) instead
   of snapping to the origin.

## Optional control datagrams (reserved, not in v1)

A future `BWC1` datagram will carry JSON calibration:

```json
{
  "type": "calibration",
  "color": {"fx": 613.5, "fy": 613.2, "cx": 319.1, "cy": 238.7, "width": 640, "height": 480},
  "depth": {"fx": 570.3, "fy": 570.3, "cx": 319.5, "cy": 239.5, "width": 640, "height": 480},
  "aligned": true,
  "coordinate_space": "color"
}
```

Until then, calibration is out of band (config file or receiver defaults).