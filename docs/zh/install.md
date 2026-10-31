# 安装

[English](../en/install.md) | [简体中文](install.md)

## 环境要求

| 项目 | 说明 |
| --- | --- |
| Windows 10/11 x64 | Linux 理论可行但未测试，Orbbec SDK 路径不同 |
| Orbbec Astra+ | PID `0x0536` / `0x0636`，UVC，无需厂商驱动 |
| USB 3.0 口 | USB 2.0 也能跑 640x480，但带宽紧张 |
| Python 3.10+ | 3.13 已验证 |
| OrbbecSDK 1.10.37 | `OrbbecSDK.dll`、`ob_usb.dll`、`OrbbecSDKConfig_v1.0.xml` |

## 1. 准备 Orbbec SDK

下载 **OrbbecSDK v1.10.37**（Windows），保持 `lib` 目录完整：

```
OrbbecSDK_v1.10.37/
  SDK/lib/OrbbecSDK.dll
  SDK/lib/ob_usb.dll
  SDK/config/OrbbecSDKConfig_v1.0.xml
```

bodywire 按以下顺序查找 SDK：

1. `BODYWIRE_ORBBEC_SDK`（DLL 路径或其所在目录）
2. `<repo>/vendor/orbbec/OrbbecSDK.dll`
3. `D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib\OrbbecSDK.dll`
4. `C:\Program Files\Orbbec\OrbbecSDK\lib\OrbbecSDK.dll`

放在别处时设置环境变量：

```powershell
$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
```

## 2. 安装 bodywire

```powershell
git clone git@github.com:SimonChenX/bodywire.git
cd bodywire
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[pose,jumpwork,dev]"
```

- `[pose]`：MediaPipe
- `[jumpwork]`：WebSocket + AES（JUMPWORK 服务需要）
- `[dev]`：pytest

## 3. 下载 MediaPipe 模型

模型不提交到仓库（约 14 MB）：

```powershell
python tools\download_models.py
```

生成：

- `models/pose_landmarker_lite.task`
- `models/hand_landmarker.task`

可用 `--model-dir` 或 `BODYWIRE_MODEL_DIR` 改位置。

## 4. 自检

```powershell
bodywire check
```

预期输出：

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

抓原始帧：

```powershell
bodywire probe --frames 10 --save captures\probe
```

看姿态预览：

```powershell
bodywire probe --pose --show --depth-view --frames 300
```