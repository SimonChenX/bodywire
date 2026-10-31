# Troubleshooting

## `OrbbecSDK.dll not found`

Set `BODYWIRE_ORBBEC_SDK` to the SDK `lib` directory (or to the DLL path).

```powershell
$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
bodywire check
```

The loader also needs `ob_usb.dll` in the same directory.

## `no Orbbec device found`

- Replug the camera (both ends), prefer a rear USB 3.0 port.
- Check Windows sees it: Device Manager → Cameras should list
  `Orbbec(R) Astra(TM) 3D Camera`.
- `bodywire devices` should show `Astra+ (pid=0x0636 ...)`.
- Another process may hold the camera (OrbbecViewer, JUMPWORK, Zoom). Close it.

## The log shows `get firmware data failed ... bad magic`

Known Astra+ quirk on the UVC control path; the SDK falls back to the vendor
interface and the device works normally. Ignore it.

## Depth has very low `valid` percentage

Structured light fails on:

- direct sunlight or strong IR sources
- mirrors, glossy floors, windows
- black/very dark clothing
- surfaces closer than ~0.6 m or farther than ~8 m

Typical indoor scenes sit at 20–40 % valid pixels. The pipeline only needs
valid depth at the landmarks themselves.

## `pose=none`

- Nobody is in frame, or the person is too close / too far.
- The camera is pointed at a wall — check `bodywire probe --save captures\x`
  and open `bodywire_probe_color.png`.
- Lighting is too dark or heavily back-lit.
- MediaPipe model files are missing (`bodywire check`).

## Skeleton is jittery or snaps

- Raise `hold_ms` (constructor of `SkeletonFilter`) if joints disappear.
- Lower `min_cutoff` for more smoothing (at the cost of latency).
- Check `confidence`: derived joints (spine, clavicle, foot) are only as good as
  their source landmarks.

## Low frame rate

`bodywire run` on USB 2.0 typically reports ~20–25 fps; the capture itself is
30 fps. Options:

- use a USB 3.0 port
- reduce colour resolution (`--width 480 --height 360`)
- keep `--no-color` for pure depth benchmarks (pose is disabled without colour)

## `address already in use` / no packets

- Another `bodywire run` or a receiver is already bound to the port.
- On Windows, `netstat -ano | findstr 9871` finds the owner.
- Firewall may block inbound UDP for receivers on another machine; allow
  private networks.

## Preview window does not open

`--show` needs an interactive desktop session. Over RDP it usually works, but
on a headless session OpenCV cannot create a window — use `--save` instead.

## D2C fell back to unaligned

If the firmware rejects software D2C the daemon logs `aligned=False` and the
calibration packet reports `coordinate_space: "depth"`. Pose still works, but
landmarks are sampled on the colour grid while depth keeps its native grid; for
best results keep D2C enabled (Astra+ firmware 1.0.18 supports it).

## MediaPipe warnings

```
WARNING: Logging before InitGoogle() is written to STDERR
Feedback manager requires a model with a single signature inference
```

Harmless MediaPipe/TFLite startup noise, printed once per process.

## Unity: no frames

- The receiver binds on `0.0.0.0:9871`; make sure `bodywire run --host` points
  at the machine running Unity.
- Windows Firewall must allow inbound UDP 9871.
- Editor may need to be restarted after the first import.

## Unreal: plugin fails to build

The plugin is provided as source and was not compiled in this repository
(no Unreal installation available). Requirements:

- UE 5.1+ (uses `TAtomic`, `FUTF8ToTCHAR`, `FSocket`)
- module dependencies `Core`, `CoreUObject`, `Engine`, `Sockets`
- add `"Bodywire"` to the project's plugin list or enable it in the editor