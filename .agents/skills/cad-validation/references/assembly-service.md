# Assembly and service

Use for required installation/removal, tool access, maintenance or handling.
Start with the operating/service state and the required operation. Establish
which parts stay fixed/mounted, which can be removed or rotated, the permitted
directions/strokes, fastener access, tool envelope and surrounding obstacles.
Do not silently grant extra disassembly, space or degrees of freedom.

Potential failures: a part fits in its final pose but cannot enter/leave; a lid
is trapped by hardware; a driver cannot reach; changing a battery requires
removing a supposedly fixed mounting; a part cannot be retained while fastening.
Choose relevant operations from the actual product's function.

Reuse native intersections, distances and the model-owned placement/motion
checks. Inspect the sequence, including intermediate positions and the relevant
surrounding assembly. Two collision-free endpoints do not prove a clear path.
For an exact simple translational prism an analytic continuous swept envelope
may suffice; distinguish it from a conservative bounding envelope or discrete
sampling. Record path, checked range/step, fixed bodies and removal assumptions.

Ask about missing critical sequence/tool/space requirements. Continue independent
measurements and mark dependent claims NOT_CHECKED; do not invent a convenient
tool or change the service operation to make the model pass.

A measured obstruction on the specified path is a functional FAIL even if
every solid is valid. A clear evaluated path is PASS only for that path and
its stated bodies. Alternative motion is a proposed design/use change, not
acceptance of the original requirement. Force, flexibility, human handling,
comfort and physical durability need evidence beyond collision-free rigid CAD.

Basis: [Boothroyd Dewhurst DFA](https://www.dfma.com/design-for-assembly.asp)
and function/failure reasoning; the detailed provenance and limitations are in
[research](../../../../docs/engineering-review/sources.md).
