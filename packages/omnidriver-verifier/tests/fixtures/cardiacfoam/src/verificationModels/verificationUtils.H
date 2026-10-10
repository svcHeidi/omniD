// cardiacFOAM 277dfeb1933990da366d4b30dd9ef40b3e94c87c src/verificationModels/verificationUtils.H, verbatim lines 74, 216-220, 241-244
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
