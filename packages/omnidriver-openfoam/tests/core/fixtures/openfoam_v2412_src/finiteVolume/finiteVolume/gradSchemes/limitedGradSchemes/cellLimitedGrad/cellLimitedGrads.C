// OpenFOAM v2412 src/finiteVolume/finiteVolume/gradSchemes/limitedGradSchemes/cellLimitedGrad/cellLimitedGrads.C, verbatim lines 57-63, 68-72
#define makeFvLimitedGradTypeScheme(SS, Type, Limiter)                         \
    makeNamedFvLimitedGradTypeScheme(SS##Grad, Type, Limiter, #SS"<"#Limiter">")

#define makeFvLimitedGradScheme(SS, Limiter)                                   \
                                                                               \
    makeFvLimitedGradTypeScheme(SS, scalar, Limiter)                           \
    makeFvLimitedGradTypeScheme(SS, vector, Limiter)
// ...
makeNamedFvLimitedGradTypeScheme(cellLimitedGrad, scalar, minmod, "cellLimited")
makeNamedFvLimitedGradTypeScheme(cellLimitedGrad, vector, minmod, "cellLimited")

makeFvLimitedGradScheme(cellLimited, Venkatakrishnan)
makeFvLimitedGradScheme(cellLimited, cubic)
