# JUMPWORK pose service

[English](jumpwork.md) | [简体中文](../zh/jumpwork.md)

JUMPWORK does **not** read the camera through `LightBuzz.Kinect4Azure` in its
main motion-capture flow. Decompiling `Assembly-CSharp.dll` shows that it:

1. waits for `%TEMP%\jumporin_shared_memory` to contain `python service is ok`,
2. connects to `ws://localhost:11102`,
3. sends AES-encrypted JSON requests, and
4. expects 18 joint positions per frame.

The official `jumpworker_pose.exe` is **not shipped** with the Steam build we
tested, so the game stays at `Camera Status: Connecting` for every camera —
including Azure Kinect.

`bodywire jumpwork` implements that service on top of bodywire's UDP stream.

## Protocol

| Item | Value |
| --- | --- |
| Transport | WebSocket, text frames |
| Cipher | AES-128-CBC, PKCS#7, base64 |
| Key | `1234567890202473` (UTF-8) |
| Initial IV | `1234567890123456` (UTF-8) |
| Handshake | `Request Random IV` → `{"response":"finish","new_iv":"<b64>"}` |
| Request ID | client sends `request_id`, matches responses on `requestId` (echo both) |

Every response is encrypted with the IV that was current when the request
arrived. The IV rotates immediately **after** the `Request Random IV` response
is sent.

### Message flow

```text
client                                   bodywire jumpwork
  │  ws://localhost:11102                      │
  ├─ Request Random IV ───────────────────────►│
  │◄──────────── finish + new_iv (old IV) ─────┤  switch IV
  ├─ Init Camera {camera_mode} ───────────────►│
  │◄──────────────────────── status ok ────────┤
  ├─ Start Camera ────────────────────────────►│
  │◄──────────────────────── status ok ────────┤
  ├─ Send Ske Data ───────────────────────────►│
  │◄──────────────────────── status ok ────────┤
  ├─ Get Ske Data ──────────────── 50 Hz ─────►│
  │◄─ {timestamp, delay, ske_data[18][3]} ─────┤
```

`Get Update Count And Time` returns `{"update_count", "update_time"}`; VR
requests (`Three Point Align`, `Add Trackers`, ...) are acknowledged but not
implemented.

## 18-joint layout

| Index | Meaning | k4abt joint |
| --- | --- | --- |
| 0 | pelvis | PELVIS |
| 1 | thorax | SPINE_CHEST |
| 2 | neck | NECK |
| 3 | left shoulder | SHOULDER_LEFT |
| 4 | left elbow | ELBOW_LEFT |
| 5 | left wrist | WRIST_LEFT |
| 6 | right shoulder | SHOULDER_RIGHT |
| 7 | right elbow | ELBOW_RIGHT |
| 8 | right wrist | WRIST_RIGHT |
| 9 | left hip | HIP_LEFT |
| 10 | left knee | KNEE_LEFT |
| 11 | left ankle | ANKLE_LEFT |
| 12 | left foot | FOOT_LEFT |
| 13 | right hip | HIP_RIGHT |
| 14 | right knee | KNEE_RIGHT |
| 15 | right ankle | ANKLE_RIGHT |
| 16 | right foot | FOOT_RIGHT |
| 17 | head | HEAD |

Coordinates are Unity-style metres: **+X right, +Y up, +Z forward**, converted
from bodywire's millimetres with `(x, -y, z) / 1000`.

The layout is inferred from `SkeProcessSystem.Change18To21()` and
`CheckHipCapture()`. The game derives the 21-joint model itself, so if a pose
looks wrong, adjust `bodywire/jumpwork/mapping.py` first.

## Running

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire jumpwork --port 11102 --bodywire-port 9871
```

Then launch JUMPWORK. It detects the flag file, connects, and (with
`AutoConnectCamera` enabled) enters motion-capture mode automatically.

Verified on the Steam build `JumpWork_11_11`:

```text
Connected Service success!
Camera Init success!
Camera Status: Connected
ServerStatus: MotionCaptureMode
GetSkeData cost = 0-1 ms
```

## Notes

- The key is hardcoded in the game; this service is for **localhost only**. Do
  not expose port 11102 to a network.
- The official service also handles VR trackers; that part is not implemented.
- `%TEMP%\jumporin_shared_memory` is deleted when the service stops.
- If the game is launched first, it waits for the flag file; start the service
  at any time and the game will connect.