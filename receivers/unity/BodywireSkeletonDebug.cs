// Minimal debug renderer for BodywireReceiver.
//
// Add to the same GameObject (or assign the receiver) and enable gizmos to see
// the skeleton in the Scene view. For a game view use LineRenderer or
// primitive spheres on top of the joint positions.

using UnityEngine;

namespace Bodywire
{
    [RequireComponent(typeof(BodywireReceiver))]
    public sealed class BodywireSkeletonDebug : MonoBehaviour
    {
        [SerializeField] private bool drawGizmos = true;
        [SerializeField] private float jointRadius = 0.02f;

        private static readonly (BodywireJoint a, BodywireJoint b)[] Bones =
        {
            (BodywireJoint.Pelvis, BodywireJoint.SpineNavel),
            (BodywireJoint.SpineNavel, BodywireJoint.SpineChest),
            (BodywireJoint.SpineChest, BodywireJoint.Neck),
            (BodywireJoint.Neck, BodywireJoint.Head),
            (BodywireJoint.Head, BodywireJoint.Nose),
            (BodywireJoint.Nose, BodywireJoint.EyeLeft),
            (BodywireJoint.Nose, BodywireJoint.EyeRight),
            (BodywireJoint.EyeLeft, BodywireJoint.EarLeft),
            (BodywireJoint.EyeRight, BodywireJoint.EarRight),
            (BodywireJoint.SpineChest, BodywireJoint.ClavicleLeft),
            (BodywireJoint.ClavicleLeft, BodywireJoint.ShoulderLeft),
            (BodywireJoint.ShoulderLeft, BodywireJoint.ElbowLeft),
            (BodywireJoint.ElbowLeft, BodywireJoint.WristLeft),
            (BodywireJoint.WristLeft, BodywireJoint.HandLeft),
            (BodywireJoint.HandLeft, BodywireJoint.HandTipLeft),
            (BodywireJoint.SpineChest, BodywireJoint.ClavicleRight),
            (BodywireJoint.ClavicleRight, BodywireJoint.ShoulderRight),
            (BodywireJoint.ShoulderRight, BodywireJoint.ElbowRight),
            (BodywireJoint.ElbowRight, BodywireJoint.WristRight),
            (BodywireJoint.WristRight, BodywireJoint.HandRight),
            (BodywireJoint.HandRight, BodywireJoint.HandTipRight),
            (BodywireJoint.Pelvis, BodywireJoint.HipLeft),
            (BodywireJoint.HipLeft, BodywireJoint.KneeLeft),
            (BodywireJoint.KneeLeft, BodywireJoint.AnkleLeft),
            (BodywireJoint.AnkleLeft, BodywireJoint.FootLeft),
            (BodywireJoint.Pelvis, BodywireJoint.HipRight),
            (BodywireJoint.HipRight, BodywireJoint.KneeRight),
            (BodywireJoint.KneeRight, BodywireJoint.AnkleRight),
            (BodywireJoint.AnkleRight, BodywireJoint.FootRight),
        };

        private BodywireReceiver _receiver;

        private void Awake() => _receiver = GetComponent<BodywireReceiver>();

        private void OnDrawGizmos()
        {
            if (!drawGizmos || _receiver == null || _receiver.Latest == null) return;

            foreach (BodywireBody body in _receiver.Latest.bodies)
            {
                if (!body.IsTracked) continue;
                Gizmos.color = new Color(0.1f, 0.8f, 1f, 0.9f);
                foreach ((BodywireJoint a, BodywireJoint b) in Bones)
                {
                    BodywireJointData ja = body[a];
                    BodywireJointData jb = body[b];
                    if (ja.confidence == 0 || jb.confidence == 0) continue;
                    Gizmos.DrawLine(ja.ToUnity(), jb.ToUnity());
                }
                foreach (BodywireJointData joint in body.joints)
                {
                    if (joint.confidence == 0) continue;
                    Gizmos.DrawSphere(joint.ToUnity(), jointRadius);
                }
            }
        }
    }
}