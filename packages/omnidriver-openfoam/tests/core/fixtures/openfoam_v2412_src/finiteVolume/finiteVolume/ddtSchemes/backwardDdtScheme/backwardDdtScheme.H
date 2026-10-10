// OpenFOAM v2412 src/finiteVolume/finiteVolume/ddtSchemes/backwardDdtScheme/backwardDdtScheme.H, verbatim lines 33-35, 62-65, 89, 212
/*
Description
    Second-order backward-differencing ddt using the current and
    two previous time-step values.
*/
// ...
class backwardDdtScheme
:
    public fv::ddtScheme<Type>
{
// ...
    TypeName("backward");
// ...
};
