"""V2.1: native BREP validation of five plates and keyless V release."""
from dataclasses import asdict
from itertools import combinations
from math import atan2, degrees, isfinite

from build123d import Box, Compound, GeomType, Pos, Vector
from OCP.BRepCheck import BRepCheck_Analyzer

from models.mangal.validation import (LENGTH_TOL, VOLUME_TOL, intersection_volume,
                                      motion_collision)


def check_guide_change(before_model, after_model, before_params, after_params):
    """Check only a guide-up redistribution against an accepted V2.1 baseline.

    Both models still need validate_geometry. This contract measures material
    changes; it does not establish baseline acceptance or physical safety.
    Invalid inputs and failed native operations raise rather than pass.
    """
    tolerance = .01  # mm3, as in this model's STEP round-trip check
    before_params.validate()
    after_params.validate()
    old_parameters, new_parameters = asdict(before_params), asdict(after_params)
    changed = sorted(n for n in old_parameters.keys() | new_parameters.keys()
                     if old_parameters.get(n) != new_parameters.get(n))
    if set(changed) - {"guide_up_allowance"}:
        raise ValueError("Guide change permits only guide_up_allowance")
    required = {"side_1", "side_2", "end_1", "end_2", "bottom"}

    def inventory(model):
        shapes = list(model["parts"])
        labels = [q.label for q in shapes]
        if len(labels) != 5 or len(set(labels)) != 5 or set(labels) != required:
            raise ValueError("Guide change requires five unique complete part labels")
        for shape in shapes:
            if (not BRepCheck_Analyzer(shape.wrapped).IsValid()
                    or len(shape.solids()) != 1 or not isfinite(shape.volume) or shape.volume <= 0):
                raise ValueError("Guide change requires valid positive single-solid parts")
        return dict(zip(labels, shapes))

    before, after = inventory(before_model), inventory(after_model)

    def difference(a, b):
        common = intersection_volume(a, b)
        removed, added = a.volume-common, b.volume-common
        if not all(isfinite(v) for v in (removed, added)) or min(removed, added) < -tolerance:
            raise ValueError("Native material comparison returned inconsistent volumes")
        return dict(removed_mm3=max(0., removed), added_mm3=max(0., added),
                    symmetric_difference_mm3=max(0., removed)+max(0., added))

    p = before_params
    delta = after_params.guide_up_allowance-p.guide_up_allowance
    checks = {"guide_change_scope": dict(status="PASS", actual=dict(
        changed_parameters=changed, guide_translation_mm=delta),
        expected="only guide_up_allowance; accepted baseline and full geometry checks required")}
    for name in sorted(required):
        baseline, target = before[name], after[name]
        expected = baseline
        if name.startswith("end"):
            slab = baseline.bounding_box()
            margin = .01
            low = p.lower_z-p.guide_down_allowance-p.relief_radius-margin
            high = p.lower_z+20+p.guide_up_allowance+p.relief_radius+margin
            for center in (-p.thickness/2, p.width+p.thickness/2):
                roi = Pos((slab.min.X+slab.max.X)/2, center, (low+high)/2)*Box(
                    slab.size.X, p.thickness+p.clearance+2*p.relief_radius+2*margin, high-low)
                # Copy the real accepted void, including its dogbones. The crop
                # surrounds only this receiver, never the whole lower Z band.
                void = roi-baseline
                if not void.is_valid or not isfinite(void.volume) or void.volume <= tolerance:
                    raise ValueError("Baseline lower receiver void could not be measured")
                expected = (expected+void)-void.translate((0, 0, delta))
            if not expected.is_valid or len(expected.solids()) != 1:
                raise ValueError("Expected guide translation did not produce one valid solid")
        actual = difference(baseline, target)
        unexpected = difference(expected, target)
        actual["unexpected_mm3"] = unexpected["symmetric_difference_mm3"]
        checks["guide_change_"+name] = dict(
            status="PASS" if actual["unexpected_mm3"] < tolerance else "FAIL", actual=actual,
            expected=dict(unexpected_mm3_below=tolerance,
                          change="translated lower receiver voids" if name.startswith("end") else "unchanged"))
    return checks


