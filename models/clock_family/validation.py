"""Independent CAD acceptance for REFACTOR.md; mm, +Z rear, gravity -Y.

Requirements below are not imported from the generator or joint implementation.
Thread-forming screw/pilot contact is intentional. Geometry does not establish
PETG torque, strength, fit, thread life or actual OEM service access.
"""

from math import acos, asin, isclose, isfinite, pi, sqrt

from build123d import (Box, CenterOf, Cone, Cylinder, GeomType, Pos,
                      RectangleRounded, extrude)
from OCP.BRepAdaptor import BRepAdaptor_Surface

LENGTH_TOL = 1e-5
VOLUME_TOL = 1e-3
CENTRES = ((-33.5, -33.5), (-33.5, 33.5), (33.5, -33.5), (33.5, 33.5))


def _cylinder(radius, z0, z1, x=0, y=0):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(radius, z1 - z0)


def _volume(shape):
    return 0.0 if shape is None else sum(s.volume for s in shape.solids())


def _close(a, b):
    return isclose(a, b, abs_tol=LENGTH_TOL, rel_tol=0)


def _record(checks, name, passed, actual, expected):
    checks[name] = dict(status="PASS" if passed else "FAIL", actual=actual, expected=expected)


def _clear(checks, name, body, probe, expected):
    collision = _volume(body.intersect(probe))
    _record(checks, name, collision < VOLUME_TOL, {"collision_mm3": collision}, expected)


def _cylinders(shape):
    result = []
    for face in shape.faces().filter_by(GeomType.CYLINDER):
        axis, box = face.axis_of_rotation, face.bounding_box()
        result.append(dict(radius=BRepAdaptor_Surface(face.wrapped).Cylinder().Radius(),
                           x=axis.position.X, y=axis.position.Y,
                           axial=abs(abs(axis.direction.Z) - 1) < LENGTH_TOL,
                           z0=box.min.Z, z1=box.max.Z))
    return result


def _at(f, radius, x, y):
    return f["axial"] and all(_close(f[k], v) for k, v in
                             (("radius", radius), ("x", x), ("y", y)))


def _has_cylinder(faces, radius, x, y, z0, z1):
    return any(_at(f, radius, x, y) and _close(f["z0"], z0) and _close(f["z1"], z1)
               for f in faces)


def _stock(name, z0, z1):
    if name == "portable":
        return Pos(0, 0, z0) * extrude(RectangleRounded(110, 116, 10), amount=z1-z0)
    return _cylinder(70 if name == "wall" else 54, z0, z1)


def _lid_prism(name, z0, z1):
    lid = _stock(name, z0, z1)
    if name == "desk":
        lid -= Pos(0, -101.8, (z0+z1)/2) * Box(200, 100, z1-z0+2)
    elif name == "portable":
        lid -= Pos(0, 99.75, (z0+z1)/2) * Box(17, 100, z1-z0+2)
    return lid


def _ring(inner, outer, z0, z1, x=0, y=0):
    return _cylinder(outer, z0, z1, x, y) - _cylinder(inner, z0, z1, x, y)


def _lid_volume_check(checks, name, lid):
    """Analytic stock/cut volume catches unrelated holes and changed profiles."""
    if name == "desk":
        area = pi*54**2-(54**2*acos(51.8/54)-51.8*sqrt(54**2-51.8**2))
    elif name == "portable":
        area = 110*116-(4-pi)*10**2-17*(58-49.75)
    else:
        # EntryR5 plus neck4.6 toY16 and its semicircular end; subtract overlap.
        overlap = 2.3*sqrt(5**2-2.3**2)+5**2*asin(2.3/5)
        key_area = pi*5**2+4.6*8+pi*2.3**2/2-overlap
        area = pi*70**2-2*key_area
    frustum_extra = pi*.5*(1.75**2+1.75*2.1+2.1**2)/3-pi*1.75**2*.5
    joint_cut = pi*1.75**2*5+pi*(4**2-1.75**2)*2.6+frustum_extra
    expected = area*5-4*joint_cut
    actual = _volume(lid)
    _record(checks, "lid_volume", abs(actual-expected) < VOLUME_TOL, actual,
            {"volume_mm3": expected, "absolute_tolerance_mm3": VOLUME_TOL,
             "method": "Analytic outline area, four stepped/conical passages, wall slots or portable notch"})


