// OpenFOAM v2412 src/finiteVolume/finiteVolume/convectionSchemes/gaussConvectionScheme/gaussConvectionScheme.H, verbatim lines 32-33, 60-63, 81, 141
/*
Description
    Basic second-order convection using face-gradients and Gauss' theorem.
*/
// ...
class gaussConvectionScheme
:
    public fv::convectionScheme<Type>
{
// ...
    TypeName("Gauss");
// ...
};
