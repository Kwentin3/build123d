"""Independent nominal CAD checks for the three TFA insert prototypes.

Requirements here are deliberate constants, not imported generator parameters.
Continuous axial swept envelopes establish clearance only for the stated proxy;
they do not establish the unpublished OEM ring, cap, tools or physical retention.
"""

from math import hypot, isclose, isfinite, pi

from build123d import Box, CenterOf, Cylinder, GeomType, Pos, RectangleRounded, extrude
from OCP.BRepAdaptor import BRepAdaptor_Surface

LENGTH_TOL = 1e-5
VOLUME_TOL = 1e-3


def _cylinder(radius, z0, z1, x=0, y=0):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(radius, z1 - z0)


def _volume(shape):
    return 0.0 if shape is None else sum(s.volume for s in shape.solids())


def _close(a, b):
    return isclose(a, b, abs_tol=LENGTH_TOL, rel_tol=0)


def _record(checks, name, passed, actual, expected):
    checks[name] = dict(status="PASS" if passed else "FAIL", actual=actual, expected=expected)


def _cylinders(shape):
    result = []
    for face in shape.faces().filter_by(GeomType.CYLINDER):
        axis = face.axis_of_rotation
        bounds = face.bounding_box()
        # build123d Face.radius returns None for trimmed cylindrical surfaces.
        result.append(dict(radius=BRepAdaptor_Surface(face.wrapped).Cylinder().Radius(),
                           x=axis.position.X, y=axis.position.Y,
                           axial=abs(abs(axis.direction.Z) - 1) < LENGTH_TOL,
                           z0=bounds.min.Z, z1=bounds.max.Z))
    return result


def _has_cylinder(faces, radius, x, y, z0, z1):
    return any(f["axial"] and all(_close(f[k], v) for k, v in
               (("radius", radius), ("x", x), ("y", y), ("z0", z0), ("z1", z1)))
               for f in faces)


def _clear(checks, name, body, probe, explanation):
    collision = _volume(body.intersect(probe))
    _record(checks, name, collision < VOLUME_TOL,
            {"collision_mm3": collision}, explanation)


def _material_ring(shape, x, y, inner, outer, z0, z1):
    ring = _cylinder(outer, z0, z1, x, y) - _cylinder(inner, z0, z1, x, y)
    missing = _volume(ring - shape)
    return missing


