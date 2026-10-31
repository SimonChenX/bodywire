# 接收端

[English](../en/receivers.md) | [简体中文](receivers.md)

所有接收端解析同一份 `bodywire/1` 报文（见
[`proto/bodywire-v1.md`](../../proto/bodywire-v1.zh-CN.md)）。

| 平台 | 路径 | 状态 |
| --- | --- | --- |
| Python | `bodywire/receiver.py`、`bodywire listen` | 已测试 |
| Unity | `receivers/unity/` | 未在本机编译（没有 Unity） |
| Unreal | `receivers/unreal/Bodywire/` | 未在本机编译（没有 UE） |
| JUMPWORK | `bodywire jumpwork` | 已在游戏内验证 |

## 坐标转换

bodywire → 引擎：

```text
bodywire (mm):  +X 右, +Y 下, +Z 前
Unity   (m):    ( x, -y,  z) / 1000
Unreal  (cm):   ( z,  x, -y) / 100
```

## 置信度

| 值 | 含义 | 接收端行为 |
| --- | --- | --- |
| 3 | 高 | 使用 |
| 2 | 中 | 使用，可多平滑一点 |
| 1 | 低 | 谨慎使用，可能是几何推导出来的 |
| 0 | 无 | **不要绘制**；保持上一帧变换（≤250ms） |

没有手部结果时，`HAND`、`HANDTIP`、`THUMB` 的置信度就是 `0`，但它们在
数组里仍然存在，解析器不能按“可见关节数”索引。

## Unity

1. 把 `receivers/unity/*.cs` 复制到 `Assets/Bodywire/`。
2. 在 GameObject 上挂 `BodywireReceiver`（默认端口 `9871`）。
3. 可选：同一物体加 `BodywireSkeletonDebug`，打开 Gizmos。

```csharp
using Bodywire;
using UnityEngine;

public class FollowHead : MonoBehaviour
{
    public BodywireReceiver receiver;

    void Update()
    {
        if (receiver.TryGetBody(0, out BodywireBody body) && body.IsTracked)
        {
            transform.position = body[BodywireJoint.Head].ToUnity();
        }
    }
}
```

说明：

- 后台线程解析，`Latest` 在 `Update` 里换帧。
- `LatestCalibrationJson` 保存最近一次校准包（内参）。
- 驱动 Humanoid 属于应用层逻辑：把关节映射到 `HumanBodyBones`、由骨骼
  方向解算旋转，或接 IK 插件。

## Unreal

1. 把 `receivers/unreal/Bodywire` 复制到 `YourProject/Plugins/Bodywire`。
2. 启用插件并重启编辑器。
3. 创建 `UBodywireReceiver`，调用 `Start(9871)`。
4. 在 `Tick` 里调用 `PollFrame`，消费 `FBodywireFrame`。

```cpp
// 头文件
UPROPERTY()
TObjectPtr<UBodywireReceiver> Receiver;

// BeginPlay
Receiver = NewObject<UBodywireReceiver>(this);
Receiver->Start(9871);

// Tick
FBodywireFrame Frame;
if (Receiver->PollFrame(Frame))
{
    for (const FBodywireBody& Body : Frame.Bodies)
    {
        if (!Body.IsTracked()) continue;
        const FVector HeadCm = Body.Get(EBodywireJoint::Head).ToUnrealCm();
        // 驱动组件 / LiveLink Subject
    }
}
```

说明：

- `PollFrame` 会清空 socket 队列并返回最新帧，每个 Tick 调一次即可。
- 位置是 `FVector PositionMm`；需要引擎空间时用 `ToUnrealCm()`，需要和
  协议对比时保留毫米。
- LiveLink：这些结构体本身就是普通数据，接 LiveLink Subject 只是薄适配层；
  因为要在引擎里验证，仓库没有内置。

## Python

```python
from bodywire.receiver import SkeletonReceiver

with SkeletonReceiver(port=9871) as rx:
    while True:
        frame = rx.poll()
        if frame and frame.bodies:
            print(frame.bodies[0].joint("HEAD"))
```

## 多人

协议支持最多 255 人，但当前守护进程只发布一人（`--body-id`）。多人需要
管线里做逐人跟踪，属于后续路线，尚未实现。