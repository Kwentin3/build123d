"""Acceptance and deliberate geometry defects for the clock-family contract."""

from copy import copy

from build123d import Cylinder, Pos, export_step, import_step
import pytest

from models.clock_family.model import make_family
from models.clock_family.validation import check_change, validate_variant


@pytest.fixture(scope="module")
def families(tmp_path_factory):
    baseline, enlarged = make_family(.4), make_family(1.0)
    # The protected geometry really passes through STEP; regenerating from the
    # current candidate source would conceal unrelated generator changes.
    directory = tmp_path_factory.mktemp("clock_accepted_step")
    imported = {}
    for variant, model in baseline.items():
        parts = {}
        for label, part in model["parts"].items():
            path = directory / f"{variant}_{label}.step"
            assert export_step(part, str(path))
            parts[label] = import_step(str(path))
            parts[label].label = label
        imported[variant] = dict(name=variant, parts=parts)
    return baseline, imported, enlarged


@pytest.mark.parametrize("variant", ("desk", "wall", "portable"))
def test_nominal_geometry_and_imported_step(families, variant):
    baseline, imported, _ = families
    for family in (baseline, imported):
        checks = validate_variant(family[variant], .4)
        assert not {k: v for k, v in checks.items() if v["status"] == "FAIL"}
        assert checks["oem_retention_fit"]["status"] == "NOT_CHECKED"
        assert checks["physical_service"]["status"] == "NOT_CHECKED"


@pytest.mark.parametrize("variant", ("desk", "wall", "portable"))
def test_only_enlarged_bore_passes_against_step(families, variant):
    _, imported, enlarged = families
    checks = check_change(imported[variant]["parts"], enlarged[variant]["parts"])
    assert all(v["status"] == "PASS" for v in checks.values()), checks


def test_unrelated_body_hole_fails_change_even_with_functional_bore(families):
    _, imported, enlarged = families
    bad = dict(name="desk", parts=copy(enlarged["desk"]["parts"]))
    bad["parts"]["body"] = bad["parts"]["body"] - Pos(50, 0, 6) * Cylinder(1, 8)
    bad["parts"]["body"].label = "body"
    functional = validate_variant(bad, 1.0)
    assert functional["bore_diameter"]["status"] == "PASS"
    assert functional["oem_envelope"]["status"] == "PASS"
    change = check_change(imported["desk"]["parts"], bad["parts"])
    assert change["change_body"]["status"] == "FAIL"
    assert change["change_body"]["actual"]["unexpected_mm3"] > 20


def test_one_stale_variant_is_rejected(families):
    baseline, _, enlarged = families
    candidate = dict(enlarged, wall=baseline["wall"])
    checks = validate_variant(candidate["wall"], 1.0)
    assert checks["bore_diameter"]["status"] == "FAIL"
    assert checks["bore_continuous_clearance"]["status"] == "FAIL"


def test_too_small_bore_collides_with_published_installation_envelope(families):
    baseline, _, _ = families
    bad = dict(name="wall", parts=copy(baseline["wall"]["parts"]))
    ring = Pos(0, 0, 11) * (Cylinder(39, 22) - Cylinder(38.4, 22))
    bad["parts"]["body"] = bad["parts"]["body"] + ring
    bad["parts"]["body"].label = "body"
    checks = validate_variant(bad, .4)
    assert checks["oem_envelope"]["status"] == "FAIL"


def test_missing_part_and_changed_lid_are_rejected(families):
    _, imported, enlarged = families
    before = imported["portable"]["parts"]
    missing = {"body": enlarged["portable"]["parts"]["body"]}
    assert check_change(before, missing)["change_part_identity"]["status"] == "FAIL"
    changed = copy(enlarged["portable"]["parts"])
    changed["lid"] = changed["lid"] - Pos(0, 0, 29.5) * Cylinder(1, 3)
    changed["lid"].label = "lid"
    assert check_change(before, changed)["change_lid"]["status"] == "FAIL"


def test_out_of_place_lid_is_rejected(families):
    baseline, _, _ = families
    bad = dict(name="portable", parts=copy(baseline["portable"]["parts"]))
    bad["parts"]["lid"] = Pos(2, 0, 0) * bad["parts"]["lid"]
    bad["parts"]["lid"].label = "lid"
    checks = validate_variant(bad, .4)
    assert checks["lid_bounds"]["status"] == "FAIL"
    assert checks["portable_screw_alignment"]["status"] == "FAIL"
