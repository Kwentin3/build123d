# Functional fit

Use when movement, location, sealing or retention depends on a mating interface.
Establish the function, counterpart, functional datum/alignment, assembly state,
intended relative movement and source of the critical dimension limits.

Potential failures include unintended interference, excessive freedom, wrong
axis/location or inability to reach the required seated position. Select the
failure relevant to the interface; nominal diameter is only one input.

Measure the actual features and positions with the model's existing OCCT
checks. For an ordinary coaxial round clearance with supplied limit sizes,
compute the bore-min minus shaft-max and bore-max minus shaft-min bounds.
This simple interval does not include positional/form tolerances, temperature,
deformation or process variation unless separately specified and evaluated.
Use the model's appropriate method for other interfaces; do not generalize this
formula to threads, snap fits or seals.

Keep nominal clearance, manufacturing allowance and guaranteed functional fit
distinct. Obtain critical tolerance/source/process data; do not turn a chosen
CAD gap into an OEM tolerance, assign ISO fit classes without their allowed
source, invent a thread or claim GD&T conformity from a nominal solid.

A measured nominal interference violates a stated no-interference requirement
and can be FAIL. Nominal clearance can be PASS while manufactured fit remains
NOT_CHECKED without limit sizes and process evidence. Physical assembly,
frictional retention, seal performance, wear and thermal behaviour need their
own applicable evidence. Record missing critical inputs and next action.

Basis: official [ISO 286-1 scope](https://www.iso.org/standard/45975.html),
[ASME Y14.5 scope](https://www.asme.org/codes-standards/find-codes-standards/y14-5-dimensioning-tolerancing).
No paid standard tables are reproduced; see the
[source boundaries](../../../../docs/engineering-review/sources.md).
