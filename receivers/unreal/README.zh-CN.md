# Unreal 接收端

[English](README.md) | [简体中文](README.zh-CN.md)

`Bodywire/` 是一个小型运行时插件，接收 `bodywire/1` 数据报，并暴露成
`FBodywireFrame` / `FBodywireBody` 蓝图结构体。

> 本仓库没有编译验证：开发机没有 Unreal。代码面向 UE 5.1+，只依赖
> `Core`、`CoreUObject`、`Engine`、`Sockets`。请把它当作起点，而不是
> 已验证的二进制。

## 安装

1. 把 `Bodywire` 目录复制到 `YourProject/Plugins/Bodywire`。
2. 启用插件（Edit → Plugins → Input → bodywire）并重启。
3. 如果从其他模块调用，把 `"Bodywire"` 加进
   `PublicDependencyModuleNames`。

## 使用

```cpp
// .h
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
    }
}
```

## 蓝图

- `Start (Port, Bind Address)`、`Stop` 可在蓝图调用。
- `PollFrame` 返回最新帧，在 Event Tick 里调用。
- `GetLatestCalibrationJson` 返回最近一次 `BWC1` 校准包。

## 坐标转换

```text
bodywire (mm): +X 右, +Y 下, +Z 前
Unreal  (cm):  ( z, x, -y ) / 100
```

由 `FBodywireJointData::ToUnrealCm()` 实现。

## 为什么不做成 LiveLink 插件

LiveLink source 需要引擎内编译验证，而且和 LiveLink API 绑定较紧。这里的
结构体刻意保持与引擎无关，你可以自己接到 LiveLink、自定义动画节点或媒体
管线，只需一层薄适配。