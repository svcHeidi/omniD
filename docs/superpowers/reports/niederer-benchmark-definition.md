# Niederer et al. 2011 N-version benchmark — definition, from the primary source

Source paper: Niederer SA, Kerfoot E, Benson AP, et al. "Verification of cardiac
tissue electrophysiology simulators using an N-version benchmark." *Phil.
Trans. R. Soc. A* 369(1954):4331–4351 (2011). doi:10.1098/rsta.2011.0139.
PMCID: PMC3263775. Retrieved via the PMC/Europe PMC open-access full text and
the article's own Figure 1 image (`rsta20110139-g1.jpg`), 2026-09-26.

## 1. Slab geometry and coordinate frame

> "The tissue geometry was defined as a cuboid, with dimensions of 3×7×20 mm."
(§3b, "Geometry of the tissue model")

Table 3 restates this as **dimensions: 20×7×3 mm**.

> "Fibre directions are defined to be orientated in the long (20 mm) axis of
> the rectangular cuboid." (§3b; Table 3: "fibre orientation — fibres are
> aligned in the long, 20 mm, axis")

**Origin:** the paper never states a numeric (x,y,z) origin or draws axis
arrows. It only describes physical dimensions (3, 7, 20 mm) and refers to
named corners in Figure 1. Figure 1a shows the stimulus cube sitting flush
against one corner of the cuboid, with the 3 mm (height), 7 mm (depth) and
20 mm (fibre/length) edges all meeting there — i.e. the natural origin is
that corner, but this is an inference from the schematic, not a stated
coordinate.

## 2. Stimulus region

> "The stimulus current was delivered to a volume of 1.5×1.5×1.5 mm located
> at one corner of the slab. Defining initial activation in the corner
> ensured that the principal direction of wave propagation was not aligned
> with the fibre orientation..." (§3c, "Boundary conditions and initial
> values")

Table 3: **"stimulation geometry — 1.5×1.5×1.5 mm cube from a corner"**;
**"stimulation protocol — 2 ms at 50 000 μA cm⁻²"** (as printed; this is the
stimulus current density, 50 000 μA cm⁻³ = 5×10⁴ A m⁻³, i.e. Iion units
volumetric — the exponent renders oddly in the extracted text but Table 3's
own units row for current is μA mm⁻² for I_ion, so the stimulus is a
current-density source over the 1.5³ mm³ box). Figure 1a labels the cube "S"
with three 1.5 mm arrows (one per axis) measured from the corner.

The paper does not explicitly write "from t = 0" in the extracted text; the
2 ms duration is given without restating the start time, but every
downstream reproduction (and the paper's own activation-time definition,
"first activation") is consistent with the stimulus starting at t = 0.

## 3. Output points P1–P9 and the diagonal line

Figure 1 caption, panel (b):

> "Summary of points at which activation time was evaluated. Activation
> times at points P1–P9 were evaluated and are available in the electronic
> supplementary material. Plots of the activation time were evaluated along
> the line from P1 to P8..."

§5: "we evaluated activation time at points P1–P9 (labelled in figure 1b),
along a line (blue line in figure 1b)..."

§5b (AMDB website description) gives the clearest verbal definition of P1,
P8 and P9:

> "The time of activation along the line from **the initial corner** to
> **the far corner** is represented as one line on the graph per result...
> a second analysis operation collects the activation times of **the
> corners** of all selected results, as well as calculating the activation
> time at **the centre of the cuboid**."

Reading Figure 1b directly (the 8 cuboid corners as red dots, plus a 9th
interior point):
- **P1** = the corner where the stimulus/wavefront originates (the diagonal
  line starts here; the colour map in the figure is dark blue — earliest
  activation — at this corner, matching Figure 4's "dark blue (0 ms)"
  convention).
- **P8** = the corner diagonally opposite P1 through the volume (differs in
  all three dimensions); the diagonal line terminates here, and the colour
  at that corner is red (latest activation). The paper's discussion
  confirms this is the last-activating point: "the time of last activation
  at the highest spatial and temporal resolutions still differs across the
  codes between 37.8 and 48.7 ms" (§6, Discussion) — this is the published
  per-code *range* at P8, stated in prose, not a table.
- **P9** = the geometric centre of the cuboid (explicit in §5b, quoted
  above): with dimensions 20×7×3 mm this is (10, 3.5, 1.5) mm from the P1
  corner.
