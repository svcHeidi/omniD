// OpenFOAM v2412 src/finiteVolume/finiteVolume/ddtSchemes/CrankNicolsonDdtScheme/CrankNicolsonDdtScheme.H, verbatim lines 33-35, 63-64, 117-120, 126-130, 159, 214, 326
/*
Description
    Second-oder Crank-Nicolson implicit ddt using the current and
    previous time-step fields as well as the previous time-step ddt.
*/
// ...
/*
    With a coefficient of 1 the scheme is fully centred and second-order,
    with a coefficient of 0 the scheme is equivalent to Euler-implicit.
*/
// ...
class CrankNicolsonDdtScheme
:
    public fv::ddtScheme<Type>
{
// ...
        template<class GeoField>
        class DDt0Field
        :
            public GeoField
        {
// ...
        };
// ...
    TypeName("CrankNicolson");
// ...
};
