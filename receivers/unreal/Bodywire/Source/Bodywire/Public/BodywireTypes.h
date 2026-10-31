// bodywire/1 types for Unreal Engine.
//
// bodywire sends millimetres in a right-handed frame with +X right, +Y down
// and +Z forward. Unreal uses centimetres, +X forward, +Y right, +Z up.
// ToUnrealCm() performs that conversion; keep the raw millimetre value if you
// need to compare against the wire protocol.

#pragma once

#include "CoreMinimal.h"
#include "BodywireTypes.generated.h"

UENUM(BlueprintType)
enum class EBodywireJoint : uint8
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
};

USTRUCT(BlueprintType)
struct FBodywireJointData
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    FVector PositionMm = FVector::ZeroVector;

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    uint8 Confidence = 0;

    FVector ToUnrealCm() const
    {
        // bodywire: X right, Y down, Z forward (mm)
        // Unreal:   X forward, Y right, Z up (cm)
        return FVector(PositionMm.Z * 0.1, PositionMm.X * 0.1, -PositionMm.Y * 0.1);
    }
};

USTRUCT(BlueprintType)
struct FBodywireBody
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    uint8 Id = 0;

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    uint8 TrackingState = 0;

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    TArray<FBodywireJointData> Joints;

    bool IsTracked() const { return TrackingState != 0; }

    const FBodywireJointData& Get(EBodywireJoint Joint) const
    {
        static const FBodywireJointData Empty;
        const int32 Index = static_cast<int32>(Joint);
        return Joints.IsValidIndex(Index) ? Joints[Index] : Empty;
    }
};

USTRUCT(BlueprintType)
struct FBodywireFrame
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    uint64 FrameId = 0;

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    uint64 TimestampUs = 0;

    UPROPERTY(BlueprintReadOnly, Category = "bodywire")
    TArray<FBodywireBody> Bodies;

    bool IsValid() const { return FrameId != 0 || Bodies.Num() > 0; }
};