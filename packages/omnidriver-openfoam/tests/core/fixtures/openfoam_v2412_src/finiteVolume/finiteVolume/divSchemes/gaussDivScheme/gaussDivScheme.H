// OpenFOAM v2412 src/finiteVolume/finiteVolume/divSchemes/gaussDivScheme/gaussDivScheme.H, verbatim lines 32-33, 60-63, 76, 104
/*
Description
    Basic second-order div using face-gradients and Gauss' theorem.
*/
// ...
class gaussDivScheme
:
    public fv::divScheme<Type>
{
// ...
    TypeName("Gauss");
// ...
};
