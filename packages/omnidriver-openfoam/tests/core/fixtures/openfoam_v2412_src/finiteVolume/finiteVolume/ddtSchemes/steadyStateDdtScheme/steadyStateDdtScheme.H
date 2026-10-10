// OpenFOAM v2412 src/finiteVolume/finiteVolume/ddtSchemes/steadyStateDdtScheme/steadyStateDdtScheme.H, verbatim lines 32-33, 60-63, 76, 187
/*
Description
    SteadyState implicit/explicit ddt which returns 0.
*/
// ...
class steadyStateDdtScheme
:
    public fv::ddtScheme<Type>
{
// ...
    TypeName("steadyState");
// ...
};