def _rear_joint_checks(checks, body, lid, rear, body_faces, lid_faces):
    seat = rear + 2.4
    missing_boss, missing_support, missing_mating, missing_head_seat = [], [], [], []
    pilot_void, front_web, lid_void, pocket_void, chamfer_void, tools = [], [], [], [], [], []
    pilot_floors, pilots, passages, pockets = [], [], [], []
    for x, y in CENTRES:
        pilot = _cylinder(1.2, rear-12, rear, x, y)
        boss = _cylinder(5, rear-14, rear, x, y) - pilot
        missing_boss.append(_volume(boss - body))
        missing_support.append(_volume(_cylinder(5, rear-14.5, rear-14, x, y) - body))
        missing_mating.append(_volume(_ring(1.75, 5, rear, rear+.05, x, y) - lid))
        missing_head_seat.append(_volume(_ring(2.1, 2.5, seat-.05, seat, x, y) - lid))
        pilot_void.append(_volume(body.intersect(pilot)))
        front_web.append(_volume(_cylinder(1.2, 0, rear-12, x, y)-body))
        lid_void.append(_volume(lid.intersect(_cylinder(1.75, rear, rear+5, x, y))))
        pocket_void.append(_volume(lid.intersect(_cylinder(4, seat, rear+5, x, y))))
        chamfer = Pos(x, y, seat-.25) * Cone(1.75, 2.1, .5)
        chamfer_void.append(_volume(lid.intersect(chamfer)))
        tool = _cylinder(3.8, seat+2.42, rear+50, x, y)
        tools.append(_volume(body.intersect(tool)) + _volume(lid.intersect(tool)))
        pilots.append(_has_cylinder(body_faces, 1.2, x, y, rear-12, rear))
        passages.append(_has_cylinder(lid_faces, 1.75, x, y, rear, seat-.5))
        pockets.append(_has_cylinder(lid_faces, 4, x, y, seat, rear+5))
        measured = [f["z0"] for f in body_faces if _at(f, 1.2, x, y)]
        pilot_floors.append(min(measured) if measured else rear)
    _record(checks, "rear_boss_support", max(missing_boss + missing_support) < VOLUME_TOL,
            {"missing_boss_mm3": missing_boss, "missing_foundation_mm3": missing_support},
            "Four diameter10 bosses rear-14..rear, complete0.5mm foundation into front wall; geometric load path only")
    _record(checks, "blind_pilots", all(pilots) and max(pilot_void+front_web) < VOLUME_TOL,
            {"cylinders": pilots, "collision_mm3": pilot_void, "measured_floor_z_mm": pilot_floors,
             "missing_axial_front_web_mm3": front_web},
            {"diameter_mm": 2.4, "depth_mm": 12, "front_web_mm": rear-12})
    # Tip is rear-penetration; reserve is tip minus the measured blind floor.
    reserves = [(rear-10.15) - floor for floor in pilot_floors]
    _record(checks, "rear_screw_budget", min(reserves) >= 1.85-LENGTH_TOL,
            {"penetration_mm": [9.05, 10.15], "bottom_reserve_mm": reserves,
             "measured_front_web_mm": pilot_floors},
            {"screw_length_mm": [11.45, 12.55], "head_seat_z_mm": seat,
             "minimum_bottom_reserve_mm": 1.85,
             "scope": "Diameter3.1 thread envelope intentionally overlaps diameter2.4 pilot; physical thread fit unverified"})
    _record(checks, "rear_cover_passages", all(passages) and all(pockets)
            and max(lid_void+pocket_void+chamfer_void) < VOLUME_TOL,
            {"passage_cylinders": passages, "pocket_cylinders": pockets,
             "passage_collision_mm3": lid_void, "pocket_collision_mm3": pocket_void,
             "under_head_cone_collision_mm3": chamfer_void},
            {"through_diameter_mm": 3.5, "pocket_diameter_depth_mm": [8, 2.6],
             "under_head_cone_top_diameter_depth_mm": [4.2, .5]})
    _record(checks, "rear_bearing_patches", max(missing_mating+missing_head_seat) < VOLUME_TOL,
            {"missing_lid_body_mating_mm3": missing_mating, "missing_head_seat_mm3": missing_head_seat},
            {"body_lid_annulus_r_mm": [1.75, 5], "head_bearing_annulus_r_mm": [2.1, 2.5],
             "scope": "Flat material patches for screw clamping; no strength or preload claim"})
    _record(checks, "rear_driver_access", max(tools) < VOLUME_TOL,
            {"collision_mm3": tools},
            {"axial_driver_diameter_mm": 7.6, "z_mm": [seat+2.42, rear+50],
             "drive": "10IP; T10 not substituted", "state": "Wall variant demounted"})
    return pilot_floors


