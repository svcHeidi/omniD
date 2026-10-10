// OpenFOAM v2412 src/finiteVolume/finiteVolume/ddtSchemes/backwardDdtScheme/backwardDdtScheme.C, verbatim lines 60-72
template<class Type>
template<class GeoField>
scalar backwardDdtScheme<Type>::deltaT0_(const GeoField& vf) const
{
    if (mesh().time().timeIndex() < 2)
    {
        return GREAT;
    }
    else
    {
        return deltaT0_();
    }
}
