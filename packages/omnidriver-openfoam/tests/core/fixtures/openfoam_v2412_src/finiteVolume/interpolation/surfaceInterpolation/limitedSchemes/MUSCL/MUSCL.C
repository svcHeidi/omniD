// OpenFOAM v2412 src/finiteVolume/interpolation/surfaceInterpolation/limitedSchemes/MUSCL/MUSCL.C, verbatim lines 36-47
    makeLimitedSurfaceInterpolationScheme(MUSCL, MUSCLLimiter)
    makeLimitedVSurfaceInterpolationScheme(MUSCLV, MUSCLLimiter)

    makeLLimitedSurfaceInterpolationTypeScheme
    (
        limitedMUSCL,
        LimitedLimiter,
        MUSCLLimiter,
        NVDTVD,
        magSqr,
        scalar
    )
