---
name: cad-validation
description: Verify CAD geometry, exported round trips and independent design requirements; diagnose FAIL versus technical errors and reject stale reports after source or artifact changes.
---

Read the requirement and model-owned validator/tests before running them.
Measured BREP geometry must establish the intended feature: validity and a
bounding box alone do not prove a through hole, involute profile or assembly.
Reuse the model's checks; do not build a universal geometry validator.

For an existing-model edit, also compare with accepted geometry: distinguish
requested, justified collateral and unexplained material/placement changes.
Unexplained changes block acceptance even when ordinary checks pass. Use the
model-owned narrow contract when applicable; see [local-edits.md](references/local-edits.md)
for the plate bore and V2.1 guide APIs. Outside those scopes define an explicit
model test; never silently widen the allowed region or bless a new baseline.
SHA identifies bytes/freshness, not geometric equality or trustworthy provenance.

Run the existing model, inspect `report.json`, then run its tests and the full
`python -m pytest -q` through the installed environment and bounded executor.
The model's STEP reimport checks must pass. Before relying on a retained report,
compare its source, dependency and artifact SHA-256 with the actual files
using standard Python (README.md has the example). Older reports without
bindings need a rerun. Use a dedicated output directory for an experiment.

Keep four facts separate: requirement, check actually executed, measured result,
unverified property. Read every FAIL and NOT_CHECKED reason. Exit 0 and
matching hashes are not engineering approval. Technical execution failure is not
evidence of a particular geometry defect. Never change expectations solely to
make a failing test pass.

For controlled recovery, preserve a fixed target, introduce one geometry defect
in a task-owned copy, run and observe the specific FAIL, correct source, and
rerun. Check that the old successful report becomes stale after the edit.

If images are required, use existing OCP CAD Viewer `--screenshots` and open
the resulting current PNGs. If unavailable, report that boundary. Images do not
prove numerical dimensions; geometry does not prove strength, fit under heat,
production tolerances or physical assembly. Keep those NOT_CHECKED.
