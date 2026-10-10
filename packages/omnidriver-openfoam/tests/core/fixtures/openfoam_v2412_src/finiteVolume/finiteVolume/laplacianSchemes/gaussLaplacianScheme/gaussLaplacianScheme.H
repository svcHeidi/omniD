// OpenFOAM v2412 src/finiteVolume/finiteVolume/laplacianSchemes/gaussLaplacianScheme/gaussLaplacianScheme.H, verbatim lines 33-34, 61-64, 83, 141
/*
Description
    Basic second-order laplacian using face-gradients and Gauss' theorem.
*/
// ...
class gaussLaplacianScheme
:
    public fv::laplacianScheme<Type, GType>
{
// ...
    TypeName("Gauss");
// ...
};
