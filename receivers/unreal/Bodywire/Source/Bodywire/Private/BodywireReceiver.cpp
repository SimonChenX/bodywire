#include "BodywireReceiver.h"

#include "IPAddress.h"
#include "SocketSubsystem.h"
#include "Sockets.h"

namespace
{
    constexpr uint8 kMagic[4] = {'B', 'W', 'R', '1'};
    constexpr uint8 kControlMagic[4] = {'B', 'W', 'C', '1'};
    constexpr int32 kHeaderSize = 24;
    constexpr int32 kBodyHeaderSize = 4;
    constexpr int32 kJointSize = 16;
    constexpr int32 kJointCount = 32;

    FORCEINLINE int32 ReadI32(const uint8* Data, int32 Offset)
    {
        return static_cast<int32>(
            static_cast<uint32>(Data[Offset]) |
            (static_cast<uint32>(Data[Offset + 1]) << 8) |
            (static_cast<uint32>(Data[Offset + 2]) << 16) |
            (static_cast<uint32>(Data[Offset + 3]) << 24));
    }

    FORCEINLINE uint64 ReadU64(const uint8* Data, int32 Offset)
    {
        uint64 Value = 0;
        for (int32 i = 7; i >= 0; --i)
        {
            Value = (Value << 8) | Data[Offset + i];
        }
        return Value;
    }

    FORCEINLINE bool Matches(const uint8* Data, int32 Offset, const uint8 (&Magic)[4])
    {
        return Data[Offset] == Magic[0] && Data[Offset + 1] == Magic[1] &&
               Data[Offset + 2] == Magic[2] && Data[Offset + 3] == Magic[3];
    }
}

bool UBodywireReceiver::Start(int32 Port, const FString& BindAddress)
{
    if (Socket)
    {
        return true;
    }

    ISocketSubsystem* Subsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
    if (!Subsystem)
    {
        UE_LOG(LogTemp, Error, TEXT("[bodywire] no socket subsystem"));
        return false;
    }

    Socket = Subsystem->CreateSocket(NAME_DGram, TEXT("bodywire"));
    if (!Socket)
    {
        UE_LOG(LogTemp, Error, TEXT("[bodywire] failed to create UDP socket"));
        return false;
    }

    Socket->SetNonBlocking(true);

    TSharedRef<FInternetAddr> Address = Subsystem->CreateInternetAddr();
    bool bValid = false;
    Address->SetIp(*BindAddress, bValid);
    Address->SetPort(Port);
    if (!bValid)
    {
        Address->SetAnyAddress();
    }

    if (!Socket->Bind(*Address))
    {
        UE_LOG(LogTemp, Error, TEXT("[bodywire] failed to bind udp %s:%d"), *BindAddress, Port);
        Socket->Close();
        Subsystem->DestroySocket(Socket);
        Socket = nullptr;
        return false;
    }

    UE_LOG(LogTemp, Log, TEXT("[bodywire] listening on udp %s:%d"), *BindAddress, Port);
    return true;
}

void UBodywireReceiver::Stop()
{
    if (!Socket)
    {
        return;
    }
    ISocketSubsystem* Subsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
    Socket->Close();
    if (Subsystem)
    {
        Subsystem->DestroySocket(Socket);
    }
    Socket = nullptr;
}

void UBodywireReceiver::BeginDestroy()
{
    Stop();
    Super::BeginDestroy();
}

bool UBodywireReceiver::PollFrame(FBodywireFrame& OutFrame)
{
    if (!Socket)
    {
        return false;
    }

    bool bGotFrame = false;
    uint32 Pending = 0;
    while (Socket->HasPendingData(Pending))
    {
        Buffer.SetNumUninitialized(static_cast<int32>(FMath::Min<uint32>(Pending, 65535u)));
        int32 Read = 0;
        if (!Socket->Recv(Buffer.GetData(), Buffer.Num(), Read) || Read <= 0)
        {
            break;
        }

        if (Read >= 4 && Matches(Buffer.GetData(), 0, kControlMagic))
        {
            ParseControl(Buffer.GetData(), Read);
            continue;
        }

        FBodywireFrame Frame;
        if (ParseFrame(Buffer.GetData(), Read, Frame))
        {
            OutFrame = MoveTemp(Frame);
            bGotFrame = true;
        }
    }
    return bGotFrame;
}

bool UBodywireReceiver::ParseFrame(const uint8* Data, int32 Length, FBodywireFrame& OutFrame) const
{
    if (Length < kHeaderSize || !Matches(Data, 0, kMagic) || Data[4] != 1)
    {
        return false;
    }

    const int32 BodyCount = Data[6];
    const int32 JointCount = Data[7];
    if (JointCount != kJointCount)
    {
        return false;
    }

    OutFrame.FrameId = ReadU64(Data, 8);
    OutFrame.TimestampUs = ReadU64(Data, 16);
    OutFrame.Bodies.Reset(BodyCount);

    int32 Offset = kHeaderSize;
    for (int32 b = 0; b < BodyCount; ++b)
    {
        if (Offset + kBodyHeaderSize > Length)
        {
            return false;
        }
        FBodywireBody Body;
        Body.Id = Data[Offset];
        Body.TrackingState = Data[Offset + 1];
        const int32 N = Data[Offset + 2];
        Offset += kBodyHeaderSize;

        if (N != kJointCount || Offset + N * kJointSize > Length)
        {
            return false;
        }

        Body.Joints.SetNum(N);
        for (int32 j = 0; j < N; ++j)
        {
            Body.Joints[j].PositionMm = FVector(
                static_cast<float>(ReadI32(Data, Offset)),
                static_cast<float>(ReadI32(Data, Offset + 4)),
                static_cast<float>(ReadI32(Data, Offset + 8)));
            Body.Joints[j].Confidence = Data[Offset + 12];
            Offset += kJointSize;
        }
        OutFrame.Bodies.Add(MoveTemp(Body));
    }
    return true;
}

void UBodywireReceiver::ParseControl(const uint8* Data, int32 Length)
{
    if (Length < 8 || Data[5] != 1)
    {
        return; // only calibration packets are kept
    }
    const int32 JsonLength = Data[6] | (Data[7] << 8);
    if (Length < 8 + JsonLength)
    {
        return;
    }
    LatestCalibrationJson =
        FString(FUTF8ToTCHAR(reinterpret_cast<const ANSICHAR*>(Data + 8), JsonLength).Get());
}