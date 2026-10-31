# bodywire

[English](README.md) | [简体中文](README.zh-CN.md)

用 **Orbbec Astra+**（深度 + RGB）做无标记人体追踪，以
**k4abt 兼容骨骼**通过 **UDP** 输出。

任何基于 Azure Kinect Body Tracking（`k4abt`）写的应用，只需一个薄接收端就能
接入 bodywire——不需要 Azure 深度引擎、不需要 Kinect、也不需要替换
`k4a.dll`。

```
Astra+ ──► OrbbecSDK ──► MediaPipe Pose/Hands ──► 3D 提升 ──► 32 关节 ──► UDP
```

## 状态

| 层 | 包 | 状态 |
| --- | --- | --- |
| 采集（深度 + 彩色 + D2C） | `bodywire.capture` | ✅ Astra+ 实测 |
| 姿态（33 + 每手 21） | `bodywire.pose` | ✅ MediaPipe 1.2 |
| 3D 提升 + 映射 + 滤波 | `bodywire.skeleton` | ✅ 单测覆盖 |
| 协议 + 控制包 | `bodywire.transport` | ✅ 单测覆盖 |
| 守护进程（`bodywire run`） | `bodywire.daemon` | ✅ 硬件端到端 |
| Python 接收端 | `bodywire.receiver` | ✅ 已测试 |
| JUMPWORK pose 服务 | `bodywire.jumpwork` | ✅ 游戏内验证 |
| Unity 接收端 | `receivers/unity` | ⚠️ 仅源码（本机无 Unity） |
| Unreal 接收端 | `receivers/unreal` | ⚠️ 仅源码（本机无 UE） |

不做的事：二进制替换 `k4a.dll` / `k4abt.dll`。原因见
[`docs/zh/architecture.md`](docs/zh/architecture.md#为什么不做-k4adll-二进制替换)。

## 快速开始

```powershell
git clone git@github.com:SimonChenX/bodywire.git
cd bodywire
python -m pip install -e ".[pose,jumpwork,dev]"
python tools\download_models.py

$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
bodywire check
bodywire probe --pose --show --depth-view
```

发布给接收端：

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire listen --port 9871
```

## JUMPWORK

JUMPWORK 的动作捕捉走的是本地 **Python pose 服务**，不是 `k4a`。Steam 版本
里没有附带 `jumpworker_pose.exe`，所以即使接 Azure Kinect，游戏也会一直停在
`Camera Status: Connecting`。

`bodywire jumpwork` 用 bodywire 实现了这个服务：

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire jumpwork --port 11102 --bodywire-port 9871
```

在 `JumpWork_11_11` 上实测：

```text
Connected Service success!
Camera Init success!
Camera Status: Connected
ServerStatus: MotionCaptureMode
GetSkeData cost = 0-1 ms
```

协议和 18 关节映射见 [`docs/zh/jumpwork.md`](docs/zh/jumpwork.md)。

## 命令

| 命令 | 用途 |
| --- | --- |
| `bodywire devices` | 列出 Orbbec 设备 |
| `bodywire check` | 检查 SDK、相机、模型、Python 依赖 |
| `bodywire probe` | 原始深度/彩色统计，`--profiles` 看全部模式 |
| `bodywire probe --pose --show` | 实时姿态 + 骨架预览 |
| `bodywire run` | 守护进程：采集 → 推理 → 发布 |
| `bodywire listen` | 参考接收端 / 调试打印 |
| `bodywire jumpwork` | 提供 JUMPWORK pose 服务协议 |

## 输出契约

32 个关节，顺序同 `k4abt_joint_id_t`，毫米，右手系，**+X 右、+Y 下、+Z 前**，
置信度 `0..3`。每帧一个 UDP 数据报：

```
BWR1 | ver | flags | body_count | joint_count=32 | frame_id u64 | ts_us u64
body_id | state | 32 × (x i32, y i32, z i32, conf u8)
```

`BWC1` 控制报文携带校准（内参、D2C 状态）和心跳。完整规范：
[`proto/bodywire-v1.zh-CN.md`](proto/bodywire-v1.zh-CN.md)。

## 接收端

```text
bodywire (mm): +X 右, +Y 下, +Z 前
Unity   (m):   ( x, -y,  z) / 1000
Unreal  (cm):  ( z,  x, -y) / 100
```

见 [`docs/zh/receivers.md`](docs/zh/receivers.md)。Unity 需要两个 `.cs` 文件；
Unreal 是一个小型运行时插件；Python 内置。

## 性能

开发机实测（RTX 3090，Astra+ 走 **USB 2.0**）：

```
depth 640x480@30 Y16 + colour 640x480@30 MJPG, D2C aligned
bodywire run: ~21 fps，MediaPipe Pose Lite 跑在 CPU
```

纯采集 30 fps。换 USB 3.0、降低彩色分辨率还能更快。

## 文档

| 文档 | 内容 |
| --- | --- |
| [`docs/zh/install.md`](docs/zh/install.md) | SDK 布局、环境变量、模型、自检 |
| [`docs/zh/running.md`](docs/zh/running.md) | 命令、守护进程参数、预览、性能 |
| [`docs/zh/architecture.md`](docs/zh/architecture.md) | 分层、坐标系、滤波、限制 |
| [`docs/zh/receivers.md`](docs/zh/receivers.md) | Unity / Unreal / Python 接入 |
| [`docs/zh/jumpwork.md`](docs/zh/jumpwork.md) | JUMPWORK 服务协议与 18 关节映射 |
| [`docs/zh/troubleshooting.md`](docs/zh/troubleshooting.md) | 设备、深度、姿态、网络问题 |
| [`proto/bodywire-v1.zh-CN.md`](proto/bodywire-v1.zh-CN.md) | 报文格式 |

英文版在 [`docs/en/`](docs/en/) 和
[`proto/bodywire-v1.md`](proto/bodywire-v1.md)。

## 开发

```powershell
python -m pip install -e ".[pose,jumpwork,dev]"
pytest
```

测试覆盖报文往返、控制包、UDP 接收、关节顺序、3D 提升数学、映射、时域滤波
和 JUMPWORK 协议，不需要相机。

## 限制

- 单人（协议支持多人，管线尚未实现）
- 没有手指关节，只有手掌 / 中指指尖 / 拇指尖
- 必须有彩色；纯深度模式没有姿态
- 结构光在玻璃、阳光、黑色衣服上噪声较大
- JUMPWORK 的 VR tracker 模式未实现

## 许可证

尚未确定。