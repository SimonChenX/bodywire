# 排错

[English](../en/troubleshooting.md) | [简体中文](troubleshooting.md)

## `OrbbecSDK.dll not found`

把 `BODYWIRE_ORBBEC_SDK` 指向 SDK 的 `lib` 目录（或 DLL 路径）。

```powershell
$env:BODYWIRE_ORBBEC_SDK = "D:\Orbbec\OrbbecSDK_v1.10.37\SDK\lib"
bodywire check
```

加载器还需要同目录下的 `ob_usb.dll`。

## `no Orbbec device found`

- 重新插拔相机（两端），优先用主板后置 USB 3.0。
- 设备管理器 → 相机，应看到 `Orbbec(R) Astra(TM) 3D Camera`。
- `bodywire devices` 应显示 `Astra+ (pid=0x0636 ...)`。
- 可能有别的进程占着相机（OrbbecViewer、JUMPWORK、Zoom），先关掉。

## 日志出现 `get firmware data failed ... bad magic`

Astra+ 在 UVC 控制通道上的已知问题，SDK 会自动回退到厂商接口，设备正常
工作。忽略即可。

## 深度有效率很低

结构光对以下场景无效：

- 阳光直射、强红外源
- 镜子、抛光地板、窗户
- 黑色/深色衣服
- 距离小于约 0.6 m 或大于约 8 m

普通室内大约 20–40% 有效像素。管线只需要关键点所在位置有深度。

## `pose=none`

- 画面里没人，或者人太近/太远。
- 相机对着墙——用 `bodywire probe --save captures\x` 抓一张
  `bodywire_probe_color.png` 看看。
- 光线太暗或严重逆光。
- 模型文件缺失（`bodywire check`）。

## 骨架抖动或突然跳变

- 关节经常消失时，调大 `SkeletonFilter` 的 `hold_ms`。
- 想要更平滑就调低 `min_cutoff`（代价是延迟）。
- 看 `confidence`：脊柱、锁骨、脚这些推导关节的质量取决于源关键点。

## 帧率低

USB 2.0 下 `bodywire run` 一般 20–25 fps（采集本身是 30 fps）：

- 换 USB 3.0
- 降低彩色分辨率（`--width 480 --height 360`）
- 只测深度时用 `--no-color`（没有姿态）

## `address already in use` / 收不到包

- 已有另一个 `bodywire run` 或接收端占用了端口。
- Windows 下 `netstat -ano | findstr 9871` 找占用进程。
- 跨机接收时防火墙可能拦 UDP，允许专用网络。

## 预览窗口打不开

`--show` 需要交互式桌面会话。远程桌面通常可以，纯后台会话无法创建窗口，
改用 `--save`。

## D2C 回退成未对齐

固件拒绝软件 D2C 时，日志会显示 `aligned=False`，校准包报
`coordinate_space: "depth"`。姿态仍可用，但关键点采样在彩色网格、深度在
原生网格，最好保持 D2C 开启（Astra+ 固件 1.0.18 支持）。

## MediaPipe 警告

```
WARNING: Logging before InitGoogle() is written to STDERR
Feedback manager requires a model with a single signature inference
```

MediaPipe/TFLite 的启动噪声，每个进程只打印一次，无害。

## Unity 收不到帧

- 接收端绑定 `0.0.0.0:9871`；确认 `bodywire run --host` 指向 Unity 所在机器。
- Windows 防火墙要放行 UDP 9871。
- 首次导入后可能需要重启编辑器。

## Unreal 插件编译失败

插件只提供源码，本仓库没有 Unreal 环境，未编译验证。要求：

- UE 5.1+
- 模块依赖 `Core`、`CoreUObject`、`Engine`、`Sockets`
- 在项目插件列表里启用 `Bodywire`

## JUMPWORK 一直显示 `Camera Status: Connecting`

- 确认 `bodywire jumpwork` 已启动，且 `%TEMP%\jumporin_shared_memory` 存在。
- 端口必须是 `11102`（游戏内写死，除非场景改过）。
- 官方 `jumpworker_pose.exe` 不随游戏提供；用 bodywire 的服务替代。
- 详见 [jumpwork.md](jumpwork.md)。