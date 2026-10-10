// OpenFOAM v2412 src/finiteVolume/finiteVolume/gradSchemes/gaussGrad/gaussGrad.H, verbatim lines 33-35, 64-67, 86, 156
/*
Description
    Basic second-order gradient scheme using face-interpolation
    and Gauss' theorem.
*/
// ...
class gaussGrad
:
    public fv::gradScheme<Type>
{
// ...
    TypeName("Gauss");
// ...
};
