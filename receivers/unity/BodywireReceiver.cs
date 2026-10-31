// bodywire/1 receiver for Unity.
//
// Drop this file into Assets/Bodywire/ and add the component to a GameObject.
// It listens on a UDP port in a background thread and exposes the latest
// frame on the main thread. Coordinates are converted from bodywire's
// right-handed, Y-down, millimetre frame to Unity's left-handed, Y-up, metre
// frame: (x/1000, -y/1000, z/1000).
//
// Protocol: proto/bodywire-v1.md

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

namespace Bodywire
{
    public enum BodywireJoint
    {
        Pelvis = 0,
        SpineNavel = 1,
        SpineChest = 2,
        Neck = 3,
        ClavicleLeft = 4,
        ShoulderLeft = 5,
        ElbowLeft = 6,
        WristLeft = 7,
        HandLeft = 8,
        HandTipLeft = 9,
        ThumbLeft = 10,
        ClavicleRight = 11,
        ShoulderRight = 12,
        ElbowRight = 13,
        WristRight = 14,
        HandRight = 15,
        HandTipRight = 16,
        ThumbRight = 17,
        HipLeft = 18,
        KneeLeft = 19,
        AnkleLeft = 20,
        FootLeft = 21,
        HipRight = 22,
        KneeRight = 23,
        AnkleRight = 24,
        FootRight = 25,
        Head = 26,
        Nose = 27,
        EyeLeft = 28,
        EarLeft = 29,
        EyeRight = 30,
        EarRight = 31,
    }

    [Serializable]
    public struct BodywireJointData
    {
        public Vector3 positionMm;
        public byte confidence; // 0 none, 1 low, 2 medium, 3 high

        public Vector3 ToUnity() =>
            new Vector3(positionMm.x * 0.001f, -positionMm.y * 0.001f, positionMm.z * 0.001f);
    }

    public sealed class BodywireBody
    {
        public byte id;
        public byte trackingState; // 0 not tracked, 1 inferred, 2 tracked
        public BodywireJointData[] joints = new BodywireJointData[BodywireConstants.JointCount];

        public bool IsTracked => trackingState != 0;

        public BodywireJointData this[BodywireJoint joint] => joints[(int)joint];
    }

    public sealed class BodywireFrame
    {
        public ulong frameId;
        public ulong timestampUs;
        public byte flags;
        public List<BodywireBody> bodies = new List<BodywireBody>();
    }

    public static class BodywireConstants
    {
        public const int JointCount = 32;
        public const int HeaderSize = 24;
        public const int BodyHeaderSize = 4;
        public const int JointSize = 16;
        public const int DefaultPort = 9871;
        public static readonly byte[] Magic = { (byte)'B', (byte)'W', (byte)'R', (byte)'1' };
        public static readonly byte[] ControlMagic = { (byte)'B', (byte)'W', (byte)'C', (byte)'1' };
    }

    /// <summary>Receives bodywire/1 skeleton frames over UDP.</summary>
    public sealed class BodywireReceiver : MonoBehaviour
    {
        [Header("Transport")]
        [SerializeField] private string bindAddress = "0.0.0.0";
        [SerializeField] private int port = BodywireConstants.DefaultPort;
        [SerializeField] private bool autoStart = true;

        [Header("Runtime")]
        [SerializeField] private bool logWarnings = true;

        public BodywireFrame Latest { get; private set; }
        public string LatestCalibrationJson { get; private set; }
        public bool IsRunning => _running;

        private UdpClient _client;
        private Thread _thread;
        private volatile bool _running;
        private readonly object _lock = new object();
        private BodywireFrame _pending;
        private string _pendingCalibration;
        private bool _dirty;

        private void Start()
        {
            if (autoStart) StartReceiver();
        }

        private void OnDestroy() => StopReceiver();

        public void StartReceiver()
        {
            if (_running) return;
            try
            {
                _client = new UdpClient(new IPEndPoint(IPAddress.Parse(bindAddress), port));
                _client.Client.ReceiveTimeout = 500;
                _running = true;
                _thread = new Thread(ReceiveLoop) { IsBackground = true, Name = "bodywire" };
                _thread.Start();
            }
            catch (Exception exc)
            {
                Debug.LogError($"[bodywire] failed to bind udp {bindAddress}:{port}: {exc.Message}");
                _running = false;
            }
        }

