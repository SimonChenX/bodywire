# Unity receiver

Two files, no package dependencies:

| File | Purpose |
| --- | --- |
| `BodywireReceiver.cs` | UDP socket, background parser, latest frame |
| `BodywireSkeletonDebug.cs` | Gizmo rendering of the skeleton |

## Install

1. Copy both files into `Assets/Bodywire/`.
2. Add `BodywireReceiver` to a GameObject. Defaults: bind `0.0.0.0`, port `9871`.
3. Add `BodywireSkeletonDebug` to the same GameObject, enable Gizmos.

## Use

```csharp
using Bodywire;

BodywireFrame frame = receiver.Latest;
foreach (BodywireBody body in frame.bodies)
{
    if (!body.IsTracked) continue;
    Vector3 head = body[BodywireJoint.Head].ToUnity();   // metres, Y up
    byte confidence = body[BodywireJoint.Head].confidence;
}
```

`BodywireFrame`, `BodywireBody` and `BodywireJointData` are plain classes/structs,
so they are safe to keep a reference to for one frame; the receiver swaps in a
new frame object rather than mutating the old one.

## Notes

- The component must be on the main thread (it is a MonoBehaviour).
- Do not call `StartReceiver` twice; `StopReceiver` closes the socket.
- Tested against the protocol unit tests, not compiled in this repository
  (no Unity install on the development machine). The parser mirrors
  `bodywire/transport/protocol.py` exactly.
- See `docs/receivers.md` for confidence handling and coordinate conversion.