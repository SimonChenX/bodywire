# Installation

[English](install.md) | [简体中文](../zh/install.md)


## Requirements

| Item | Notes |
| --- | --- |
| Windows 10/11 x64 | Linux is possible but untested; the Orbbec SDK path differs |
| Orbbec Astra+ | PID `0x0536` / `0x0636`, UVC, no vendor driver required |
| USB 3.0 port | USB 2.0 works at 640x480 but leaves little bandwidth |
| Python 3.10+ | 3.13 tested |
| OrbbecSDK 1.10.37 | `OrbbecSDK.dll`, `ob_usb.dll`, `OrbbecSDKConfig_v1.0.xml` |

## 1. Get the Orbbec SDK

Download **OrbbecSDK v1.10.37** (Windows) and keep the `lib` directory intact:

```
OrbbecSDK_v1.10.37/
  SDK/lib/OrbbecSDK.dll
  SDK/lib/ob_usb.dll
  SDK/config/OrbbecSDKConfig_v1.0.xml
```

bodywire looks for the SDK in this order:

1. `BODYWIRE_ORBBEC_SDK` (a `.dll` path or its directory)
2. `<repo>/vendor/orbbec/OrbbecSDK.dll`
3. `D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib\OrbbecSDK.dll`
4. `C:\Program Files\Orbbec\OrbbecSDK\lib\OrbbecSDK.dll`

Set the environment variable if you keep it elsewhere:

```powershell
$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
```

## 2. Install bodywire

```powershell
git clone git@github.com:SimonChenX/bodywire.git
cd bodywire
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[pose,jumpwork,dev]"
```

`[pose]` pulls MediaPipe, `[jumpwork]` pulls WebSocket + AES (for the JUMPWORK service), `[dev]` pulls pytest.

## 3. Download the MediaPipe models

Models are not committed (≈14 MB):

```powershell
python tools\download_models.py
```

They land in `models/`:

- `pose_landmarker_lite.task`
- `hand_landmarker.task`

Override the location with `--model-dir` or `BODYWIRE_MODEL_DIR`.

## 4. Verify

```powershell
bodywire check
```

Expected output:

```
OrbbecSDK      1.10.37-main
devices        1
               Astra+ (pid=0x0636, vid=0x2bc5, sn=..., fw=1.0.18, usb=USB3.0)
model dir      ...\models
  pose_landmarker_lite.task    ok (5.8 MB)
  hand_landmarker.task         ok (7.8 MB)
mediapipe      1.2.0
opencv         4.12.0
numpy          2.2.3
```

Then grab raw frames:

```powershell
bodywire probe --frames 10 --save captures\probe
```

and a pose preview:

```powershell
bodywire probe --pose --show --depth-view --frames 300
```