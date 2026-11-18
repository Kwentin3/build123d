---
name: cad-entry
description: Start or resume a build123d CAD task in this lab; locate model sources, requirements, reports and the relevant CAD skill without loading every specialty.
---

Use the repository root (contains `models/` and `requirements.txt`). Geometry is
editable Python in `models/<name>/`; outputs belong in `output/<name>/` or a
task-owned variant directory. Read that model's README (root README for plate)
and current task first.
Keep independent products separate; an inherited release may explicitly reuse
older geometry. Use the installed environment; do not change build123d core.

Before selecting checks, identify the affected function, its required operating
or service state, and a plausible way it could fail. A surface type does not
establish purpose: a round hole is not necessarily a fastener hole. Keep the
function/requirement, assumptions and evidence in the existing model task or
README, not a second registry. For an ordinary local edit, cover only affected
functions and protected behaviour.

Read only the relevant engineering reference when the task needs it:
- Load-bearing attachment/retention or a cut affecting its support:
  [attachment and load path](../cad-validation/references/attachment-load-path.md).
- A mating interface whose motion or retention depends on dimensions:
  [functional fit](../cad-validation/references/functional-fit.md).
- Installation, removal, tool access or maintenance:
  [assembly and service](../cad-validation/references/assembly-service.md).
Manufacturing checks remain process-specific in **cad-manufacturing**.

For a small edit, load **cad-modeling** and **cad-validation** only. For joints,
placement, interference or motion, load **cad-assembly**. Load **cad-manufacturing**
only for process choice or production output. Each lives beside this directory,
in `../<skill-name>/SKILL.md`. Do not read all skills or all model READMEs.
Read [WORKFLOW.md](../../../WORKFLOW.md) when planning a new design or a release;
a local parameter edit only needs its affected steps. When delegating a bounded
task, read its section on transferring work; reuse native subagents and files.

Tools compute; skills guide their use. Existing model CLIs and model-owned
validators are the tools. Read the report's measurements, failed checks and
reasons for NOT_CHECKED before accepting it.

On resumption: inspect Git changes, the model README/task requirements, then
compare the report's source/dependency/artifact SHA-256 with the actual files
(the short standard Python example is in README.md). A missing binding or
changed input is unverified; rerun the affected model and checks. Keep decisions
and remaining steps in the existing task record, without copying report data.
Windows execution follows the user's managed executor; Linux uses its own
bounded execution policy. No viewer is required for numerical checks.