def validate_variant(model, expected_clearance):
    """Return measured checks; the caller must retain FAIL and NOT_CHECKED results."""
    if not isfinite(expected_clearance) or not 0 <= expected_clearance <= 2:
        raise ValueError("Expected diametral allowance must be finite, 0..2 mm")
    name, parts = model["name"], model["parts"]
    if name not in ("desk", "wall", "portable"):
        raise ValueError(f"Unknown clock variant: {name}")
    checks = {}
    required = {"body", "lid"} if name == "portable" else {"body"}
    _record(checks, "part_identity", set(parts) == required and
            all(p.label == label for label, p in parts.items()),
            {k: p.label for k, p in parts.items()}, sorted(required))
    for label, part in parts.items():
        _record(checks, f"{label}_occ_valid", part.is_valid, part.is_valid, True)
        _record(checks, f"{label}_solid_count", len(part.solids()) == 1,
                len(part.solids()), 1)
    if "body" not in parts:
        return checks
    body = parts["body"]
    radius = (77 + expected_clearance) / 2
    cylinders = _cylinders(body)
    coaxial = [f for f in cylinders if f["axial"] and _close(f["x"], 0)
               and _close(f["y"], 0) and _close(f["z0"], 0) and _close(f["z1"], 22)]
    _record(checks, "bore_diameter", any(_close(f["radius"], radius) for f in coaxial),
            {"diameters_mm": [2 * f["radius"] for f in coaxial]}, 77 + expected_clearance)
    _record(checks, "bore_axis_depth", _has_cylinder(cylinders, radius, 0, 0, 0, 22),
            coaxial, {"axis_xy_mm": [0, 0], "z_mm": [0, 22], "diameter_mm": 2 * radius})
    _clear(checks, "bore_continuous_clearance", body, _cylinder(radius, 0, 22),
           "Entire nominal socket cylinder is empty, z=0..22 mm")
    _clear(checks, "oem_envelope", body, _cylinder(38.5, 0, 22),
           "Published installation envelope diameter77 x22 mm has no material collision")
    # Union over every translation of each envelope along the stated axial path.
    # This is a continuous sweep, not a selection of collision-free samples.
    _clear(checks, "front_insertion", body,
           _cylinder(38.5, -45, 22) + _cylinder(45, -40, 0),
           {"installation_sweep_z_mm": [-45, 22], "bezel_sweep_z_mm": [-40, 0],
            "method": "Continuous union of axial cylinder envelopes"})
    _clear(checks, "service_clearance", body, _cylinder(38.5, 22, 90),
           {"diameter_mm": 77, "z_mm": [22, 90],
            "precondition": "Portable lid and screws removed; wall variant demounted"})
    # A 0.05mm material probe at the measured front plane tests the whole annular seat.
    missing_seat = _material_ring(body, 0, 0, radius, 45, 0, .05)
    front_planes = [f for f in body.faces().filter_by(GeomType.PLANE)
                    if _close(f.center().Z, 0) and abs(f.normal_at().Z) > 1 - LENGTH_TOL]
    _record(checks, "bezel_seat", bool(front_planes) and missing_seat < VOLUME_TOL,
            {"missing_probe_mm3": missing_seat, "front_planar_area_mm2": sum(f.area for f in front_planes),
             "required_contact_area_mm2": pi * (45**2 - radius**2)},
            "Complete front annulus from actual bore radius to45 mm; planar face z=0")
    depth, relief = (30, 59) if name == "wall" else (28, 49)
    _record(checks, "rear_relief", _has_cylinder(cylinders, relief, 0, 0, 22, depth),
            [f for f in cylinders if _close(f["radius"], relief)],
            {"diameter_mm": 2 * relief, "z_mm": [22, depth]})
    expected_bounds = {
        "desk": (-72, -64, -44, 72, 54, 64),
        "wall": (-70, -70, 0, 70, 70, 30),
        "portable": (-55, -58, 0, 55, 74, 28),
    }[name]
    box = body.bounding_box()
    bounds = [*box.min, *box.max]
    _record(checks, "body_bounds", all(_close(a, b) for a, b in zip(bounds, expected_bounds)),
            bounds, expected_bounds)

    if name == "desk":
        # Material in the ground-contact slab must fill the claimed rectangular support.
        foot = body & (Pos(0, -63.95, 10) * Box(200, .1, 200))
        fb = foot.bounding_box()
        cm = body.center(CenterOf.MASS)
        filled = _close(_volume(foot), 144 * 108 * .1)
        supported = (fb.min.X < min(cm.X, -45) and fb.max.X > max(cm.X, 45)
                     and fb.min.Z < min(cm.Z, -36) and fb.max.Z > max(cm.Z, 36))
        _record(checks, "desk_support", filled and supported,
                {"material_com_xz_mm": [cm.X, cm.Z],
                 "measured_foot_xz_mm": [fb.min.X, fb.max.X, fb.min.Z, fb.max.Z],
                 "contact_slab_volume_mm3": _volume(foot)},
                {"module_com_conservative_xz_mm": [-45, 45, -36, 36],
                 "criterion": "Body CoM and every module CoM in this box lie inside full foot rectangle",
                 "scope": "Gravity -Y, rigid geometry only; no physical stability claim"})
    elif name == "wall":
        holes = all(_has_cylinder(cylinders, 2.25, x, 0, 0, 30) for x in (-60, 60))
        voids = sum(_volume(body.intersect(_cylinder(2.25, 0, 30, x))) for x in (-60, 60))
        # The front load-bearing22mm has material around each hole, independently
        # of the open rear relief. A full1mm radial ring is required here.
        missing = sum(_material_ring(body, x, 0, 2.25, 3.25, 1, 21) for x in (-60, 60))
        _record(checks, "wall_mount_holes", holes and voids < VOLUME_TOL and missing < VOLUME_TOL,
                {"continuous_void_collision_mm3": voids, "missing_1mm_ligament_probe_mm3": missing},
                {"centres_mm": [[-60, 0], [60, 0]], "diameter_mm": 4.5, "z_mm": [0, 30]})
        approach = sum(_volume(body.intersect(_cylinder(4.5, -30, 0, x))) for x in (-60, 60))
        _record(checks, "wall_screw_approach", approach < VOLUME_TOL and 60 - 4.5 > 45,
                {"collision_mm3": approach, "bezel_to_head_radial_gap_mm": 60 - 4.5 - 45},
                "Front axial head/driver cylinder radius4.5 atx=+/-60; hardware selected separately")
        rear_gap = box.max.Z - 22
        _record(checks, "wall_rear_gap", rear_gap >= 8 - LENGTH_TOL,
                rear_gap, "At least8 mm between installation-envelope rear and mounting plane; demount for service")
    else:
        lug_void = _volume(body.intersect(_cylinder(2.5, 0, 8, y=64)))
        missing = _material_ring(body, 0, 64, 2.5, 10, 0, 8)
        _record(checks, "portable_lug", _has_cylinder(cylinders, 2.5, 0, 64, 0, 8)
                and lug_void < VOLUME_TOL and missing < VOLUME_TOL,
                {"hole_collision_mm3": lug_void, "missing_7_5mm_ligament_probe_mm3": missing},
                {"hole_centre_mm": [0, 64], "hole_diameter_mm": 5, "minimum_radial_ligament_mm": 7.5})
        if "lid" in parts:
            lid = parts["lid"]
            lid_cylinders = _cylinders(lid)
            centres = [(x, y) for x in (-46, 46) for y in (-48, 48)]
            holes = all(_has_cylinder(cylinders, 1.7, x, y, 0, 28) and
                        _has_cylinder(lid_cylinders, 1.7, x, y, 28, 31) for x, y in centres)
            missing = sum(_material_ring(part, x, y, 1.7, 6.7, z0, z1)
                          for part, z0, z1 in ((body, 0, 28), (lid, 28, 31)) for x, y in centres)
            _record(checks, "portable_screw_alignment", holes and missing < VOLUME_TOL,
                    {"missing_5mm_web_probe_mm3": missing, "coaxial_cylinders": holes},
                    {"centres_mm": centres, "through_diameter_mm": 3.4,
                     "minimum_web_mm": 5, "hardware": "Four M3x35 through screws plus nuts, removed before lid"})
            hardware_envelopes = {
                "shank": (1.5, 0, 35), "pan_head": (3, -3, 0),
                "nut": (3.3, 31, 33.4), "front_driver": (4, -20, -3),
            }
            collisions = {}
            for hardware, (r, z0, z1) in hardware_envelopes.items():
                collisions[hardware] = sum(
                    _volume(part.intersect(_cylinder(r, z0, z1, x, y)))
                    for part in (body, lid) for x, y in centres)
            module_gap = min(hypot(x, y) - 4 - 45 for x, y in centres)
            _record(checks, "portable_hardware_clearance",
                    all(v < VOLUME_TOL for v in collisions.values()) and module_gap > 0,
                    {"collision_mm3": collisions, "minimum_gap_to_module_frontdisk_mm": module_gap},
                    {"four_axial_envelopes_each": {
                        key: {"radius_mm": r, "z_mm": [z0, z1]}
                        for key, (r, z0, z1) in hardware_envelopes.items()},
                     "module_frontdisk_radius_mm": 45,
                     "scope": "Conservative hardware/driver cylinders; actual hardware and controls require prototype check"})
            lb = lid.bounding_box()
            actual = [*lb.min, *lb.max]
            _record(checks, "lid_bounds", all(_close(a, b) for a, b in
                    zip(actual, (-55, -58, 28, 55, 58, 31))), actual,
                    [-55, -58, 28, 55, 58, 31])
            collision = _volume(body.intersect(lid))
            # Face contact is a geometric mating condition, not a positive retention proof.
            contact = sum(f.area for f in body.touch(lid).faces())
            _record(checks, "lid_mating", collision < VOLUME_TOL and contact > 100,
                    {"collision_mm3": collision, "contact_area_mm2": contact},
                    "No solid overlap; rear-plane contact area>100 mm2")
            swept_lid = Pos(0, 0, 31) * extrude(RectangleRounded(110, 116, 10), amount=49)
            _clear(checks, "lid_removal", body, swept_lid,
                   {"continuous_prism_z_mm": [31, 80], "precondition": "All four through screws removed"})

    for item, reason in {
        "oem_retention_fit": "OEM ring geometry, retention, tolerances and allowed panel thickness unpublished; measure actual module and ring",
        "physical_service": "Actual rear cap, battery, adjustment wheel, tool and fingertip geometry unavailable; envelope sweep alone cannot prove access",
        "strength_and_manufacturing": "No strength, drop, heat, FDM shrinkage, print fit, wall-anchor or physical stability test performed",
    }.items():
        checks[item] = {"status": "NOT_CHECKED", "reason": reason}
    return checks


