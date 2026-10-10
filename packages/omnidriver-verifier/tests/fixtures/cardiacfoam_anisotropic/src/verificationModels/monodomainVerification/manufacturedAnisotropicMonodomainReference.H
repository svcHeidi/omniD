// cardiacFOAM 277dfeb1933990da366d4b30dd9ef40b3e94c87c src/verificationModels/monodomainVerification/manufacturedAnisotropicMonodomainReference.H, verbatim lines 61-64, 80, 84, 105-106, 111-112, 114-116, 142, 143, 150-152, 154-156, 158-160, 162-169, 174
        F[cellI] =
            Foam::sqr(Foam::sin(pi*c.x()))
           *Foam::sqr(Foam::sin(pi*c.y()))
           *Foam::sqr(Foam::sin(pi*c.z()));
// ...
    const scalar sqrt1t = Foam::sqrt(1.0 + t);
// ...
        V[cellI] = sqrt1t*F[cellI];
// ...
    const scalar sqrt1t = Foam::sqrt(1.0 + t);
    const scalar inv1t = 1.0/(1.0 + t);
// ...
        const scalar G =
            1.0 + c.x()*Foam::sqr(c.y())*Foam::pow(c.z(), 3);
// ...
        u1[cellI] = (1.0 + t)*G + sqrt1t*F[cellI];
        u2[cellI] = inv1t*Foam::pow(G, -0.5);
        u3[cellI] = 0.0;
// ...
    const scalar piSqr = Foam::sqr(pi);
// ...
    const scalar sqrt1t = Foam::sqrt(1.0 + t);
// ...
        const scalar sx2 = Foam::sqr(Foam::sin(pi*c.x()));
        const scalar sy2 = Foam::sqr(Foam::sin(pi*c.y()));
        const scalar sz2 = Foam::sqr(Foam::sin(pi*c.z()));
// ...
        const scalar dx = pi*Foam::sin(2.0*pi*c.x());
        const scalar dy = pi*Foam::sin(2.0*pi*c.y());
        const scalar dz = pi*Foam::sin(2.0*pi*c.z());
// ...
        const scalar dxx = 2.0*piSqr*Foam::cos(2.0*pi*c.x());
        const scalar dyy = 2.0*piSqr*Foam::cos(2.0*pi*c.y());
        const scalar dzz = 2.0*piSqr*Foam::cos(2.0*pi*c.z());
// ...
        const scalar F = sx2*sy2*sz2;
        const scalar divKGradF =
            K.xx()*dxx*sy2*sz2
          + K.yy()*sx2*dyy*sz2
          + K.zz()*sx2*sy2*dzz
          + (K.xy() + K.yx())*dx*dy*sz2
          + (K.xz() + K.zx())*dx*sy2*dz
          + (K.yz() + K.zy())*sx2*dy*dz;
// ...
        source[cellI] = sqrt1t*(beta*F - divKGradF);
