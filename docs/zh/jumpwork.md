# JUMPWORK pose 服务

[English](../en/jumpwork.md) | [简体中文](jumpwork.md)

JUMPWORK 的主动捕流程**并不**通过 `LightBuzz.Kinect4Azure` 读相机。
反编译 `Assembly-CSharp.dll` 可以看到它：

1. 等待 `%TEMP%\jumporin_shared_memory` 内容为 `python service is ok`，
2. 连接 `ws://localhost:11102`，
3. 发送 AES 加密的 JSON 请求，
4. 每帧期望 18 个关节位置。

我们测试的 Steam 版本**没有附带**官方 `jumpworker_pose.exe`，所以无论接
什么相机（包括 Azure Kinect），游戏都会停在 `Camera Status: Connecting`。

`bodywire jumpwork` 就是在 bodywire 的 UDP 流之上实现了这个服务。

## 协议

| 项目 | 值 |
| --- | --- |
| 传输 | WebSocket 文本帧 |
| 加密 | AES-128-CBC，PKCS#7，base64 |
| Key | `1234567890202473`（UTF-8） |
| 初始 IV | `1234567890123456`（UTF-8） |
| 握手 | `Request Random IV` → `{"response":"finish","new_iv":"<b64>"}` |
| 请求 ID | 客户端发 `request_id`，按 `requestId` 匹配响应（两个都回显） |

每个响应都用“请求到达时”的 IV 加密。`Request Random IV` 的响应发出去
**之后**，双方才切换到新 IV。

### 消息流程

```text
客户端                                   bodywire jumpwork
  │  ws://localhost:11102                      │
  ├─ Request Random IV ───────────────────────►│
  │◄──────────── finish + new_iv（旧 IV）──────┤  切换 IV
  ├─ Init Camera {camera_mode} ───────────────►│
  │◄──────────────────────── status ok ────────┤
  ├─ Start Camera ────────────────────────────►│
  │◄──────────────────────── status ok ────────┤
  ├─ Send Ske Data ───────────────────────────►│
  │◄──────────────────────── status ok ────────┤
  ├─ Get Ske Data ──────────────── 50 Hz ─────►│
  │◄─ {timestamp, delay, ske_data[18][3]} ─────┤
```

`Get Update Count And Time` 返回 `{"update_count", "update_time"}`；VR 相关
请求（`Three Point Align`、`Add Trackers` 等）会回 ok，但未实现。

## 18 关节布局

| 索引 | 含义 | k4abt 关节 |
| --- | --- | --- |
| 0 | 骨盆 | PELVIS |
| 1 | 胸 | SPINE_CHEST |
| 2 | 颈 | NECK |
| 3 | 左肩 | SHOULDER_LEFT |
| 4 | 左肘 | ELBOW_LEFT |
| 5 | 左腕 | WRIST_LEFT |
| 6 | 右肩 | SHOULDER_RIGHT |
| 7 | 右肘 | ELBOW_RIGHT |
| 8 | 右腕 | WRIST_RIGHT |
| 9 | 左髋 | HIP_LEFT |
| 10 | 左膝 | KNEE_LEFT |
| 11 | 左踝 | ANKLE_LEFT |
| 12 | 左脚 | FOOT_LEFT |
| 13 | 右髋 | HIP_RIGHT |
| 14 | 右膝 | KNEE_RIGHT |
| 15 | 右踝 | ANKLE_RIGHT |
| 16 | 右脚 | FOOT_RIGHT |
| 17 | 头 | HEAD |

坐标是 Unity 风格的米制：**+X 右、+Y 上、+Z 前**，由 bodywire 的毫米坐标
按 `(x, -y, z) / 1000` 转换。

布局是从 `SkeProcessSystem.Change18To21()` 和 `CheckHipCapture()` 推断的。
游戏自己会派生 21 关节模型，所以姿势不对时先调
`bodywire/jumpwork/mapping.py`。

## 运行

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire jumpwork --port 11102 --bodywire-port 9871
```

然后启动 JUMPWORK。它检测到 flag 文件后自动连接；启用
`AutoConnectCamera` 时会直接进入动作捕捉模式。

在 Steam 版本 `JumpWork_11_11` 上实测：

```text
Connected Service success!
Camera Init success!
Camera Status: Connected
ServerStatus: MotionCaptureMode
GetSkeData cost = 0-1 ms
```

## 说明

- Key 是游戏里写死的，这个服务只适合 **本机 localhost**，不要把 11102
  暴露到网络。
- 官方服务还处理 VR tracker，这部分未实现。
- 服务停止时会删除 `%TEMP%\jumporin_shared_memory`。
- 如果先启动游戏，它会一直等 flag 文件；之后随时启动服务都能连上。