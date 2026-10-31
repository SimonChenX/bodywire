# Unity 接收端

[English](README.md) | [简体中文](README.zh-CN.md)

两个文件，无第三方依赖：

| 文件 | 用途 |
| --- | --- |
| `BodywireReceiver.cs` | UDP socket、后台解析、最新帧 |
| `BodywireSkeletonDebug.cs` | 用 Gizmos 画骨架 |

## 安装

1. 把两个文件复制到 `Assets/Bodywire/`。
2. 在 GameObject 上挂 `BodywireReceiver`，默认绑定 `0.0.0.0:9871`。
3. 同一物体加 `BodywireSkeletonDebug`，打开 Gizmos。

## 使用

```csharp
using Bodywire;

BodywireFrame frame = receiver.Latest;
foreach (BodywireBody body in frame.bodies)
{
    if (!body.IsTracked) continue;
    Vector3 head = body[BodywireJoint.Head].ToUnity();   // 米，Y 向上
    byte confidence = body[BodywireJoint.Head].confidence;
}
```

`BodywireFrame`、`BodywireBody`、`BodywireJointData` 都是普通类/结构体，可以
安心持有一帧；接收端换的是新对象，不会原地修改旧帧。

## 说明

- 组件必须在主线程（它是 MonoBehaviour）。
- 不要重复调用 `StartReceiver`；`StopReceiver` 会关闭 socket。
- 解析逻辑与 `bodywire/transport/protocol.py` 逐字节一致，但本仓库没有
  Unity 环境，未编译验证。
- 置信度与坐标转换见 [`docs/zh/receivers.md`](../../docs/zh/receivers.md)。