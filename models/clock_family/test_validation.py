"""Rear joint acceptance and deliberate failures; accepted old STEP stays frozen."""

from copy import copy
from build123d import Box, Cylinder, Pos, export_step, import_step
import pytest

from models.clock_family.model import make_family
from models.clock_family.refactor import load_frozen
from models.clock_family.validation import check_change, check_refactor, validate_variant


def _cylinder(radius, z0, z1, x=0, y=0):
    return Pos(x, y, (z0+z1)/2)*Cylinder(radius, z1-z0)


def _mutant(model):
    result = dict(model, parts=copy(model["parts"]))
    if "hardware" in model:
        result["hardware"] = copy(model["hardware"])
    return result


def _part(model, name, shape):
    shape.label = name
    model["parts"][name] = shape


@pytest.fixture(scope="module")
def families(tmp_path_factory):
    baseline, enlarged = make_family(.4), make_family(1.0)
    directory = tmp_path_factory.mktemp("rear_clock_step")
    restored = {}
    for variant, model in baseline.items():
        parts = {}
        for label, shape in model["parts"].items():
            path = directory/f"{variant}_{label}.step"
            assert export_step(shape, str(path))
            parts[label] = import_step(str(path))
            parts[label].label = label
        restored[variant] = dict(name=variant, parts=parts)
    return baseline, restored, enlarged


@pytest.fixture(scope="module")
def frozen():
    # One owner verifies the versioned historical ZIP and its four STEP members.
    # Missing or changed evidence is an error, never a skipped acceptance check.
    result = load_frozen()
    assert sum(map(len, result.values())) == 4
    return result


@pytest.mark.parametrize("variant", ("desk", "wall", "portable"))
def test_nominal_and_step_reimport_geometry(families, variant):
    baseline, restored, _ = families
    for family in (baseline, restored):
        checks = validate_variant(family[variant], .4)
        assert not {k: v for k, v in checks.items() if v["status"] == "FAIL"}
        assert checks["strength_and_manufacturing"]["status"] == "NOT_CHECKED"
        assert checks["physical_service"]["status"] == "NOT_CHECKED"


@pytest.mark.parametrize("variant", ("desk", "wall", "portable"))
def test_refactor_uses_only_approved_body_zones(families, frozen, variant):
    checks = check_refactor(frozen[variant], families[0][variant]["parts"], variant)
    assert all(v["status"] == "PASS" for v in checks.values()), checks


@pytest.mark.parametrize("variant", ("desk", "wall", "portable"))
def test_bore_change_preserves_new_rear_joint_and_every_lid(families, variant):
    _, restored, enlarged = families
    checks = check_change(restored[variant]["parts"], enlarged[variant]["parts"])
    assert all(v["status"] == "PASS" for v in checks.values()), checks


def test_front_through_hole_rejected_without_changing_oem_bore(families, frozen):
    bad = _mutant(families[0]["wall"])
    _part(bad, "body", bad["parts"]["body"]-_cylinder(1, -1, 31, y=50))
    checks = validate_variant(bad, .4)
    assert checks["front_closed"]["status"] == "FAIL"
    assert checks["bore_diameter"]["status"] == "PASS"
    assert check_refactor(frozen["wall"], bad["parts"], "wall")["refactor_body"]["status"] == "FAIL"


def test_overlong_or_wrong_screw_envelope_rejected(families):
    bad = _mutant(families[0]["desk"])
    seat = 30.4
    screw = _cylinder(1.5, seat-15, seat, -33.5, -33.5)
    screw += _cylinder(2.65, seat, seat+2.3, -33.5, -33.5)
    screw.label = "cover_screw_1"
    bad["hardware"][screw.label] = screw
    checks = validate_variant(bad, .4)
    assert checks["cover_screw_1"]["status"] == "FAIL"
    assert checks["bore_diameter"]["status"] == "PASS"


def test_short_blind_pilot_loses_required_bottom_reserve(families):
    bad = _mutant(families[0]["desk"])
    _part(bad, "body", bad["parts"]["body"]+_cylinder(1.2, 16, 18.5, -33.5, -33.5))
    checks = validate_variant(bad, .4)
    assert checks["blind_pilots"]["status"] == "FAIL"
    assert checks["rear_screw_budget"]["status"] == "FAIL"