- The figure's own wireframe shows vertical construction lines pairing each
  bottom corner with the top corner directly above it: P1–P5, P2–P6, P3–P7,
  P4–P8 (each pair shares two coordinates and differs only in the 3 mm
  axis). P4 is therefore the same (x,y) as P8, i.e. the "far corner" of the
  *bottom* face; P2/P3 and P6/P7 are the two corners adjacent to P1 (one
  displaced along the 7 mm axis, one along the 20 mm axis), but the figure
  does not print numeric coordinates for them, and I could not verify from
  the primary source which of the two remaining directions (7 mm vs 20 mm)
  corresponds to "P2" versus "P3" (and hence "P6" vs "P7") — Figure 1b is a
  schematic with no coordinate axes or numbers on panel (b), and the actual
  per-point numeric table is stated to live only in the electronic
  supplementary material (ESM), which is hosted on the Royal Society
  Publishing site behind a Cloudflare bot-check I did not attempt to bypass
  (per operating constraints). It was not mirrored on PMC or Europe PMC.

**Diagonal line:** explicitly "the line from P1 to P8" (Figure 1 caption;
§5, §5b as "from the initial corner to the far corner"). Endpoints: P1 (the
stimulus corner) and P8 (the diagonally opposite corner) — under the
corner-inference above, (0,0,0) mm to (20,7,3) mm, but see caveat above:
the paper itself never prints these numeric triples.

## 4. Activation-time definition and discretisations

> "The time that the membrane potential passes through 0 mV upon first
> activation was chosen [as the metric]..." (§3f, "Metrics of model
> behaviour")

Units: milliseconds throughout (Δt in ms; all reported activation times in
ms in Figures 2–4 and the Discussion).

Discretisations (§3d, "Numerical methods"; Table 3):
- **Δx = 0.5, 0.2 and 0.1 mm** (spatial, isotropic)
- **Δt = 0.05, 0.01 and 0.005 ms** (temporal, PDE time step)
- All 3×3 = **9 combinations**, run by each of the 11 participating codes
  ("resulting in nine simulation results in total per simulation code").

## 5. Are per-code / consensus activation times tabulated?

**Not as a P1–P9 numeric table in the main text.** What the main text and
figures actually contain:
- **Figure 2**: P8 activation time, one point/line per code, across all 9
  (Δx,Δt) combinations — a plot, not a table of values.
- **Figure 3**: activation time along the P1→P8 line, per code, at three Δx
  (Δt = 0.005 ms fixed) — a plot.
- **Figure 4**: activation time as a 2-D colour map "on the plane shown [in
  fig. 1b]," dark blue (0 ms) to red (130 ms), 10 ms contour bands, for
  highest/lowest Δx at Δt = 0.005 ms — a figure, not numeric data.
- **Table 5**: the L2 norm of the *difference* between codes' activation
  fields at the finest resolution — a derived similarity metric, not raw
  P1–P9 activation times.
- **Discussion (§6, prose only)**: "the time of last activation at the
  highest spatial and temporal resolutions still differs across the codes
  between **37.8 and 48.7 ms**" — the one explicit numeric range given in
  the main text, and it is for P8 only (the "last activation" point), not a
  full P1–P9 table.

**Where the real numbers live:**
> "Activation times at points P1–P9 were evaluated and are available in the
> electronic supplementary material." (Figure 1 caption)

> "the results from each simulation were stored on and are available from
> the AMDB website (formerly euHeartDB [...]) in the form of meshes
> representing the cuboid... Each result is a mesh representing the
> cuboid, with each node recording the time of activation at that point."
> (§5b) — i.e. full per-code activation-time fields (not just P1–P9) were
> deposited at AMDB/euHeartDB (`https://euheartdb.physiomeproject.org/AMDBWebInt/`),
> a site that may or may not still be live 15 years on (not checked here).

So: yes, the paper explicitly says supplementary/downloadable data exists
(ESM + AMDB database), but I could not retrieve either — the ESM lives on
the publisher's site (`royalsocietypublishing.org`), which returned a
Cloudflare interstitial ("Just a moment...") that I did not attempt to
solve, per the constraint against bypassing bot-detection; and I did not
independently verify the AMDB/euHeartDB URL's current availability.

## Comparison with the inferred P1–P9 mapping

Inferred mapping under test:
P1(0,0,0), P2(0,7,0), P3(20,0,0), P4(20,7,0), P5(0,0,3), P6(0,7,3),
P7(20,0,3), P8(20,7,3), P9(10,3.5,1.5) mm; stimulus at the origin corner.

- **P1 = (0,0,0)** — consistent with the primary source: P1 is the corner
  where the stimulus sits and the wave originates (diagonal starts there,
  colour map is "earliest"/blue at that corner in Fig. 1b/Fig. 4's
  convention). High confidence.
- **P8 = (20,7,3)** — consistent: P8 is explicitly the corner diagonally
  opposite P1 ("far corner"), and it's the last-activating point discussed
  in §6. High confidence.
- **P9 = (10,3.5,1.5)** — confirmed near-verbatim: §5b explicitly defines a
  point at "the centre of the cuboid," which for 20×7×3 mm dimensions is
  exactly (10, 3.5, 1.5) mm. High confidence.