def _hardware_checks(checks, model, rear, floors):
    hardware = model.get("hardware")
    if hardware is None:
        return  # STEP acceptance still runs independent complete budgets above.
    required = {f"cover_screw_{i}" for i in range(1, 5)}
    if model["name"] == "wall":
        required |= {"wall_screw_1", "wall_screw_2"}
    _record(checks, "hardware_identity", set(hardware) == required and
            all(s.label == k for k, s in hardware.items()),
            {k: s.label for k, s in hardware.items()}, sorted(required))
    for i, ((x, y), floor) in enumerate(zip(CENTRES, floors), 1):
        key, seat = f"cover_screw_{i}", rear+2.4
        if key not in hardware:
            continue
        screw = hardware[key]
        faces = _cylinders(screw)
        stems = [f for f in faces if _at(f, 1.5, x, y) and _close(f["z1"], seat)]
        heads = [f for f in faces if f["axial"] and _close(f["x"], x) and _close(f["y"], y)
                 and 2.5-LENGTH_TOL <= f["radius"] <= 2.65+LENGTH_TOL and _close(f["z0"], seat)
                 and 2.18-LENGTH_TOL <= f["z1"]-f["z0"] <= 2.42+LENGTH_TOL]
        lengths = [f["z1"]-f["z0"] for f in stems]
        reserves = [f["z0"]-floor for f in stems]
        collision = _volume(model["parts"]["lid"].intersect(screw))
        ok = (screw.is_valid and len(screw.solids()) == 1 and bool(stems) and bool(heads)
              and all(11.45-LENGTH_TOL <= v <= 12.55+LENGTH_TOL for v in lengths)
              and min(reserves, default=-1) >= 1.85-LENGTH_TOL and collision < VOLUME_TOL)
        _record(checks, key, ok, {"stem_lengths_mm": lengths, "bottom_reserves_mm": reserves,
                "lid_collision_mm3": collision, "cylinders": faces},
                "Nominal diameter3 stem at specified rear seat, published length/head limits and blind-bottom reserve; thread contact intentional")
    if model["name"] == "wall":
        for i, x in enumerate((-50, 50), 1):
            key = f"wall_screw_{i}"
            if key not in hardware:
                continue
            screw = hardware[key]
            faces = _cylinders(screw)
            collision = sum(_volume(p.intersect(screw)) for p in model["parts"].values())
            ok = (screw.is_valid and len(screw.solids()) == 1
                  and _has_cylinder(faces, 2, x, 16.3, 30, 55)
                  and _has_cylinder(faces, 3.95, x, 16.3, 27.2, 30)
                  and collision < VOLUME_TOL)
            _record(checks, key, ok, {"collision_mm3": collision, "cylinders": faces},
                    "Wurth0153740025 nominal diameter4x25, head7.9x2.8, hung atY16.3; wall/wood strength unverified")


def _wall_checks(checks, body, lid):
    entry, shaft_path, head_path, support, bearing_area = [], [], [], [], []
    for x in (-50, 50):
        entry.append(_volume(lid.intersect(_cylinder(5, 30, 35, x, 8))))
        # Continuous capsule swept by maximum4.2mm shaft, Y8..16.2.
        shaft = _cylinder(2.1, 30, 35.5, x, 8) + _cylinder(2.1, 30, 35.5, x, 16.2)
        shaft += Pos(x, 12.1, 32.75) * Box(4.2, 8.2, 5.5)
        shaft_path.append(sum(_volume(p.intersect(shaft)) for p in (body, lid)))
        head = _cylinder(4.25, 26.5, 40, x, 8)
        head_path.append(sum(_volume(p.intersect(head)) for p in (body, lid)))
        for offset in (-3, 3):
            patch = Pos(x+offset, 16.3, 30.025) * Box(1, 1, .05)
            support.append(_volume(patch-lid))
        bearing_area.append(_volume(lid.intersect(_cylinder(3.95, 30, 30.05, x, 16.3)))/.05)
    _record(checks, "wall_keyhole_entry", max(entry) < VOLUME_TOL,
            {"collision_mm3": entry}, {"centres_mm": [[-50, 8], [50, 8]], "diameter_mm": 10})
    _record(checks, "wall_hang_remove_path", max(shaft_path+head_path) < VOLUME_TOL,
            {"shaft_path_collision_mm3": shaft_path, "head_entry_collision_mm3": head_path},
            {"continuous_head_admission_diameter_mm": 8.5, "head_height_budget_mm": 3.5,
             "continuous_shaft_diameter_mm": 4.2, "shaft_relative_y_mm": [8, 16.2],
             "sequence": "Head enters large opening axially; lower clock to neck; reverse to demount before opening cover"})
    _record(checks, "wall_head_retention", max(support) < VOLUME_TOL and min(bearing_area) > 2,
            {"missing_side_bearing_patches_mm3": support, "nominal_head_bearing_area_mm2": bearing_area},
            "Nominal head7.9 atY16.3 bears on both sides of neck4.6; geometric retention only")
    gap = 35.5-lid.bounding_box().max.Z
    _record(checks, "wall_fixture_budget", gap >= .5-LENGTH_TOL,
            {"body_to_test_board_gap_mm": gap, "board_z_mm": [35.5, 65.5],
             "nominal_wood_penetration_mm": 19.5, "budget_wood_penetration_mm": 20.5,
             "remaining_board_mm": 9.5},
            "Control wooden board30mm; screw nominalL25/budget26, shaft datumZ30; actual wall and anchors NOT_CHECKED")


