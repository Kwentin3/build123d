"""Independent BREP measurements and continuous translation collision checks.

Translation sweeps comprise the initial solid and the exact extrusion of each
boundary face. Their union is the swept volume: a moving boundary must cross any
newly occupied point. No discretisation of the assembly path is used.
"""

from itertools import combinations

from build123d import GeomType, Keep, Plane, Solid, Vector
from OCP.BRepCheck import BRepCheck_Analyzer

LENGTH_TOL = 1e-6
VOLUME_TOL = 1e-5


def _volume(shape):
    if shape is None:
        return 0.0
    if isinstance(shape, (list, tuple)):
        return sum(_volume(item) for item in shape)
    return sum(s.volume for s in shape.solids())


def _overlap_bounds(a, b):
    aa, bb = a.bounding_box(), b.bounding_box()
    return all(min(tuple(aa.max)[i], tuple(bb.max)[i]) - max(tuple(aa.min)[i], tuple(bb.min)[i]) > LENGTH_TOL
               for i in range(3))


def intersection_volume(a, b):
    """Zero for disjoint bounding boxes; otherwise measure native common solids."""
    return _volume(a.intersect(b)) if _overlap_bounds(a, b) else 0.0


def translation_sweep(shape, delta):
    """Exact sweep pieces for planar/cylindrical sheet-part boundaries."""
    direction = Vector(delta)
    if direction.length <= LENGTH_TOL:
        raise ValueError("Assembly motion must have nonzero displacement")
    yield shape
    for face in shape.faces():
        if face.geom_type == GeomType.PLANE:
            if abs(face.normal_at().dot(direction)) <= LENGTH_TOL:
                continue
            yield Solid.extrude(face, direction)
        elif face.geom_type == GeomType.CYLINDER:
            axis = face.axis_of_rotation
            radial = direction - axis.direction * direction.dot(axis.direction)
            if radial.length <= LENGTH_TOL:
                continue
            # A full cylindrical-face prism folds over itself. Splitting at
            # radial tangencies makes each half monotone along the movement.
            halves = face.split(Plane(origin=axis.position, z_dir=radial), Keep.BOTH)
            for half in halves:
                pieces = half if isinstance(half, (list, tuple)) else [half]
                for patch in (f for piece in pieces if piece is not None for f in piece.faces()):
                    swept = Solid.extrude(patch, direction)
                    if not swept.is_valid:
                        raise ValueError("Invalid cylindrical sweep prism")
                    yield swept
        else:
            raise ValueError(f"Unsupported swept surface: {face.geom_type}")


def motion_collision(parts, moving, fixed, delta):
    """Return collision witnesses over the complete continuous translation."""
    witnesses = []
    for label in moving:
        for piece in translation_sweep(parts[label], delta):
            for other in fixed:
                volume = intersection_volume(piece, parts[other])
                if volume > VOLUME_TOL:
                    witnesses.append({"moving": label, "fixed": other,
                                      "swept_common_mm3": volume})
    return witnesses