def validate_geometry(model, p):
    checks = {}

    def record(name, passed, actual, expected=None, reason=None):
        checks[name] = dict(status="NOT_CHECKED" if passed is None else "PASS" if passed else "FAIL",
                            actual=actual)
        if expected is not None:
            checks[name]["expected"] = expected
        if reason:
            checks[name]["reason"] = reason

    parts = {q.label: q for q in model["parts"]}
    required = {"side_1", "side_2", "end_1", "end_2", "bottom"}
    record("part_inventory", len(model["parts"]) == 5 and set(parts) == required,
           sorted(parts), sorted(required))
    solids = {n: dict(valid=bool(BRepCheck_Analyzer(q.wrapped).IsValid()),
                     solids=len(q.solids()), volume_mm3=q.volume) for n, q in parts.items()}
    record("valid_single_solids", all(v["valid"] and v["solids"] == 1 and v["volume_mm3"] > 0
                                     for v in solids.values()), solids)
    profiles = {n: dict(valid=bool(BRepCheck_Analyzer(q.wrapped).IsValid()),
                       faces=len(q.faces()), closed=all(w.is_closed for f in q.faces() for w in f.wires()),
                       area_mm2=q.area, z_span_mm=q.bounding_box().size.Z,
                       z_offset_mm=q.bounding_box().min.Z) for n, q in model["profiles"].items()}
    record("flat_closed_profiles", set(profiles) == {"side", "end", "bottom"}
           and all(v["valid"] and v["faces"] == 1 and v["closed"] and v["area_mm2"] > 0
                   and v["z_span_mm"] < LENGTH_TOL and abs(v["z_offset_mm"]) < LENGTH_TOL
                   for v in profiles.values()), profiles)
    record("layout_inventory", len(model["layout"]) == 5, len(model["layout"]), 5)
    record("flat_inventory", set(model["flats"]) == {"side", "end", "bottom"},
           sorted(model["flats"]), ["bottom", "end", "side"])
    if not required.issubset(parts):
        record("dimensions", None, None, reason="Required part labels missing")
        return checks
    b = {n: q.bounding_box() for n, q in parts.items()}
    measured = dict(inside_length_mm=b["end_2"].min.X-b["end_1"].max.X,
                    inside_width_mm=b["side_2"].min.Y-b["side_1"].max.Y,
                    wall_height_mm=b["side_1"].size.Z,
                    leg_height_mm=b["side_1"].min.Z-b["end_1"].min.Z,
                    bottom_elevation_mm=b["bottom"].min.Z)
    expected = dict(inside_length_mm=p.length, inside_width_mm=p.width, wall_height_mm=p.height,
                    leg_height_mm=p.leg_height, bottom_elevation_mm=p.bottom_z)
    record("dimensions", all(abs(measured[k]-v) < LENGTH_TOL for k, v in expected.items()), measured, expected)
    thickness = {n: tuple(bb.size)[1 if n.startswith("side") else 2 if n == "bottom" else 0]
                 for n, bb in b.items()}
    record("sheet_thickness", all(abs(v-p.thickness) < LENGTH_TOL for v in thickness.values()), thickness, p.thickness)
    overlaps = [{"parts": [a, c], "common_mm3": v} for (a, q), (c, r) in combinations(parts.items(), 2)
                if (v := intersection_volume(q, r)) > VOLUME_TOL]
    record("assembled_no_interference", not overlaps, overlaps, [])

    # Use BREP edge endpoints rather than the requested angle or generator helpers.
    floor = p.upper_z
    base = floor-p.seat_drop
    centers = (-p.thickness/2, p.length+p.thickness/2)
    seats = []
    for center in centers:
        slopes = []
        for edge in model["profiles"]["side"].edges():
            if edge.geom_type != GeomType.LINE:
                continue
            a, c = edge.start_point(), edge.end_point()
            dx, dz = c.X-a.X, c.Y-a.Y
            if (abs(dx) < LENGTH_TOL or abs(dz) < LENGTH_TOL
                    or max(abs(a.X-center), abs(c.X-center)) > p.thickness+2
                    or min(a.Y, c.Y) < base-1e-5 or max(a.Y, c.Y) > base+p.wedge_run_height+1e-5):
                continue
            slope = dx/dz
            slopes.append(dict(angle_to_vertical_deg=degrees(atan2(abs(dx), abs(dz))),
                               floor_x_mm=a.X+(floor-a.Y)*slope,
                               mouth_x_mm=a.X+(base-a.Y)*slope,
                               throat_x_mm=a.X+(base+p.wedge_run_height-a.Y)*slope))
        slopes.sort(key=lambda s: s["floor_x_mm"])
        valid = len(slopes) == 2
        if valid:
            valid = (all(abs(s["angle_to_vertical_deg"]-p.wedge_angle_deg) < 1e-5 for s in slopes)
                     and all(abs(s["floor_x_mm"]-(center+sign*p.thickness/2)) < 1e-5
                             for s, sign in zip(slopes, (-1, 1)))
                     and abs(slopes[1]["mouth_x_mm"]-slopes[0]["mouth_x_mm"]-(p.thickness+p.clearance)) < 1e-5
                     and slopes[1]["throat_x_mm"]-slopes[0]["throat_x_mm"] > 0)
        seats.append(dict(center_x_mm=center, flanks=slopes, valid=valid))
    record("upper_v_geometry", all(s["valid"] for s in seats), seats,
           dict(angle_to_vertical_deg=p.wedge_angle_deg, mouth_width_mm=p.thickness+p.clearance,
                floor_width_mm=p.thickness))
    windows = []
    for center in (-p.thickness/2, p.width+p.thickness/2):
        levels = []
        for edge in model["profiles"]["end"].edges():
            if edge.geom_type != GeomType.LINE:
                continue
            a, c = edge.start_point(), edge.end_point()
            if (abs(a.Y-c.Y) < LENGTH_TOL and min(a.X, c.X) < center < max(a.X, c.X)
                    and floor-1 < a.Y < floor+32):
                levels.append(a.Y)
        windows.append(dict(center_y_mm=center, horizontal_levels_mm=sorted(levels)))
    expected_levels = [floor, floor+30+p.clearance]
    record("upper_fixed_windows", all(len(w["horizontal_levels_mm"]) == 2
           and all(abs(a-c) < LENGTH_TOL for a, c in zip(w["horizontal_levels_mm"], expected_levels))
           for w in windows), windows, expected_levels)
    lower_windows = []
    for center in (-p.thickness/2, p.width+p.thickness/2):
        levels = []
        for edge in model["profiles"]["end"].edges():
            if edge.geom_type == GeomType.LINE:
                a, c = edge.start_point(), edge.end_point()
                if (abs(a.Y-c.Y) < LENGTH_TOL and min(a.X, c.X) < center < max(a.X, c.X)
                        and p.lower_z-2 < a.Y < p.lower_z+22):
                    levels.append(a.Y)
        lower_windows.append(dict(center_y_mm=center, horizontal_levels_mm=sorted(levels)))
    lower_levels = [p.lower_z-p.guide_down_allowance, p.lower_z+20+p.guide_up_allowance]
    record("lower_receiver_windows", all(len(w["horizontal_levels_mm"]) == 2
           and all(abs(a-c) < LENGTH_TOL for a, c in zip(w["horizontal_levels_mm"], lower_levels))
           for w in lower_windows), lower_windows, lower_levels)
    relief = [dict(center=list(e.arc_center), radius_mm=e.radius,
                   lowest_z_mm=e.bounding_box().min.Y)
              for e in model["profiles"]["side"].edges()
              if e.geom_type == GeomType.CIRCLE and abs(e.radius-.1*p.thickness) < 1e-6
              and any(abs(e.arc_center.X-c) < p.thickness+2 for c in centers)]
    record("upper_corner_relief", len(relief) == 4 and all(v["lowest_z_mm"] > floor+LENGTH_TOL for v in relief),
           relief, "four native corner relief arcs strictly above bearing floor")
    for side in ("side_1", "side_2"):
        hits = motion_collision(parts, [side], ["end_1", "end_2"], (0, 0, -.05))
        record("seated_"+side, {h["fixed"] for h in hits} == {"end_1", "end_2"}, hits,
               "downward 0.05 mm blocked at both upper V seats")
    for name in ("bottom",):
        hits = motion_collision(parts, [name], [n for n in parts if n != name], (0, 0, -.1))
        record("seated_"+name, bool(hits), hits)

    # Crop real parts to the lower-guide band, excluding upper bearing geometry.
    band = Pos(p.length/2, p.width/2, p.lower_z+10)*Box(p.length+2*p.tab_reach+20,
                                                        p.width+100, 24)
    lower = {n: Compound(children=list(q.intersect(band).solids()))
             for n, q in parts.items() if n in ("side_1", "end_1", "end_2")}
    for name, axis, limit in (("y_minus", (0, -1, 0), p.clearance/2),
                              ("y_plus", (0, 1, 0), p.clearance/2),
                              ("z_down", (0, 0, -1), p.guide_down_allowance),
                              ("z_up", (0, 0, 1), p.guide_up_allowance)):
        distances = [limit-.01, limit+.01]
        volumes = [sum(intersection_volume(lower["side_1"].translate(Vector(axis)*d), lower[n])
                       for n in ("end_1", "end_2")) for d in distances]
        record("lower_guide_"+name, volumes[0] <= VOLUME_TOL and volumes[1] > VOLUME_TOL,
               dict(travel_bracket_mm=distances, common_mm3=volumes), limit)
    hits = motion_collision(parts, ["end_2"], ["side_1", "side_2"], (p.tab_reach+10, 0, 0))
    record("v_restrains_end", {"side_1", "side_2"}.issubset({h["fixed"] for h in hits}), hits)
    raised = dict(parts)
    for n in ("side_1", "side_2"):
        raised[n] = raised[n].translate((0, 0, p.release_lift))
    hits = motion_collision(raised, ["end_2"], ["side_1", "side_2", "bottom", "end_1"],
                            (p.tab_reach+10, 0, 0))
    record("raised_end_withdrawal", not hits, hits,
           "continuous withdrawal clears raised V seats without retaining keys")
    # Probe the former retaining-slot bands on both actual assembled solids.
    # At the projection roof the material ends normally: no extension was added
    # while filling the old top-open slots.
    slot_evidence = []
    for name, y in (("side_1", -p.thickness/2), ("side_2", p.width+p.thickness/2)):
        solid = parts[name].solids()[0]
        for x0 in (-2*p.thickness-p.key_float, p.length+p.thickness+p.key_float):
            x = x0+p.thickness/2
            filled = [solid.is_inside((x+dx, y, base+dz))
                      for dx in (-p.thickness/3, 0, p.thickness/3)
                      for dz in (16, 20, 29.9)]
            roof_clear = not solid.is_inside((x, y, base+30.1))
            slot_evidence.append(dict(part=name, x_mm=x, material_probes=filled,
                                      above_roof_clear=roof_clear))
    record("no_retaining_slots", all(all(e["material_probes"]) and e["above_roof_clear"]
                                     for e in slot_evidence), slot_evidence,
           "four former slot bands filled below the original projection roof")

    # Each stage starts from the previous stage's endpoint; removed parts leave
    # the active inventory. This is essential for the raised sidewall steps.
    pose = dict(parts)
    active = set(parts)
    motions = model.get("motions", [])
    record("assembly_motions_present", len(motions) == 4, len(motions), 4)
    for index, motion in enumerate(motions):
        try:
            moving, fixed = motion["moving"], motion["fixed"]
            delta = tuple(motion["delta"])
            lift = set(moving) == {"side_1", "side_2"} and delta[2] > 0
            if index == 0:
                correct_stage = lift and all(abs(a-c) < LENGTH_TOL
                                            for a, c in zip(delta, (0, 0, p.release_lift)))
            else:
                expected_moving = {"end_2"} if index == 1 else {"bottom"} if index == 2 else {"side_1", "side_2"}
                correct_stage = set(moving) == expected_moving and delta == (p.tab_reach+10, 0, 0)
            if not moving or not set(moving).issubset(active) or set(fixed) != active-set(moving):
                raise ValueError("Motion fixed labels must equal all remaining nonmoving parts")
            hits = motion_collision(pose, moving, fixed, delta)
            record("motion_"+motion["name"], correct_stage and not hits,
                   dict(delta_mm=list(delta), continuous=True, stage=index+1,
                        collision_witnesses=hits), "collision-free sequential disassembly stage")
            for n in moving:
                pose[n] = pose[n].translate(delta)
            if not lift:
                active.difference_update(moving)
        except Exception as exc:
            record("motion_"+motion["name"], None, None, reason=f"Continuous sweep failed: {exc}")
    record("disassembly_terminal_inventory", active == {"end_1"}, sorted(active), ["end_1"])
    return checks