- **Vertical pairing (P1–P5, P2–P6, P3–P7, P4–P8 sharing x,y, differing
  only in the 3 mm axis)** — consistent with Figure 1b's own construction
  lines. The inferred mapping's structure (P5=P1+z, P6=P2+z, P7=P3+z,
  P8=P4+z) matches this exactly.
- **P2 vs P3 (and hence P6 vs P7)** — i.e., whether P2 is the corner
  displaced from P1 along the 7 mm axis and P3 along the 20 mm axis (as
  inferred), or the reverse — **could not be verified** from the primary
  source's accessible text/figure. Figure 1b carries no printed axis labels
  or numbers on panel (b), and the only place the actual numbers exist is
  the ESM, which is not accessible from this session. Treat P2/P3/P6/P7 as
  *plausible but unverified* against the primary source; P1, P4 (by
  vertical pairing with P8), P8, and P9 are verified.
- **Origin at the stimulus corner** — the paper's own convention: yes, the
  stimulus is delivered "at one corner of the slab," and that corner is
  demonstrably P1 by the colour-map/diagonal evidence in Figure 1b/Fig. 4.
  The paper never assigns that corner numeric coordinates (0,0,0) itself —
  that much is an added (reasonable) convention, not a direct quote.

## Sources

- Niederer SA et al. (2011), full text via Europe PMC (mirrors PMC3263775):
  https://europepmc.org/article/MED/21969679 (full text loaded from this
  page; section headers: Introduction, Code verification, Virtual
  physiological human benchmark requirements, Benchmark definition,
  Benchmark simulations, Discussion, Conclusions).
- PMC record (redirects to the same full text):
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3263775/ →
  https://pmc.ncbi.nlm.nih.gov/articles/PMC3263775/
- Figure 1 (both panels), full resolution JPEG served by Europe PMC:
  https://europepmc.org/api/fulltextRepo?pmcId=PMC3263775&type=FILE&fileName=rsta20110139-g1.jpg&mimeType=image/jpeg&version=1
  (Figure 1a: slab + stimulus schematic with 3/7/20 mm and 1.5 mm arrows;
  Figure 1b: P1–P9 wireframe + activation-time colour map + P1→P8 diagonal.)
- Publisher record (DOI landing page) — not retrievable in this session,
  blocked by a Cloudflare interstitial:
  https://royalsocietypublishing.org/doi/10.1098/rsta.2011.0139
  — this is presumably where the electronic supplementary material (ESM)
  with the numeric P1–P9 activation-time table is hosted; not accessed.
- AMDB / euHeartDB, named in §5b as the online results database:
  https://euheartdb.physiomeproject.org/AMDBWebInt/ — named in the paper,
  not independently checked for current availability in this session.
- Local repository cross-reference (NOT the primary source; included only
  to flag a discrepancy in axis convention): `niederer_protocol.qmd` in
  the owner's unpublished paper appendix (not in this repository)
  uses its own coordinate frame with the stimulus box at
  `[0,1.5]×[0,1.5]×[5.5,7]` mm and P1=(0,0,7), P8=(20,3,0) — i.e. a
  *different* origin/axis-direction choice than the (0,0,0)-at-stimulus
  convention inferred here from the primary figure. Both can be internally
  self-consistent implementations of the same benchmark; neither is what
  the primary paper itself states in numeric form, since the paper doesn't
  print (x,y,z) coordinates at all.

## Resolution of P2–P7 (2026-09-26, controller)

Source: the owner's own paper, `~/Documents/Latex_papers/ElectrophysiologySolver/sections/paperI_methods_publication/appendices/niederer_protocol.qmd`, table "Probe | Position (mm)" (cardiacFOAM frame: slab 20 × 3 × 7 mm, stimulus box [0,1.5]×[0,1.5]×[5.5,7] mm):
P1 (0,0,7) · P2 (0,0,0) · P3 (20,0,7) · P4 (20,0,0) · P5 (0,3,7) · P6 (0,3,0) · P7 (20,3,7) · P8 (20,3,0) · P9 (10,1.5,3.5).
Labels = cardiacFOAM probe index + 1. In the Niederer frame (20 × 7 × 3 mm, stimulus at origin), via (x, y_cf, z_cf) → (x, 7 − z_cf, y_cf):
P1 (0,0,0) · P2 (0,7,0) · P3 (20,0,0) · P4 (20,7,0) · P5 (0,0,3) · P6 (0,7,3) · P7 (20,0,3) · P8 (20,7,3) · P9 (10,3.5,1.5).
Consistent with every constraint the paper states (P1, P8, P9, vertical pairings); the P2/P3 naming order is the owner's paper's convention, not independently checked against Niederer's ESM. The owner's cardiacFOAM P8 at Δx 0.1 mm = 45.386 ms, inside the paper's 37.8–48.7 ms range.
