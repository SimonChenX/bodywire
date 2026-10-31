# 运行

[English](../en/running.md) | [简体中文](running.md)

## 命令

| 命令 | 用途 |
| --- | --- |
| `bodywire devices` | 列出 Orbbec 设备 |
| `bodywire check` | 检查 SDK、相机、模型、Python 依赖 |
| `bodywire probe` | 原始深度/彩色统计，`--profiles` 看全部模式 |
| `bodywire probe --pose` | 姿态 + 骨架统计 |
| `bodywire probe --pose --show --depth-view` | 实时预览窗口 |
| `bodywire run` | 采集 → 推理 → UDP 发布 |
| `bodywire listen` | 接收并打印报文（参考接收端） |
| `bodywire jumpwork` | 提供 JUMPWORK 的 pose 服务协议 |

## 预览

```powershell
bodywire probe --pose --show --depth-view
```

- 绿色：MediaPipe 2D 关键点
- 黄色：手部
- 蓝色：k4abt 3D 骨架反投影回图像（用来验证 3D 提升是否正确）
- 右侧：深度伪彩色（300–4000 mm）
- `q` / `Esc`：退出

如果蓝色骨架没有贴合绿色关键点，说明内参或 D2C 对齐有问题，先检查校准包。

## 守护进程

```powershell
bodywire run --host 127.0.0.1 --port 9871
```

常用参数：

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `--host` / `--port` | `127.0.0.1:9871` | UDP 目标 |
| `--duration` | `0` | N 秒后停止（0 = 一直跑） |
| `--no-color` | 关 | 只开深度（没有姿态，适合带宽测试） |
| `--preview` | 关 | 发布的同时显示预览 |
| `--depth-view` | 关 | 预览里加深度窗格 |
| `--calibration-interval` | `2.0` | 校准包间隔（秒） |
| `--body-id` | `1` | 分配的身体 ID |
| `--quiet` | 关 | 不打印状态 |

启动时立刻发一个校准包，之后每秒一个心跳；每个采集帧发一个骨架报文。
画面里没人时仍会发送 `body_count = 0` 的报文，接收端可用作存活信号。

## 接收

```powershell
bodywire listen --port 9871
bodywire listen --port 9871 --json
```

典型输出：

```
frame 120: body=1 state=2 head=(40,-120,1950)mm conf=3 pelvis=(0,0,2050)mm
```

## JUMPWORK 服务

```powershell
bodywire run --host 127.0.0.1 --port 9871
bodywire jumpwork --port 11102 --bodywire-port 9871
```

`bodywire jumpwork` 会写 `%TEMP%\jumporin_shared_memory`，JUMPWORK 看到后
自动连接 `ws://localhost:11102`。详见 [jumpwork.md](jumpwork.md)。

## 网络说明

- 报文不加密、不鉴权；只绑定 `127.0.0.1` 或可信局域网。
- 单人体 540 字节，远小于 1500 字节 MTU；超过 2 人可能分片。
- 首次 `run` 时 Windows 防火墙可能弹窗，允许专用网络即可。

## 性能

开发机实测（RTX 3090，Astra+ 走 USB 2.0）：

```
frames=280 fps=21.5 detections=0%
```

纯采集能到 30 fps，瓶颈是 CPU 上的 MediaPipe Pose Lite。现代桌面大约
20–30 fps。想再快：

- 降低彩色分辨率（`--width 480 --height 360`）
- 隔帧跑姿态，复用关节
- 换 USB 3.0，让深度和彩色不抢带宽

## 日志

SDK 会把日志打到 stdout。bodywire 首次运行时会生成
`%LOCALAPPDATA%\bodywire\OrbbecSDKConfig_v1.0.xml`，把控制台日志级别调到
`WARN`，所以只会看到真正的警告/错误。