// cardiacFOAM d684422bc085c40bd8a08a633e5c6e517d32626b src/ionicModels/verificationModels/monodomainFDAManufactured/monodomainFDAManufactured_2014.H, verbatim lines 52-53, 57, 61, 65, 80-84
    CONSTANTS[Cm]  = 2.0;
    CONSTANTS[Chi] = 3.0;
// ...
        CONSTANTS[Beta] = -1.1;
// ...
        CONSTANTS[Beta] = -5.9;
// ...
        CONSTANTS[Beta] = -8.6;
// ...
    RATES[V] = 0.0;
    RATES[u1] = pow(STATES[u1] + STATES[u3] - STATES[V], 2.0) * pow(STATES[u2], 2.0) + 0.5 * (STATES[u1] + STATES[u3] - STATES[V]) * pow(STATES[u2], 2.0) * (STATES[V] - STATES[u3]);
    RATES[u2] = - (STATES[u1] + STATES[u3] - STATES[V]) *  pow(STATES[u2], 3);
    RATES[u3] = 0;
    ALGEBRAIC[Iion] =  - 0.5*CONSTANTS[Cm] * (STATES[u1] + STATES[u3] - STATES[V])  * pow(STATES[u2], 2) * (STATES[V] - STATES[u3]) + (CONSTANTS[Beta] * (STATES[V] - STATES[u3])) / CONSTANTS[Chi];
