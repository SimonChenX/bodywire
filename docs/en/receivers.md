# Receivers

All receivers parse the same `bodywire/1` datagram (see
[`proto/bodywire-v1.md`](../proto/bodywire-v1.md)).

| Platform | Path | Status |
| --- | --- | --- |
| Python | `bodywire/receiver.py`, `bodywire listen` | tested |
| Unity | `receivers/unity/` | not compiled here (no Unity install) |
| Unreal | `receivers/unreal/Bodywire/` | not compiled here (no UE install) |

## Coordinate conversion

bodywire → engine:

```text
bodywire (mm):      +X right, +Y down, +Z forward
Unity   (m):        ( x, -y,  z) / 1000
Unreal  (cm):       ( z,  x, -y) / 100
```

## Confidence

| Value | Meaning | Receiver behaviour |
| --- | --- | --- |
| 3 | high | use |
| 2 | medium | use, optionally smooth more |
| 1 | low | use with care; may be geometrically derived |
| 0 | none | do **not** draw; hold the previous transform (≤250 ms) |

`HAND`, `HANDTIP` and `THUMB` are `0` whenever MediaPipe Hands did not find that
hand. They are still present in the array, so parsers must never index by
"number of visible joints".

## Unity

1. Copy `receivers/unity/*.cs` into `Assets/Bodywire/`.
2. Add `BodywireReceiver` to a GameObject (default port `9871`).
3. Optionally add `BodywireSkeletonDebug` to the same object and enable Gizmos.

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

Notes:

- Packets are parsed on a background thread; `Latest` is swapped in `Update`.
- `LatestCalibrationJson` contains the last calibration packet (intrinsics).
- Driving a humanoid is application-specific: map joints to
  `HumanBodyBones`, solve rotations from bone directions, or use an IK package.

## Unreal

1. Copy `receivers/unreal/Bodywire` into `YourProject/Plugins/Bodywire`.
2. Enable the plugin and restart the editor.
3. Create a `UBodywireReceiver` and call `Start(9871)`.
4. Call `PollFrame` from `Tick` and consume `FBodywireFrame`.

```cpp
// Header
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
        // drive a component / LiveLink subject here
    }
}
```

Notes:

- `PollFrame` drains the socket queue and returns the newest frame; call it once
  per tick.
- Positions are provided as `FVector PositionMm`; use `ToUnrealCm()` for engine
  space, or keep millimetres for comparison with the wire spec.
- LiveLink: the skeleton arrays are plain structs, so publishing them to a
  LiveLink subject is a thin adapter; it is not included because it requires an
  engine build to validate.

## Python

```python
from bodywire.receiver import SkeletonReceiver

with SkeletonReceiver(port=9871) as rx:
    while True:
        frame = rx.poll()
        if frame and frame.bodies:
            print(frame.bodies[0].joint("HEAD"))
```

## Multi-body

The wire format supports up to 255 bodies, but the current daemon publishes one
(`--body-id`). Multi-body requires per-body tracking in the pipeline; it is on
the roadmap, not implemented.