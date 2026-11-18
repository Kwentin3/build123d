"""Model-owned functional checks for the teaching holder, not a rules engine.

The continuous sweep below is exact only for this full rectangular cartridge
and specified rigid translation. It is not an arbitrary assembly-path solver.
"""

from build123d import Box, Pos

VOLUME_TOL = 1e-5
SERVICE_STROKE = 90.0  # independently specified in the product brief


def volume(shape):
    return 0.0 if shape is None else sum(s.volume for s in shape.solids())


def symmetric_difference(a, b):
    return volume(a - b) + volume(b - a)


def service_check(parts, stroke=SERVICE_STROKE):
    if stroke is None:
        return dict(status="NOT_CHECKED", reason="Removal stroke/path not supplied",
                    needed="Permitted service motion and fixed bodies", next_action="Ask task owner")
    if stroke <= 0:
        raise ValueError("This fixture's service stroke must be positive")
    frame, cartridge = parts["frame"], parts["cartridge"]
    target = Pos(0, 0, 10) * Box(50, 70, 8)
    if symmetric_difference(cartridge, target) > VOLUME_TOL:
        raise ValueError("Exact sweep is limited to the specified full rectangular cartridge")
    swept = Pos(0, stroke / 2, 10) * Box(50, 70 + stroke, 8)
    collision = volume(frame.intersect(swept))
    final = Pos(0, stroke, 0) * cartridge
    return dict(status="PASS" if collision < VOLUME_TOL else "FAIL",
                initial_collision_mm3=volume(frame.intersect(cartridge)),
                final_collision_mm3=volume(frame.intersect(final)),
                continuous_path_collision_mm3=collision,
                motion=dict(translation_axis="+Y", range_mm=[0, stroke], frame="fixed",
                            other_disassembly=False, rotation=False),
                method="Exact full-prism translation sweep, not endpoint-only sampling",
                requirement="Cartridge replacement by specified straight stroke without frame disassembly")


def review_geometry(parts, stroke=SERVICE_STROKE):
    return dict(
        valid_solids=dict(status="PASS" if all(p.is_valid and len(p.solids()) == 1
                                                for p in parts.values()) else "FAIL"),
        installed_clearance=dict(status="PASS" if volume(parts["frame"].intersect(
            parts["cartridge"])) < VOLUME_TOL else "FAIL"),
        service_path=service_check(parts, stroke),
        structural_capacity=dict(status="NOT_CHECKED",
            reason="Material, fabrication and service loads not provided",
            needed="Material/process, loads and applicable acceptance criterion",
            next_action="Obtain inputs before calculation or physical qualification"),
        manufactured_fit=dict(status="NOT_CHECKED", reason="Only nominal dimensions supplied",
            needed="Limit dimensions and manufacturing process", next_action="Specify and inspect prototype"))
