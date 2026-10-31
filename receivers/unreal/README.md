# Unreal receiver

`Bodywire/` is a small runtime plugin that receives `bodywire/1` datagrams and
exposes them as `FBodywireFrame` / `FBodywireBody` Blueprint structs.

> Not compiled in this repository: the development machine has no Unreal
> installation. The code targets UE 5.1+ and uses only `Core`, `CoreUObject`,
> `Engine` and `Sockets`. Treat it as a starting point, not a tested binary.

## Install

1. Copy the `Bodywire` folder into `YourProject/Plugins/Bodywire`.
2. Enable the plugin (Edit → Plugins → Input → bodywire) and restart.
3. Add `"Bodywire"` to `PublicDependencyModuleNames` if you call the receiver
   from another module.

## Use

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

## Blueprint

- `Start (Port, Bind Address)` and `Stop` are BlueprintCallable.
- `PollFrame` returns the newest frame; call it from Event Tick.
- `GetLatestCalibrationJson` returns the last `BWC1` calibration payload.

## Coordinate conversion

```text
bodywire (mm): +X right, +Y down, +Z forward
Unreal (cm):   ( z, x, -y ) / 100
```

`FBodywireJointData::ToUnrealCm()` implements this.

## Why not a LiveLink plugin?

A LiveLink source would need an engine build to validate and is tightly coupled
to the LiveLink API surface. The structs here are deliberately engine-agnostic
so you can publish them to LiveLink, a custom animation node, or a media
pipeline with a thin adapter.