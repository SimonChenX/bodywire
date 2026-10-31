# 架构

[English](../en/architecture.md) | [简体中文](architecture.md)

bodywire 把 Orbbec Astra+ 变成一路无标记人体追踪数据源，输出格式对齐 Azure
Kinect Body Tracking（`k4abt`），但不依赖 Azure 深度引擎。

## 分层

```
Astra+（UVC：深度 + 彩色）
   │  OrbbecSDK 1.10.37（ctypes）          bodywire/capture
   ▼
深度 Y16 + 彩色 MJPG + 内参 + 软件 D2C
   │
   ▼  bodywire/pose
MediaPipe Pose（33）+ Hands（每手 21）  →  PoseResult
   │  bodywire/skeleton/lift
对齐深度采样 + 反投影  →  毫米级 3D 关键点
   │  bodywire/skeleton/mapping
几何推导 + 手部合并    →  32 个 k4abt 关节
   │  bodywire/skeleton/filter
One Euro + 短暂保持     →  稳定骨架
   │  bodywire/transport
bodywire/1 UDP 报文（+ BWC1 控制包）
   ▼
Unity / Unreal / Python / JUMPWORK 接收端
```

## 为什么不做 `k4a.dll` 二进制替换

`k4abt` 依赖微软闭源的 `depthengine_2_0.dll`，而它绑定 Azure Kinect 的标定
模型。把 Astra+ 的深度硬塞进去，几何是错的——这正是 Orbbec K4A Wrapper 把
Astra+ 过滤掉、返回 0 台设备的原因。

bodywire 改为保持**数据契约**兼容：

- 32 个关节，顺序与 `k4abt_joint_id_t` 一致
- 毫米、右手系、+X 右、+Y 下、+Z 前
- 置信度 0..3（none / low / medium / high）
- 同一条轨迹内 `body_id` 稳定

不追求二进制 API 兼容，这是有意取舍。

## 坐标系

| 阶段 | 空间 | 单位 |
| --- | --- | --- |
| Orbbec 原始深度 | 深度相机，X 右 / Y 下 / Z 前 | mm |
| 软件 D2C 之后 | 彩色相机像素网格 | mm |
| `LiftResult.pose_mm` | 彩色相机空间 | mm |
| k4abt 骨架 | 彩色相机空间（校准包中声明） | mm |
| 线上协议 | 同 k4abt | mm（int32） |
| Unity 接收端 | (x, -y, z) / 1000 | m |
| Unreal 接收端 | (z, x, -y) / 100 | cm |

`aligned = true` 时，活动相机是**彩色相机**，校准包里的
`coordinate_space` 会明确说明。

## 为什么选 MediaPipe Pose + Hands

- Pose 给出 33 个点（含脚跟、脚尖、耳朵、眼睛），能覆盖大部分 k4abt 关节。
- Hands 补上 `HAND`、`HANDTIP`、`THUMB`；没有手部结果时这三个关节发
  `confidence = 0`，但**不删除**，保证数组长度固定。
- MediaPipe Tasks 是 Apache-2.0，CPU 上即可实时运行，不需要 GPU 运行时。

## 滤波

每个关节的每个轴过一遍 One Euro（`min_cutoff = 1.0`，`beta = 0.007`）：
运动时响应快，静止时抑制抖动。关节消失后保留最后位置 250ms，置信度置为
`NONE`，之后归零。接收端应把 `NONE` 理解为“保持上一帧，不绘制”。

## 线程模型

守护进程是单线程：采集、推理、UDP 发送、可选预览都在同一个采集循环里，
延迟可预测，也避免 MediaPipe 的线程安全问题。接收端各自跑 socket 循环；
Unity 接收端在后台线程解析，在 `Update` 里换帧。

## 已知限制

- **单人**。`num_poses` 可以调大，但协议和映射按单人实现，只取第一个。
- **没有手指关节**。MediaPipe Hands 有 21 点，这里只映射手掌、中指指尖、
  拇指尖。
- **必须有彩色**。纯深度模式没有姿态。
- **结构光限制**。玻璃、阳光直射、黑色衣服会降低深度有效率，这些帧会
  回退到保持关节。