def validate_variant(model, expected_clearance):
    """Measure rear-fastener contract; retain FAIL and NOT_CHECKED results."""
    if not isfinite(expected_clearance) or not 0 <= expected_clearance <= 2:
        raise ValueError("Expected diametral allowance must be finite,0..2mm")
    name, parts = model["name"], model["parts"]
    if name not in ("desk", "wall", "portable"):
        raise ValueError(f"Unknown clock variant:{name}")
    checks = {}
    _record(checks, "part_identity", set(parts) == {"body", "lid"} and
            all(p.label == k for k, p in parts.items()), {k: p.label for k, p in parts.items()}, ["body", "lid"])
    for key, shape in parts.items():
        _record(checks, f"{key}_occ_valid", shape.is_valid, shape.is_valid, True)
        _record(checks, f"{key}_solid_count", len(shape.solids()) == 1, len(shape.solids()), 1)
    if not {"body", "lid"}.issubset(parts):
        return checks
    body, lid = parts["body"], parts["lid"]
    rear, relief = (30, 59) if name == "wall" else (28, 49)
    radius = (77+expected_clearance)/2
    faces, lid_faces = _cylinders(body), _cylinders(lid)
    bore = _has_cylinder(faces, radius, 0, 0, 0, 22)
    coaxial = [f for f in faces if f["axial"] and _close(f["x"], 0) and _close(f["y"], 0)
               and _close(f["z0"], 0) and _close(f["z1"], 22)]
    _record(checks, "bore_diameter", bore, [2*f["radius"] for f in coaxial], 77+expected_clearance)
    _record(checks, "bore_axis_depth", bore, coaxial, {"axis_xy_mm": [0, 0], "z_mm": [0, 22]})
    _clear(checks, "bore_continuous_clearance", body, _cylinder(radius, 0, 22), "Entire nominal socket empty")
    _clear(checks, "oem_envelope", body, _cylinder(38.5, 0, 22), "Published diameter77x22 installation envelope")
    _clear(checks, "front_insertion", body, _cylinder(38.5, -45, 22)+_cylinder(45, -40, 0),
           "Continuous axial installation/bezel envelopes; front/rear split of actual OEM body unpublished")
    _clear(checks, "service_clearance", body, _cylinder(38.5, 22, 90),
           "Continuous rear envelope after four screws and lid removed; wall clock first demounted")
    missing_seat = _volume(_ring(radius, 45, 0, .05)-body)
    _record(checks, "bezel_seat", missing_seat < VOLUME_TOL,
            {"missing_probe_mm3": missing_seat, "nominal_annular_area_mm2": pi*(45**2-radius**2)},
            "Full front annular seat between bore and radius45")
    _record(checks, "rear_relief", _has_cylinder(faces, relief, 0, 0, 22, rear),
            [f for f in faces if _at(f, relief, 0, 0)], {"radius_mm": relief, "z_mm": [22, rear]})
    missing_front = _volume((_stock(name, 0, 1)-_cylinder(radius, 0, 1))-body)
    _record(checks, "front_closed", missing_front < VOLUME_TOL,
            {"missing_front_mm3": missing_front}, "No facade holes outside OEM bore in full front1mm stock")
    expected = {"desk": (-72, -64, -44, 72, 54, 64), "wall": (-70, -70, 0, 70, 70, 30),
                "portable": (-55, -58, 0, 55, 74, 33)}[name]
    bounds = [*body.bounding_box().min, *body.bounding_box().max]
    _record(checks, "body_bounds", all(_close(a, b) for a, b in zip(bounds, expected)), bounds, expected)
    lid_expected = {"desk": (-54, -51.8, 28, 54, 54, 33), "wall": (-70, -70, 30, 70, 70, 35),
                    "portable": (-55, -58, 28, 55, 58, 33)}[name]
    lb = [*lid.bounding_box().min, *lid.bounding_box().max]
    _record(checks, "lid_bounds", all(_close(a, b) for a, b in zip(lb, lid_expected)), lb, lid_expected)
    _lid_volume_check(checks, name, lid)
    floors = _rear_joint_checks(checks, body, lid, rear, faces, lid_faces)
    _hardware_checks(checks, model, rear, floors)
    collision = _volume(body.intersect(lid))
    contact = sum(f.area for f in body.touch(lid).faces())
    _record(checks, "lid_mating", collision < VOLUME_TOL and contact > 100,
            {"collision_mm3": collision, "contact_area_mm2": contact}, "Zero solid overlap and rear mating contact>100mm2")
    _clear(checks, "lid_removal", body, _lid_prism(name, rear, rear+65),
           {"method": "Continuous conservative prism of specified lid outline", "z_mm": [rear, rear+65],
            "state": "Four rear screws removed; wall variant demounted; body fixed"})
    if name == "desk":
        foot = body & (Pos(0, -63.95, 10)*Box(200, .1, 200))
        fb = foot.bounding_box() if foot is not None else None
        cm = body.center(CenterOf.MASS)
        supported = fb is not None and (fb.min.X < min(cm.X, -45) and fb.max.X > max(cm.X, 45)
                    and fb.min.Z < min(cm.Z, -36) and fb.max.Z > max(cm.Z, 36))
        _record(checks, "desk_support", supported and _close(_volume(foot), 144*108*.1),
                {"material_com_xz_mm": [cm.X, cm.Z], "foot_slab_mm3": _volume(foot)},
                "Full144x108 foot; body CoM and conservative module CoM X+/-45,Z+/-36 within support; gravity-Y only")
    elif name == "wall":
        _wall_checks(checks, body, lid)
    else:
        missing_lug = _volume(_ring(2.5, 10, 25, 33, 0, 64)-body)
        missing_brace = _volume((Pos(0, 55, 26.5)*Box(14, 10, 13))-body)
        _record(checks, "portable_rear_lug", _has_cylinder(faces, 2.5, 0, 64, 25, 33)
                and missing_lug < VOLUME_TOL and missing_brace < VOLUME_TOL,
                {"missing_lug_mm3": missing_lug, "missing_brace_mm3": missing_brace},
                {"lug_diameters_mm": [20, 5], "lug_z_mm": [25, 33], "centre_xy_mm": [0, 64],
                 "brace_xyz_mm": [[-7, 7], [50, 60], [20, 33]], "attachment": "Integral with body, not lid"})
        old_lug = _cylinder(10, 0, 8, y=64)-_stock("portable", 0, 8)
        _clear(checks, "portable_old_front_lug_absent", body, old_lug, "No old lug material outside nominal front outlineZ0..8")
        _clear(checks, "portable_lid_notch", lid, Pos(0, 74.75, 30.5)*Box(17, 50, 5),
               "Open rear-lid notch X+/-8.5,Y>=49.75 clears fixed lug/brace")
    for key, reason in {
        "oem_retention_fit": "Actual OEM mounting ring, retention, panel tolerance and rear cap geometry unpublished; measure real module",
        "physical_service": "Actual OEM cap, battery, controls, hand/tool comfort and real assembly require prototype; envelope path alone insufficient",
        "strength_and_manufacturing": "No PETG/FDM strength, pullout, torque, preload, drop, creep, heat, print tolerance or repeated screw-use test; run pilot coupon with real EJOT screw",
        "actual_wall_anchors": "Wooden30mm fixture is a geometry example; actual wall, anchors and load capacity unspecified and untested",
    }.items():
        checks[key] = dict(status="NOT_CHECKED", reason=reason)
    return checks


