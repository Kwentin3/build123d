"""Independent native-geometry checks for the centred, straight involute gear."""

import math

from build123d import GeomType
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
from OCP.BRepCheck import BRepCheck_Analyzer

LENGTH_TOL_MM = 1e-6
FLANK_TOL_MM = 1e-4
ANGLE_TOL_RAD = 1e-6
CHECK_NAMES = (
    "occ_valid", "solid_count", "self_intersections", "thickness",
    "outer_diameter", "root_diameter", "tooth_count", "angular_regularity",
    "involute_flanks", "bore_diameter", "bore_position", "through_hole",
    "straight_teeth", "pitch_circle", "base_circle",
)


def check_gear(gear, expected):
    """Measure the final BREP, without using the generator's points or tooth list.

    Involute residuals are sampled geometric evidence, not an exact symbolic
    proof for an interpolated B-spline. Pitch/base circles are reference geometry.
    """
    actual, checks = {}, {}

    def record(name, passed, observed, target, tolerance=None, reason=None):
        checks[name] = {
            "status": "NOT_CHECKED" if passed is None else "PASS" if passed else "FAIL",
            "actual": observed, "expected": target, "tolerance": tolerance,
        }
        if reason:
            checks[name]["reason"] = reason

    def close(a, b):
        return abs(a - b) <= LENGTH_TOL_MM

    def angle_delta(a, b):
        return (a - b + math.pi) % (2 * math.pi) - math.pi

    solids = gear.solids()
    valid = bool(BRepCheck_Analyzer(gear.wrapped).IsValid())
    record("occ_valid", valid, valid, True)
    record("solid_count", len(solids) == 1, len(solids), 1)
    size = gear.bounding_box().size
    actual.update(solid_count=len(solids), volume_mm3=gear.volume,
                  dimensions_mm=[size.X, size.Y, size.Z])
    caps = [f for f in gear.faces().filter_by(GeomType.PLANE)
            if abs(abs(f.normal_at().Z) - 1) <= LENGTH_TOL_MM]
    caps.sort(key=lambda f: f.center().Z)
    height = expected["thickness"]
    cap_z = [f.center().Z for f in caps]
    thickness = cap_z[-1] - cap_z[0] if len(caps) >= 2 else None
    record("thickness", len(caps) == 2 and close(cap_z[0], -height / 2)
           and close(cap_z[-1], height / 2), cap_z, [-height / 2, height / 2],
           {"absolute_mm": LENGTH_TOL_MM})
    actual["thickness_mm"] = thickness
    top = caps[-1].outer_wire() if caps else None
    edges = list(top.edges()) if top is not None else []
    circles = [e for e in edges if e.geom_type == GeomType.CIRCLE]
    radii = [e.radius for e in circles]
    ra, rf = (max(radii), min(radii)) if radii else (None, None)
    tips = [e for e in circles if close(e.radius, ra)] if radii else []
    concentric = all(math.hypot(e.arc_center.X, e.arc_center.Y) <= LENGTH_TOL_MM
                     for e in circles)
    for name, radius in (("outer_diameter", ra), ("root_diameter", rf)):
        value = 2 * radius if radius is not None else None
        actual[name + "_mm"] = value
        record(name, value is not None and concentric and close(value, expected[name]),
               value, expected[name], {"absolute_mm": LENGTH_TOL_MM})
    centres = sorted(math.atan2(e.position_at(0.5).Y, e.position_at(0.5).X)
                     % (2 * math.pi) for e in tips)
    count = len(centres)
    actual["tooth_count"] = count
    record("tooth_count", count == expected["teeth"], count, expected["teeth"])
    gaps = [(centres[(i + 1) % count] - centres[i]) % (2 * math.pi)
            for i in range(count)] if count > 1 else []
    gap_error = max((abs(g - 2 * math.pi / count) for g in gaps), default=None)
    actual["observed_pitch_angles_deg"] = [math.degrees(g) for g in gaps]
    record("angular_regularity", gap_error is not None and gap_error <= ANGLE_TOL_RAD,
           {"tip_centres_rad": centres, "max_pitch_error_rad": gap_error},
           {"uniform_pitch_rad": 2 * math.pi / count if count else None},
           {"absolute_rad": ANGLE_TOL_RAD})

    flanks = [e for e in edges if e.geom_type == GeomType.BSPLINE]
    rb = expected["base_diameter"] / 2
    alpha = math.radians(expected["pressure_angle_deg"])
    residuals, radial_errors, flank_counts = [], [], [0] * count
    span_errors, flank_spans = [], []
    flank_sides = [[0, 0] for _ in range(count)]
    if count:
        for edge in flanks:
            midpoint = edge.position_at(0.5)
            centre_index = min(range(count), key=lambda i: abs(angle_delta(
                math.atan2(midpoint.Y, midpoint.X), centres[i])))
            flank_counts[centre_index] += 1
            signed_angle = angle_delta(math.atan2(midpoint.Y, midpoint.X), centres[centre_index])
            flank_sides[centre_index][0 if signed_angle < 0 else 1] += 1
            # A short correct involute joined to an incorrect connector must fail.
            endpoints = [edge.position_at(u) for u in (0, 1)]
            endpoint_radii = sorted(math.hypot(p.X, p.Y) for p in endpoints)
            flank_spans.append(endpoint_radii)
            if ra is not None:
                span_errors.append(max(abs(endpoint_radii[0] - rb), abs(endpoint_radii[1] - ra)))
            for j in range(33):
                p = edge.position_at(j / 32)
                radius = math.hypot(p.X, p.Y)
                radial_errors.append(max(0, rb - radius))
                ratio = max(1, radius / rb)
                involute = math.sqrt(ratio * ratio - 1) - math.acos(1 / ratio)
                target = math.pi / (2 * count) + math.tan(alpha) - alpha - involute
                observed = abs(angle_delta(math.atan2(p.Y, p.X), centres[centre_index]))
                residuals.append(abs(observed - target) * radius)
    max_residual = max(residuals, default=None)
    max_radial_error = max(radial_errors, default=None)
    max_span_error = max(span_errors, default=None)
    flank_actual = {"flank_count": len(flanks), "flanks_per_tooth": flank_counts,
                    "left_right_flanks_per_tooth": flank_sides,
                    "endpoint_radial_spans_mm": flank_spans,
                    "max_endpoint_radial_span_error_mm": max_span_error,
                    "samples_per_flank": 33, "max_tangential_residual_mm": max_residual,
                    "max_below_base_mm": max_radial_error}
    actual["involute_flanks"] = flank_actual
    record("involute_flanks", bool(count) and len(flanks) == 2 * count
           and all(n == 2 for n in flank_counts) and max_residual is not None
           and all(sides == [1, 1] for sides in flank_sides)
           and max_span_error is not None and max_span_error <= FLANK_TOL_MM
           and max_residual <= FLANK_TOL_MM and max_radial_error <= FLANK_TOL_MM,
           flank_actual, {"flanks_per_tooth": 2, "pressure_angle_deg": expected["pressure_angle_deg"],
                          "reference_base_diameter_mm": expected["base_diameter"],
                          "each_flank_radial_span_mm": [rb, ra]},
           {"sampled_position_mm": FLANK_TOL_MM})

    diameter = expected["bore_diameter"]
    cylinders = list(gear.faces().filter_by(GeomType.CYLINDER))
    bores = [f for f in cylinders if close(2 * f.radius, diameter)]
    rims = [e for e in gear.edges().filter_by(GeomType.CIRCLE)
            if close(2 * e.radius, diameter)]
    bore_diameters = [2 * f.radius for f in bores]
    record("bore_diameter", len(bores) == 1, bore_diameters, [diameter],
           {"absolute_mm": LENGTH_TOL_MM})
    rim_centres = [list(e.arc_center) for e in rims]
    centred = len(rims) == 2 and all(math.hypot(c[0], c[1]) <= LENGTH_TOL_MM for c in rim_centres)
    record("bore_position", centred, rim_centres,
           [[0, 0, -height / 2], [0, 0, height / 2]], {"absolute_mm": LENGTH_TOL_MM})
    rim_z = sorted(c[2] for c in rim_centres)
    axis_empty = len(solids) == 1 and all(not solids[0].is_inside((0, 0, z))
        for z in (-height * 0.49, 0, height * 0.49))
    spans = len(bores) == 1 and close(bores[0].bounding_box().size.Z, height)
    open_rims = len(rim_z) == 2 and close(rim_z[0], -height / 2) and close(rim_z[1], height / 2)
    record("through_hole", centred and spans and open_rims and axis_empty,
           {"rim_z_mm": rim_z, "bore_spans_thickness": spans, "axis_empty": axis_empty},
           {"rim_z_mm": [-height / 2, height / 2], "bore_spans_thickness": True, "axis_empty": True},
           {"absolute_mm": LENGTH_TOL_MM})
    actual.update(bore_diameters_mm=bore_diameters, bore_rim_centres_mm=rim_centres)

    intersection_results = {}
    try:
        for name, shape in (("solid", gear), ("profile", top)):
            if shape is None:
                raise ValueError("No planar top profile")
            probe = BRepAlgoAPI_Check(shape.wrapped, False, True)
            probe.Perform()
            intersection_results[name] = {"valid": bool(probe.IsValid()),
                "faults": [str(r.GetCheckStatus()) for r in probe.Result()]}
        record("self_intersections", all(v["valid"] for v in intersection_results.values()),
               intersection_results, {"solid": "no self interference", "profile": "no self interference"})
    except Exception as exc:
        record("self_intersections", None, intersection_results, "native check completed", reason=str(exc))

    # Matching native cap contours alone does not exclude a twisted middle.
    # Require every side surface to have a horizontal normal at sampled points too.
    contour_error = None
    if len(caps) == 2:
        def contour(face):
            return sorted((p.X, p.Y) for e in face.outer_wire().edges()
                          for p in e.positions([0, 0.25, 0.5, 0.75, 1]))
        bottom_points, top_points = contour(caps[0]), contour(caps[-1])
        if len(bottom_points) == len(top_points):
            contour_error = max((math.hypot(a[0] - b[0], a[1] - b[1])
                for a, b in zip(bottom_points, top_points)), default=0)
    sides = [f for f in gear.faces() if not any(f.is_same(cap) for cap in caps)]
    max_normal_z = max((abs(f.normal_at(u, v).Z) for f in sides
                        for u, v in ((0.25, 0.25), (0.5, 0.5), (0.75, 0.75))), default=None)
    record("straight_teeth", contour_error is not None and contour_error <= LENGTH_TOL_MM
           and max_normal_z is not None and max_normal_z <= LENGTH_TOL_MM,
           {"cap_contour_max_error_mm": contour_error, "sampled_side_normal_max_abs_z": max_normal_z},
           {"cap_contour_max_error_mm": 0, "sampled_side_normal_max_abs_z": 0},
           {"absolute_mm": LENGTH_TOL_MM, "normal_component": LENGTH_TOL_MM})
    for name in ("pitch_circle", "base_circle"):
        key = "pitch_diameter" if name == "pitch_circle" else "base_diameter"
        reason = "Reference circle is not a physical BREP edge or face; no direct diameter measurement."
        if name == "base_circle":
            reason += " The supplied base diameter is checked indirectly through sampled flank geometry."
        record(name, None, None, expected[key], reason=reason)
    return actual, checks