        public void StopReceiver()
        {
            _running = false;
            try { _client?.Close(); } catch { /* ignore */ }
            _client = null;
            if (_thread != null && _thread.IsAlive) _thread.Join(500);
            _thread = null;
        }

        private void ReceiveLoop()
        {
            var remote = new IPEndPoint(IPAddress.Any, 0);
            while (_running)
            {
                try
                {
                    byte[] data = _client.Receive(ref remote);
                    if (data.Length >= 4 && Matches(data, 0, BodywireConstants.ControlMagic))
                    {
                        HandleControl(data);
                        continue;
                    }
                    BodywireFrame frame = ParseFrame(data);
                    if (frame == null) continue;
                    lock (_lock)
                    {
                        _pending = frame;
                        _dirty = true;
                    }
                }
                catch (SocketException)
                {
                    // Receive timeout or the socket was closed while stopping.
                }
                catch (ObjectDisposedException)
                {
                    return;
                }
                catch (Exception exc)
                {
                    if (logWarnings) Debug.LogWarning($"[bodywire] parse error: {exc.Message}");
                }
            }
        }

        private void Update()
        {
            lock (_lock)
            {
                if (!_dirty) return;
                Latest = _pending;
                if (_pendingCalibration != null)
                {
                    LatestCalibrationJson = _pendingCalibration;
                    _pendingCalibration = null;
                }
                _dirty = false;
            }
        }

        public bool TryGetBody(int index, out BodywireBody body)
        {
            BodywireFrame frame = Latest;
            if (frame != null && index >= 0 && index < frame.bodies.Count)
            {
                body = frame.bodies[index];
                return true;
            }
            body = null;
            return false;
        }

        // -- parsing ----------------------------------------------------
        private void HandleControl(byte[] data)
        {
            if (data.Length < 8) return;
            int length = data[6] | (data[7] << 8);
            if (data.Length < 8 + length) return;
            byte type = data[5];
            if (type != 1) return; // 1 = calibration
            string json = System.Text.Encoding.UTF8.GetString(data, 8, length);
            lock (_lock) _pendingCalibration = json;
        }

        private static BodywireFrame ParseFrame(byte[] data)
        {
            if (data.Length < BodywireConstants.HeaderSize) return null;
            if (!Matches(data, 0, BodywireConstants.Magic)) return null;
            if (data[4] != 1) return null;

            byte flags = data[5];
            int bodyCount = data[6];
            int jointCount = data[7];
            if (jointCount != BodywireConstants.JointCount) return null;

            var frame = new BodywireFrame
            {
                frameId = ReadU64(data, 8),
                timestampUs = ReadU64(data, 16),
                flags = flags,
            };

            int offset = BodywireConstants.HeaderSize;
            for (int b = 0; b < bodyCount; b++)
            {
                if (offset + BodywireConstants.BodyHeaderSize > data.Length) return null;
                var body = new BodywireBody
                {
                    id = data[offset],
                    trackingState = data[offset + 1],
                };
                int n = data[offset + 2];
                offset += BodywireConstants.BodyHeaderSize;
                if (n != BodywireConstants.JointCount) return null;
                if (offset + n * BodywireConstants.JointSize > data.Length) return null;

                for (int j = 0; j < n; j++)
                {
                    body.joints[j] = new BodywireJointData
                    {
                        positionMm = new Vector3(
                            ReadI32(data, offset),
                            ReadI32(data, offset + 4),
                            ReadI32(data, offset + 8)),
                        confidence = data[offset + 12],
                    };
                    offset += BodywireConstants.JointSize;
                }
                frame.bodies.Add(body);
            }
            return frame;
        }

        private static bool Matches(byte[] data, int offset, byte[] magic)
        {
            for (int i = 0; i < magic.Length; i++)
                if (data[offset + i] != magic[i]) return false;
            return true;
        }

        private static int ReadI32(byte[] b, int o) =>
            b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24);

        private static ulong ReadU64(byte[] b, int o)
        {
            ulong value = 0;
            for (int i = 7; i >= 0; i--) value = (value << 8) | b[o + i];
            return value;
        }
    }
}