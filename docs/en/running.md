# Running bodywire

[English](running.md) | [简体中文](../zh/running.md)


## Commands

| Command | Purpose |
| --- | --- |
| `bodywire devices` | list Orbbec devices visible to the SDK |
| `bodywire check` | SDK + camera + models + python deps |
| `bodywire probe` | raw depth/colour stats |
| `bodywire probe --pose` | pose + skeleton stats |
| `bodywire probe --pose --show --depth-view` | live preview window |
| `bodywire run` | capture → infer → publish over UDP |
| `bodywire listen` | receive and print packets (reference receiver) |
| `bodywire jumpwork` | serve JUMPWORK's pose-service protocol |

## Preview

```powershell
bodywire probe --pose --show --depth-view
```

- green: MediaPipe pose connections
- yellow: hands
- blue: k4abt skeleton projected back through the depth (sanity check that
  the 3D lift matches the 2D landmarks)
- right pane: depth colour map (300–4000 mm)
- `q` / `Esc`: quit

If the projected blue skeleton does not sit on the green landmarks, the depth
intrinsics or the D2C alignment are wrong — check the calibration packet.

## Daemon

```powershell
bodywire run --host 127.0.0.1 --port 9871
```

Options worth knowing:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--host` / `--port` | `127.0.0.1:9871` | UDP destination |
| `--duration` | `0` | stop after N seconds (0 = forever) |
| `--no-color` | off | depth only (no pose; useful for bandwidth tests) |
| `--preview` | off | show the OpenCV preview while publishing |
| `--depth-view` | off | add the depth pane to the preview |
| `--calibration-interval` | `2.0` | seconds between `BWC1` calibration packets |
| `--body-id` | `1` | id assigned to the tracked body |
| `--quiet` | off | suppress status lines |

Output includes a calibration packet on start, a heartbeat every second, and
one skeleton datagram per captured frame. With no person in view the datagrams
still flow with `body_count = 0`, which receivers can use as a liveness signal.

## Receiving

```powershell
bodywire listen --port 9871
bodywire listen --port 9871 --json
```

Typical frame line:

```
frame 120: body=1 state=2 head=(40,-120,1950)mm conf=3 pelvis=(0,0,2050)mm
```

## JUMPWORK service

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire jumpwork --port 11102 --bodywire-port 9871
```

The service writes `%TEMP%\jumporin_shared_memory`; JUMPWORK connects to
`ws://localhost:11102` automatically. See [jumpwork.md](jumpwork.md).

## Network notes

- Datagrams are unencrypted and unauthenticated; bind to `127.0.0.1` or a
  trusted LAN only.
- One body is 540 bytes, well under a 1500-byte MTU. More than two bodies may
  fragment.
- Windows Firewall may prompt on first `run`; allow private networks.

## Performance

Measured on the development machine (RTX 3090, USB 2.0 link):

```
frames=280 fps=21.5 detections=0%
```

Capture alone runs at 30 fps; MediaPipe Pose Lite on CPU is the bottleneck.
Expect ~20–30 fps on a modern desktop. If you need more:

- lower the colour resolution (e.g. 480x360) with `--width/--height`
- run pose every other frame and reuse joints
- use a USB 3.0 link so depth and colour do not contend for bandwidth

## Logs

The SDK prints to stdout. bodywire patches the SDK config once into
`%LOCALAPPDATA%\bodywire\OrbbecSDKConfig_v1.0.xml` raising the console log level
to `WARN`, so only real warnings/errors appear.