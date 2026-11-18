---
name: cad-modeling
description: Create or change editable parametric build123d Python geometry in models; use for dimensions, holes and local features, without automatically loading assembly or manufacturing knowledge.
---

Read the selected `models/<name>/README.md` (root README for plate) and
`model.py`; identify named
parameters, units (mm), coordinate convention and existing CLI/API. Change the
smallest source parameter/feature that meets the task. A CLI override is a run
variant, not a persisted source revision. Preserve unrelated model/output files.

Before committing to an attachment or mating feature, establish its function
and the counterpart/hardware contract. Record material/loads, bearing surfaces,
dimensional limits or service assumptions only where they affect this change.
Ask for missing critical inputs; continue independent nominal geometry work
with explicit limits. Do not let self-chosen geometry become its own requirement.
Use the relevant engineering reference linked by **cad-entry** when needed.

Use native build123d/Open Cascade operations and existing helpers first. Keep
parameters near the top and execution under a main guard. For a new independent
model, create `models/<name>/model.py`, its own requirements/checks and
`output/<name>/`; follow the plate example without inheriting its dimensions.
Do not generalize a product's geometry into infrastructure.

Before editing an existing model, capture the accepted source revision and
geometry separately from the candidate. State the allowed feature/parameters,
protected bodies/placements, affected mates and checks. Do not regenerate the
baseline from already edited code or mutate shared baseline shapes in place.
Follow imports/parameter uses for this feature; do not read every product.

Separate intended dimensions from measured geometry: read the task before
changing expectations. Inspect topology/feature checks and reimport STEP after
export. Load `../cad-validation/SKILL.md` for that verification. For placement
or joint/motion changes, load `../cad-assembly/SKILL.md` as well.

Use `.venv/Scripts/python.exe` on Windows (`.venv/bin/python` on Linux).
Existing model scripts accept `--output-dir`; use a variant directory for an
experiment. Retain `contextlib.chdir(output_dir)` plus ASCII basenames around
native STL operations on Windows with Cyrillic parent paths.