def _nominal_body(name):
    rear = 30 if name == "wall" else 28
    stock = _stock(name, 0, rear)
    if name == "desk":
        stock += Pos(0, -58, 10)*Box(144, 12, 108)
    return stock-_cylinder(38.7, 0, 22)-_cylinder(59 if name == "wall" else 49, 22, rear)


def check_refactor(before_parts, after_parts, name):
    """Compare body to frozen old STEP; specific allowed regions from REFACTOR.

    Caller verifies provenance/hash. No regenerated baseline or blanket healing.
    Old lids may be replaced/new lids added; validate_variant owns new lids.
    """
    if name not in ("desk", "wall", "portable"):
        raise ValueError(name)
    checks = {}
    identity = (set(before_parts) == ({"body", "lid"} if name == "portable" else {"body"})
                and set(after_parts) == {"body", "lid"}
                and all(p.label == k for k, p in before_parts.items())
                and all(p.label == k for k, p in after_parts.items()))
    _record(checks, "refactor_part_identity", identity, [sorted(before_parts), sorted(after_parts)],
            "Frozen original parts to body+new rear lid; lid replacement/addition explicitly permitted")
    if not identity:
        return checks
    rear = 30 if name == "wall" else 28
    adds = _cylinder(5, rear-14, rear, *CENTRES[0])
    removes = _cylinder(1.2, rear-12, rear, *CENTRES[0])
    for x, y in CENTRES[1:]:
        adds += _cylinder(5, rear-14, rear, x, y)
        removes += _cylinder(1.2, rear-12, rear, x, y)
    if name in ("wall", "portable"):
        stock = _nominal_body(name)
        old_centres = ((-60, 0), (60, 0)) if name == "wall" else (
            (-46, -48), (-46, 48), (46, -48), (46, 48))
        for x, y in old_centres:
            fill = _cylinder(2.25 if name == "wall" else 1.7, 0, rear, x, y) & stock
            if fill is not None:
                adds += fill
    if name == "portable":
        adds += _ring(2.5, 10, 25, 33, 0, 64)
        adds += Pos(0, 55, 26.5)*Box(14, 10, 13)
        removes += _cylinder(10, 0, 8, y=64)-_stock("portable", 0, 8)
    old, new = before_parts["body"], after_parts["body"]
    added, removed = new-old, old-new
    unexpected_add, unexpected_remove = _volume(added-adds), _volume(removed-removes)
    _record(checks, "refactor_body", unexpected_add < VOLUME_TOL and unexpected_remove < VOLUME_TOL,
            {"added_mm3": _volume(added), "removed_mm3": _volume(removed),
             "unexpected_added_mm3": unexpected_add, "unexpected_removed_mm3": unexpected_remove},
            {"allowed": "Four rear bosses/pilots; old hole filling masked by nominal stock; portable rear lug/brace and old lug removal outside base outline",
             "absolute_tolerance_mm3": VOLUME_TOL})
    return checks


