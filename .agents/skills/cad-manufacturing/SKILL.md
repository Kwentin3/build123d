---
name: cad-manufacturing
description: Prepare process-specific production artifacts from validated CAD, including flat sheet DXF, STEP, BOM and release documentation; load laser-cutting guidance only when that process applies.
---

Establish the intended process/material/thickness and required deliverables from
the task. Reuse the model's exporters and document generator. Do not infer
manufacturing readiness from valid solids or a successful export.

Choose DFM checks only for the declared process and material, with the source
and applicability of their limits. Missing process inputs do not justify a
default wall thickness, fastener edge distance or shrink allowance. For a
functional mating dimension read
[functional fit](../cad-validation/references/functional-fit.md); separate
nominal BREP clearance from manufactured limit sizes and physical fit.

For laser-cut sheet work, read [references/laser-cutting.md](references/laser-cutting.md).
For another process, obtain its actual constraints before adding a reference.
Keep product dimensions, joint topology and release rules in the model.

Check produced files, units, quantities and their source revision. Reimport
STEP; inspect DXF contours and scale using existing numerical checks. Separate
artifact generation from physical approval. Release only files associated with
the current report, with explicit unverified properties. Read
`../cad-validation/SKILL.md` for provenance and acceptance.