def test_supportless_boss_is_rejected(families):
    bad = _mutant(families[0]["desk"])
    body = bad["parts"]["body"]-_cylinder(5.1, 13.5, 28, -33.5, -33.5)
    island = _cylinder(5, 24, 28, -33.5, -33.5)-_cylinder(1.2, 24, 28, -33.5, -33.5)
    _part(bad, "body", body+island)
    checks = validate_variant(bad, .4)
    assert checks["body_solid_count"]["status"] == "FAIL"
    assert checks["rear_boss_support"]["status"] == "FAIL"


def test_shifted_lid_is_rejected(families):
    bad = _mutant(families[0]["portable"])
    _part(bad, "lid", Pos(0, 0, 1)*bad["parts"]["lid"])
    checks = validate_variant(bad, .4)
    assert checks["lid_bounds"]["status"] == "FAIL"
    assert checks["lid_mating"]["status"] == "FAIL"


def test_clear_final_pose_does_not_prove_rear_removal(families):
    bad = _mutant(families[0]["desk"])
    # Joins retained rear foot; obstructs backwards motion while initial pose clears.
    obstacle = Pos(60, -29, 45)*Box(2, 60, 2)
    obstacle += Pos(55, 0, 45)*Box(12, 2, 2)
    _part(bad, "body", bad["parts"]["body"]+obstacle)
    checks = validate_variant(bad, .4)
    assert checks["lid_mating"]["status"] == "PASS"
    assert checks["lid_removal"]["status"] == "FAIL"


def test_old_front_lug_is_rejected(families):
    bad = _mutant(families[0]["portable"])
    old_lug = _cylinder(10, 0, 8, y=64)-_cylinder(2.5, 0, 8, y=64)
    _part(bad, "body", bad["parts"]["body"]+old_lug)
    checks = validate_variant(bad, .4)
    assert checks["portable_old_front_lug_absent"]["status"] == "FAIL"


def test_wall_keyhole_obstruction_blocks_specified_mounting_path(families):
    bad = _mutant(families[0]["wall"])
    _part(bad, "lid", bad["parts"]["lid"]+_cylinder(5, 30, 35, -50, 8))
    checks = validate_variant(bad, .4)
    assert checks["wall_keyhole_entry"]["status"] == "FAIL"
    assert checks["wall_hang_remove_path"]["status"] == "FAIL"


def test_unrelated_new_lid_hole_is_rejected(families):
    bad = _mutant(families[0]["wall"])
    _part(bad, "lid", bad["parts"]["lid"]-_cylinder(1, 30, 35, y=40))
    checks = validate_variant(bad, .4)
    assert checks["rear_cover_passages"]["status"] == "PASS"
    assert checks["lid_volume"]["status"] == "FAIL"


def test_unrelated_hole_and_lid_change_fail_bore_only_contract(families):
    _, restored, enlarged = families
    bad = _mutant(enlarged["desk"])
    _part(bad, "body", bad["parts"]["body"]-_cylinder(1, 2, 10, 50))
    assert validate_variant(bad, 1.0)["bore_diameter"]["status"] == "PASS"
    assert check_change(restored["desk"]["parts"], bad["parts"])["change_body"]["status"] == "FAIL"
    _part(bad, "lid", bad["parts"]["lid"]-_cylinder(1, 28, 33))
    assert check_change(restored["desk"]["parts"], bad["parts"])["change_lid"]["status"] == "FAIL"


def test_stale_and_too_small_bores_are_rejected(families):
    baseline, _, _ = families
    assert validate_variant(baseline["wall"], 1.0)["bore_diameter"]["status"] == "FAIL"
    bad = _mutant(baseline["wall"])
    _part(bad, "body", bad["parts"]["body"]+_cylinder(39, 0, 22)-_cylinder(38.4, 0, 22))
    assert validate_variant(bad, .4)["oem_envelope"]["status"] == "FAIL"
