---
name: cad-assembly
description: Analyze CAD assemblies, joints, placement, clearances, interference and assembly paths; distinguish sampled geometric kinematics from physical dynamics or strength.
---

Read only the chosen assembly README, its parameters, placement/motion
definitions and validator. Identify which body moves, fixed bodies, contact
surfaces and independent target clearances. Reuse native Locations/Planes,
intersections and the model's existing motion checks.

For an existing joint, measure current geometry before proposing a local
change. Use an isolated variant for experiments; preserve approved releases.
Validate final placement and affected intermediate positions. Record sampling
step/range and whether contact/interference was measured as volume, distance
or another criterion. A sampled path is not a continuous collision proof.
Constrained/reverse movements and missing parts can invalidate a plausible
assembly sequence; inspect what the validator actually covers.

`models/mangal_v21/` is a product example, not a generic joint library. Its
`make_model`, `validate_geometry` and tests own that release's assumptions;
load their implementation for this product only. Its inherited helpers remain
at their current owners. Do not copy V-seats or dimensional rules into skills.

Load `../cad-validation/SKILL.md` for evidence and freshness. Load
`../cad-manufacturing/SKILL.md` if a proposed clearance depends on a real cutting
process. Geometry/kinematics cannot confirm friction, manual forces, stability,
hot strength, thermal distortion, durability or a physical assembly trial.
