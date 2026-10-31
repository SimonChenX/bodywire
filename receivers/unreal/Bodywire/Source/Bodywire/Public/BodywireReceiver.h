// UBodywireReceiver: non-blocking bodywire/1 UDP receiver for Unreal.
//
// Create it from C++ or a Blueprint (it is a UObject), call Start(), then
// PollFrame() from Tick. PollFrame drains all queued datagrams and returns the
// newest skeleton frame.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "BodywireTypes.h"
#include "BodywireReceiver.generated.h"

class FSocket;

UCLASS(BlueprintType)
class BODYWIRE_API UBodywireReceiver : public UObject
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "bodywire")
    bool Start(int32 Port = 9871, const FString& BindAddress = TEXT("0.0.0.0"));

    UFUNCTION(BlueprintCallable, Category = "bodywire")
    void Stop();

    UFUNCTION(BlueprintCallable, Category = "bodywire")
    bool PollFrame(FBodywireFrame& OutFrame);

    UFUNCTION(BlueprintPure, Category = "bodywire")
    FString GetLatestCalibrationJson() const { return LatestCalibrationJson; }

    UFUNCTION(BlueprintPure, Category = "bodywire")
    bool IsRunning() const { return Socket != nullptr; }

    virtual void BeginDestroy() override;

private:
    bool ParseFrame(const uint8* Data, int32 Length, FBodywireFrame& OutFrame) const;
    void ParseControl(const uint8* Data, int32 Length);

    FSocket* Socket = nullptr;
    FString LatestCalibrationJson;
    TArray<uint8> Buffer;
};