// cardiacFOAM 15b3e18324d597bc396c3e314f6461143d300301 src/verificationModels/verificationUtils.H, verbatim lines 78, 220-224, 245-248
    return time.value() + 0.5*time.deltaTValue() >= time.endTime().value();
// ...
        const scalar diff = Foam::mag(numeric[i] - exact[i]);
        weightedAbs += volumes[i]*diff;
        weightedSq += volumes[i]*diff*diff;
        totalVolume += volumes[i];
        maxAbs = max(maxAbs, diff);
// ...
            weightedAbs/totalVolume,
            Foam::sqrt(weightedSq/totalVolume)
        ),
        maxAbs
