"""Independent native-BREP measurements and sequential disassembly evidence."""
from itertools import combinations
from math import atan2, degrees

from build123d import Box, Compound, GeomType, Pos, Vector
from OCP.BRepCheck import BRepCheck_Analyzer

from models.mangal.validation import (LENGTH_TOL, VOLUME_TOL, intersection_volume,
                                      motion_collision)


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
    required = {"side_1", "side_2", "end_1", "end_2", "bottom", *[f"key_{i}" for i in range(1, 5)]}
    record("part_inventory", len(model["parts"]) == 9 and set(parts) == required,
           sorted(parts), sorted(required))
    solids = {n: dict(valid=bool(BRepCheck_Analyzer(q.wrapped).IsValid()),
                     solids=len(q.solids()), volume_mm3=q.volume) for n, q in parts.items()}
    record("valid_single_solids", all(v["valid"] and v["solids"] == 1 and v["volume_mm3"] > 0
                                     for v in solids.values()), solids)
    profiles = {n: dict(valid=bool(BRepCheck_Analyzer(q.wrapped).IsValid()),
                       faces=len(q.faces()), closed=all(w.is_closed for f in q.faces() for w in f.wires()),
                       area_mm2=q.area, z_span_mm=q.bounding_box().size.Z,
                       z_offset_mm=q.bounding_box().min.Z) for n, q in model["profiles"].items()}
    record("flat_closed_profiles", set(profiles) == {"side", "end", "bottom", "key"}
           and all(v["valid"] and v["faces"] == 1 and v["closed"] and v["area_mm2"] > 0
                   and v["z_span_mm"] < LENGTH_TOL and abs(v["z_offset_mm"]) < LENGTH_TOL
                   for v in profiles.values()), profiles)
    record("layout_inventory", len(model["layout"]) == 9, len(model["layout"]), 9)
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
    for name in ("bottom", "key_1", "key_2", "key_3", "key_4"):
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
    no_keys = [n for n in parts if not n.startswith("key") and n != "end_2"]
    hits = motion_collision(parts, ["end_2"], no_keys, (p.tab_reach+10, 0, 0))
    record("v_restrains_end_without_keys", {"side_1", "side_2"}.issubset({h["fixed"] for h in hits}), hits)
    raised = dict(parts)
    raised_group = ["side_1", "side_2", "key_1", "key_2", "key_3", "key_4"]
    for n in raised_group:
        raised[n] = raised[n].translate((0, 0, p.release_lift))
    # Keys are carried up by their cross-lap seats when the walls rise. Leaving
    # the keys at the original height would create a physically impossible
    # intersecting state and would not prove independent retention.
    raised_overlaps = [{"parts": [a, b], "common_mm3": v}
        for (a, q), (b, r) in combinations(raised.items(), 2)
        if (v := intersection_volume(q, r)) > VOLUME_TOL]
    lift_hits = motion_collision(parts, raised_group, ["end_1", "end_2", "bottom"],
                                 (0, 0, p.release_lift))
    record("raised_key_retention_state", not raised_overlaps and not lift_hits,
           dict(overlaps=raised_overlaps, lift_collisions=lift_hits),
           "walls and all keys reach a nonintersecting V-released pose together")
    hits = motion_collision(raised, ["end_2"], ["key_3", "key_4"], (p.tab_reach+10, 0, 0))
    record("keys_restrain_end", {h["fixed"] for h in hits} == {"key_3", "key_4"}, hits,
           "both retaining keys block withdrawal even after V seats released")

    # Each stage starts from the previous stage's endpoint; removed parts leave
    # the active inventory. This is essential for the raised sidewall steps.
    pose = dict(parts)
    active = set(parts)
    motions = model.get("motions", [])
    record("assembly_motions_present", len(motions) == 8, len(motions), 8)
    for index, motion in enumerate(motions):
        try:
            moving, fixed = motion["moving"], motion["fixed"]
            delta = tuple(motion["delta"])
            lift = set(moving) == {"side_1", "side_2"} and delta[2] > 0
            if index < 4:
                correct_stage = len(moving) == 1 and moving[0].startswith("key") and delta == (0, 0, 40)
            elif index == 4:
                correct_stage = lift and all(abs(a-c) < LENGTH_TOL
                                            for a, c in zip(delta, (0, 0, p.release_lift)))
            else:
                expected_moving = {"end_2"} if index == 5 else {"bottom"} if index == 6 else {"side_1", "side_2"}
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
