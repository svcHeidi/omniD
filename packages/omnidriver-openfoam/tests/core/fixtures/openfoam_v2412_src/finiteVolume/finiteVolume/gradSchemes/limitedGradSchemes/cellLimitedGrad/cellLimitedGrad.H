// OpenFOAM v2412 src/finiteVolume/finiteVolume/gradSchemes/limitedGradSchemes/cellLimitedGrad/cellLimitedGrad.H, verbatim lines 64-68, 101, 153
class cellLimitedGrad
:
    public fv::gradScheme<Type>,
    public Limiter
{
// ...
    TypeName("cellLimited");
// ...
};