def validate_geometry(model, p):
    """Measure generated profiles/parts independently of their construction code."""
    checks = {}

    def record(name, passed, actual, expected=None, reason=None):
        checks[name] = {"status": "NOT_CHECKED" if passed is None else
                        "PASS" if passed else "FAIL", "actual": actual}
        if expected is not None:
            checks[name]["expected"] = expected
        if reason:
            checks[name]["reason"] = reason

    parts_list = model["parts"]
    parts = {part.label: part for part in parts_list}
    required = {"side_1", "side_2", "end_1", "end_2", "bottom",
                "key_1", "key_2", "key_3", "key_4"}
    record("part_inventory", len(parts_list) == 9 and set(parts) == required,
           sorted(part.label for part in parts_list), sorted(required))
    solids = {name: {"valid": bool(BRepCheck_Analyzer(part.wrapped).IsValid()),
                     "solid_count": len(part.solids()), "volume_mm3": _volume(part)}
              for name, part in parts.items()}
    record("valid_single_solids", all(v["valid"] and v["solid_count"] == 1
           and v["volume_mm3"] > VOLUME_TOL for v in solids.values()), solids)
    profiles = {}
    for name, profile in model["profiles"].items():
        faces = list(profile.faces())
        profiles[name] = {"valid": bool(BRepCheck_Analyzer(profile.wrapped).IsValid()),
            "face_count": len(faces), "area_mm2": profile.area,
            "all_wires_closed": bool(faces) and all(w.is_closed for f in faces for w in f.wires()),
            "z_span_mm": profile.bounding_box().size.Z,
            "z_offset_mm": profile.bounding_box().min.Z}
    record("flat_closed_profiles", set(profiles) == {"side", "end", "bottom", "key"}
           and all(v["valid"] and v["face_count"] == 1 and v["all_wires_closed"]
                   and v["area_mm2"] > 0 and v["z_span_mm"] <= LENGTH_TOL
                   and abs(v["z_offset_mm"]) <= LENGTH_TOL
                   for v in profiles.values()), profiles)
    if not required.issubset(parts):
        record("dimensions", None, None, reason="Missing required part labels")
        return checks
    bounds = {name: part.bounding_box() for name, part in parts.items()}
    axes = {name: 1 if name.startswith("side") else 2 if name == "bottom" else 0
            for name in parts}
    thicknesses = {name: tuple(bounds[name].size)[axis] for name, axis in axes.items()}
    record("sheet_thickness", all(abs(t - p.thickness) <= LENGTH_TOL
           for t in thicknesses.values()), thicknesses, p.thickness)
    measured = {"inside_length_mm": bounds["end_2"].min.X - bounds["end_1"].max.X,
                "inside_width_mm": bounds["side_2"].min.Y - bounds["side_1"].max.Y,
                "wall_height_mm": bounds["side_1"].size.Z,
                "leg_height_mm": bounds["side_1"].min.Z - bounds["end_1"].min.Z,
                "bottom_elevation_mm": bounds["bottom"].min.Z}
    expected = {"inside_length_mm": p.length, "inside_width_mm": p.width,
                "wall_height_mm": p.height, "leg_height_mm": p.leg_height,
                "bottom_elevation_mm": p.bottom_z}
    record("dimensions", all(abs(measured[k] - target) <= LENGTH_TOL
           for k, target in expected.items()), measured, expected)
    collisions = []
    for (name_a, a), (name_b, b) in combinations(parts.items(), 2):
        common = intersection_volume(a, b)
        if common > VOLUME_TOL:
            collisions.append({"parts": [name_a, name_b], "common_mm3": common})
    record("assembled_no_interference", not collisions, collisions, [])
    # Small downward sweeps bound vertical free play to less than 0.1 mm,
    # rather than merely assuming that a tongue near a slot supports the part.
    for label in ("bottom", "side_1", "side_2", "key_1", "key_2", "key_3", "key_4"):
        fixed = [other for other in parts if other != label]
        hits = motion_collision(parts, [label], fixed, (0, 0, -.1))
        record("seated_" + label, bool(hits), hits,
               "downward motion blocked within 0.1 mm")
    hits = motion_collision(parts, ["end_2"], [name for name in parts if name != "end_2"],
                            (p.tab_reach + 10, 0, 0))
    record("keys_restrain_end", bool(hits), hits,
           "outward end motion blocked with retaining keys inserted")
    inverted = parts["side_1"].mirror(Plane(
        origin=(0, 0, p.leg_height + p.height / 2), z_dir=(0, 0, 1)))
    wrong_orientation_common = intersection_volume(inverted, parts["end_1"])
    record("inverted_side_cannot_seat", wrong_orientation_common > VOLUME_TOL,
           {"common_mm3": wrong_orientation_common}, "positive interference")
    # Probe both sides of the specified travel boundary on native geometry.
    # This measures a 0.02-mm bracket instead of reading slot construction data.
    probes = [("side_lateral_minus", "side_1", ["end_1", "end_2"], (0,-1,0), p.clearance/2),
              ("side_lateral_plus", "side_1", ["end_1", "end_2"], (0,1,0), p.clearance/2),
              ("side_vertical", "side_1", ["end_1", "end_2"], (0,0,1), p.clearance),
              ("bottom_lateral_minus", "bottom", ["end_1", "end_2"], (0,-1,0), 2),
              ("bottom_lateral_plus", "bottom", ["end_1", "end_2"], (0,1,0), 2),
              ("bottom_axial_minus", "bottom", ["end_1", "end_2"], (-1,0,0), p.bottom_gap),
              ("bottom_axial_plus", "bottom", ["end_1", "end_2"], (1,0,0), p.bottom_gap),
              ("key_axial_minus", "key_1", ["side_1"], (-1,0,0), p.clearance/2),
              ("key_axial_plus", "key_1", ["side_1"], (1,0,0), p.clearance/2)]
    for name, label, fixed, axis, limit in probes:
        distances = [limit - .01, limit + .01]
        common = [sum(intersection_volume(parts[label].translate(Vector(axis)*distance),
                                         parts[other]) for other in fixed)
                  for distance in distances]
        record("clearance_" + name, common[0] <= VOLUME_TOL and common[1] > VOLUME_TOL,
               {"travel_bracket_mm": distances, "probe_common_mm3": common,
                "axis": list(axis)}, {"nominal_travel_mm": limit,
                                       "bracket_half_width_mm": .01})
    motions = model.get("motions", [])
    record("assembly_motions_present", bool(motions), len(motions), "nonempty")
    for motion in motions:
        name = "motion_" + motion["name"]
        try:
            moving, fixed = motion["moving"], motion["fixed"]
            if not moving or set(moving) & set(fixed):
                raise ValueError("Motion needs moving parts and disjoint fixed labels")
            hits = motion_collision(parts, moving, fixed, motion["delta"])
            must_collide = motion.get("expected_collision", False)
            record(name, bool(hits) == must_collide,
                   {"delta_mm": list(motion["delta"]), "continuous": True,
                    "collision_witnesses": hits},
                   {"collision": must_collide})
        except Exception as exc:
            record(name, None, None, reason=f"Continuous sweep failed: {exc}")
    return checks
