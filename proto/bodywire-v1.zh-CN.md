# bodywire/1 报文格式

[English](bodywire-v1.md) | [简体中文](bodywire-v1.zh-CN.md)

状态：**已实现**（`bodywire.transport.protocol`）

传输：**UDP**，每帧一个数据报，单播（默认端口 `9871`）。所有整数为
**小端序**。发送端每个采集帧发一个数据报；接收端应容忍丢包（不重传）。

## 为什么用数据报而不是流

骨架是状态采样，不是字节流。丢一帧无所谓，被丢包阻塞才有问题。每帧一个
数据报把延迟控制在一帧左右，也没有队头阻塞。

## 坐标系

右手系，原点在活动相机：

| 轴 | 方向 |
| --- | --- |
| +X | 右 |
| +Y | 下 |
| +Z | 前（远离相机） |

单位：**毫米**，`int32`。这与 `k4abt_joint_t.position` 一致（k4a 的坐标系），
所以 +Y 向下，站在 2 m 外的人 `z ≈ 2000`。

开启软件 D2C 时，原点在**彩色相机**（深度图位于彩色像素网格）。需要精确
深度相机坐标时，请参考校准包。

## 数据报布局

### 头部（24 字节）

| 偏移 | 大小 | 字段 | 说明 |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | ASCII `BWR1` |
| 4 | 1 | `version` | `1` |
| 5 | 1 | `flags` | 保留，`0` |
| 6 | 1 | `body_count` | `0..255` |
| 7 | 1 | `joint_count` | `32` |
| 8 | 8 | `frame_id` | `u64`，单调递增 |
| 16 | 8 | `timestamp_us` | `u64`，设备时钟，微秒 |

### 人体记录（`4 + 16 × joint_count` 字节）

| 偏移 | 大小 | 字段 | 说明 |
| --- | --- | --- | --- |
| 0 | 1 | `body_id` | 跟踪期间稳定 |
| 1 | 1 | `tracking_state` | `0` 未跟踪，`1` 推断，`2` 跟踪中 |
| 2 | 1 | `joint_count` | `32` |
| 3 | 1 | `reserved` | `0` |
| 4 | 16×N | `joints` | 见下 |

### 关节（16 字节）

| 偏移 | 大小 | 字段 | 说明 |
| --- | --- | --- | --- |
| 0 | 4 | `x_mm` | `i32` |
| 4 | 4 | `y_mm` | `i32` |
| 8 | 4 | `z_mm` | `i32` |
| 12 | 1 | `confidence` | `0..3` = 无/低/中/高 |
| 13 | 3 | `reserved` | `0` |

关节顺序与 `k4abt_joint_id_t` 完全一致：

```
 0 PELVIS           8 HAND_LEFT       16 HANDTIP_RIGHT   24 ANKLE_RIGHT
 1 SPINE_NAVEL      9 HANDTIP_LEFT    17 THUMB_RIGHT     25 FOOT_RIGHT
 2 SPINE_CHEST     10 THUMB_LEFT      18 HIP_LEFT        26 HEAD
 3 NECK            11 CLAVICLE_RIGHT  19 KNEE_LEFT       27 NOSE
 4 CLAVICLE_LEFT   12 SHOULDER_RIGHT  20 ANKLE_LEFT      28 EYE_LEFT
 5 SHOULDER_LEFT   13 ELBOW_RIGHT     21 FOOT_LEFT       29 EAR_LEFT
 6 ELBOW_LEFT      14 WRIST_RIGHT     22 HIP_RIGHT       30 EYE_RIGHT
 7 WRIST_LEFT      15 HAND_RIGHT      23 KNEE_RIGHT      31 EAR_RIGHT
```

`confidence` 对应 `k4abt_joint_confidence_level_t`。模型看不到的关节（例如
没有手部模型时的 `THUMB_*`）必须发 `confidence = 0`，而不是删除，保证数组
长度固定。

## 尺寸

| 内容 | 字节 |
| --- | --- |
| 头部 | 24 |
| 单人体 | 4 + 32×16 = 516 |
| 单人体总计 | 540 |
| 4 人总计 | 2088 |

4 人时会超过常见 1500 字节 MTU，触发 IP 分片。严格要求不分片时保持
`body_count ≤ 2`，或等未来的分片标志。

## 接收端规则

1. `magic` 不是 `BWR1` 或 `version` 不是 `1` 时丢弃。
2. `joint_count != 32` 时丢弃。
3. 忽略 `tracking_state == 0` 的人体。
4. 按 `frame_id` 排序/合并；比已渲染帧更旧的直接丢弃。
5. `confidence == 0` 时短暂保持上一位置（≤ 250 ms），不要瞬间归零。

## 控制报文（`BWC1`）

控制消息与骨架共用端口，用 magic 区分，内容为 JSON，方便向前兼容。

| 偏移 | 大小 | 字段 |
| --- | --- | --- |
| 0 | 4 | magic `BWC1` |
| 4 | 1 | version（`1`） |
| 5 | 1 | type：`1` 校准，`2` 心跳 |
| 6 | 2 | payload 长度（`u16`，小端） |
| 8 | N | UTF-8 JSON |

### 校准（`type = 1`）

启动时发送，之后每 `--calibration-interval` 秒（默认 2 秒）一次。

```json
{
  "type": "calibration",
  "protocol": "bodywire/1",
  "device": {"name": "Astra+", "pid": 1590, "serial_number": "BY1A810004N", "firmware": "1.0.18"},
  "aligned": true,
  "coordinate_space": "color",
  "units": "mm",
  "color": {"fx": 479.32, "fy": 479.32, "cx": 320.46, "cy": 236.52, "width": 640, "height": 480},
  "depth": {"fx": 479.32, "fy": 479.32, "cx": 320.46, "cy": 236.52, "width": 640, "height": 480},
  "depth_profile": "depth 640x480@30 Y16",
  "color_profile": "color 640x480@30 MJPG"
}
```

软件 D2C 正常时 `coordinate_space` 为 `color`；固件回退到原生深度时为
`depth`。接收端应据此决定骨架原点。

### 心跳（`type = 2`）

每秒一次，用来区分“相机停了”和“画面里没人”。

```json
{"type": "heartbeat", "fps": 24.1, "detection_rate": 0.97}
```