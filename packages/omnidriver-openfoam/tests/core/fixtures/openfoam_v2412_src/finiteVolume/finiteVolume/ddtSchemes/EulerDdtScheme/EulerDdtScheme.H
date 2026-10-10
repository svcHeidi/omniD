// OpenFOAM v2412 src/finiteVolume/finiteVolume/ddtSchemes/EulerDdtScheme/EulerDdtScheme.H, verbatim lines 32-34, 61-64, 77, 193
/*
Description
    Basic first-order Euler implicit/explicit ddt using only the current and
    previous time-step values.
*/
// ...
class EulerDdtScheme
:
    public ddtScheme<Type>
{
// ...
    TypeName("Euler");
// ...
};