def check_change(before_parts, after_parts, before_clearance=.4, after_clearance=1.0):
    """Only enlarge the body's coaxial z0..22 bore relative to imported STEP.

    The caller owns immutable accepted STEP provenance; this function never
    regenerates a baseline and never fills or heals any baseline material.
    """
    if not all(isfinite(v) and 0 <= v <= 2 for v in (before_clearance, after_clearance)):
        raise ValueError("Allowances must be finite, 0..2 mm")
    if after_clearance <= before_clearance:
        raise ValueError("This contract permits only an enlarged bore")
    checks = {}
    identity = set(before_parts) == set(after_parts) and "body" in before_parts
    identity = identity and all(p.label == key for key, p in before_parts.items())
    identity = identity and all(p.label == key for key, p in after_parts.items())
    _record(checks, "change_part_identity", identity,
            {"before": {k: p.label for k, p in before_parts.items()},
             "after": {k: p.label for k, p in after_parts.items()}},
            "Same part keys and labels; no missing, renamed or added parts")
    if not identity:
        return checks
    baseline = before_parts["body"]
    baseline_valid = baseline.is_valid and len(baseline.solids()) == 1 and _has_cylinder(
        _cylinders(baseline), (77 + before_clearance) / 2, 0, 0, 0, 22)
    _record(checks, "change_baseline_bore", baseline_valid,
            {"valid_one_solid": baseline.is_valid and len(baseline.solids()) == 1},
            {"diameter_mm": 77 + before_clearance, "z_mm": [0, 22]})
    for key, old in before_parts.items():
        candidate = after_parts[key]
        target = old - _cylinder((77 + after_clearance) / 2, 0, 22) if key == "body" else old
        unexpected = _volume(target - candidate) + _volume(candidate - target)
        removed, added = _volume(old - candidate), _volume(candidate - old)
        ok = baseline_valid and candidate.is_valid and len(candidate.solids()) == 1 and unexpected < VOLUME_TOL
        _record(checks, f"change_{key}", ok,
                {"removed_mm3": removed, "added_mm3": added, "unexpected_mm3": unexpected},
                {"allowed": "Coaxial enlarged bore z0..22 only" if key == "body" else "Completely protected",
                 "absolute_volume_tolerance_mm3": VOLUME_TOL})
    return checks