def check_change(before_parts, after_parts, before_clearance=.4, after_clearance=1.0):
    """Only enlarge body boreZ0..22 against accepted STEP; every lid protected."""
    if not all(isfinite(v) and 0 <= v <= 2 for v in (before_clearance, after_clearance)):
        raise ValueError("Allowances must be finite,0..2mm")
    if after_clearance <= before_clearance:
        raise ValueError("Only an enlarged bore is permitted")
    checks = {}
    identity = set(before_parts) == set(after_parts) == {"body", "lid"}
    identity = identity and all(p.label == k for k, p in before_parts.items())
    identity = identity and all(p.label == k for k, p in after_parts.items())
    _record(checks, "change_part_identity", identity,
            [sorted(before_parts), sorted(after_parts)], "Same body/lid keys and labels")
    if not identity:
        return checks
    old_body = before_parts["body"]
    baseline_valid = old_body.is_valid and len(old_body.solids()) == 1 and _has_cylinder(
        _cylinders(old_body), (77+before_clearance)/2, 0, 0, 0, 22)
    _record(checks, "change_baseline_bore", baseline_valid, baseline_valid,
            {"diameter_mm": 77+before_clearance, "z_mm": [0, 22]})
    for key, old in before_parts.items():
        new = after_parts[key]
        target = old-_cylinder((77+after_clearance)/2, 0, 22) if key == "body" else old
        unexpected = _volume(target-new)+_volume(new-target)
        _record(checks, f"change_{key}", baseline_valid and new.is_valid
                and len(new.solids()) == 1 and unexpected < VOLUME_TOL,
                {"removed_mm3": _volume(old-new), "added_mm3": _volume(new-old), "unexpected_mm3": unexpected},
                {"allowed": "Enlarged coaxial boreZ0..22 only" if key == "body" else "Completely protected",
                 "absolute_tolerance_mm3": VOLUME_TOL})
    return checks
