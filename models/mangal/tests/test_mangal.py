"""Real native geometry, parameter variants, and adversarial collision evidence."""

import pytest
from build123d import Align, Box, Plane, Pos, Rectangle

from models.mangal.model import Params, make_model
from models.mangal.validation import (intersection_volume, motion_collision,
                                      validate_geometry)


@pytest.fixture(scope="module")
def nominal():
    p = Params()
    return p, make_model(p)


@pytest.mark.parametrize("p", [Params(), Params(thickness=2), Params(thickness=4),
                              Params(length=600, width=350, height=180)])
def test_geometry_and_continuous_assembly(p):
    checks = validate_geometry(make_model(p), p)
    assert checks
    assert all(c["status"] == "PASS" for c in checks.values()), {
        name: result for name, result in checks.items() if result["status"] != "PASS"}


def test_sweep_finds_collision_between_clear_endpoints():
    moving = Box(1, 1, 1)
    fixed = Pos(5, 0, 0) * Box(.02, 2, 2)
    assert intersection_volume(moving, fixed) == 0
    assert intersection_volume(moving.translate((10, 0, 0)), fixed) == 0
    assert motion_collision({"moving": moving, "fixed": fixed},
                            ["moving"], ["fixed"], (10, 0, 0))


def test_removed_tongues_are_not_reported_as_supported(nominal):
    p, m = nominal
    altered = dict(m)
    altered["parts"] = list(m["parts"])
    side = next(part for part in m["parts"] if part.label == "side_1")
    # Remove both end projections without changing the wall or its height.
    keep = Pos(0, -p.thickness, 0) * Box(p.length, p.thickness,
                p.leg_height + p.height + 1, align=(Align.MIN, Align.MIN, Align.MIN))
    broken = side & keep
    broken.label = "side_1"
    altered["parts"][0] = broken
    checks = validate_geometry(altered, p)
    assert checks["valid_single_solids"]["status"] == "PASS"
    assert checks["seated_side_1"]["status"] == "FAIL"


def test_wrong_profile_and_injected_overlap_are_rejected(nominal):
    p, m = nominal
    altered = dict(m)
    altered["profiles"] = dict(m["profiles"], key=Pos(0, 0, 1) * Rectangle(30, 30))
    altered["parts"] = list(m["parts"])
    bottom = next(part for part in m["parts"] if part.label == "bottom")
    # Force its left tongue into the intact left end's frame below the slot.
    displaced = bottom.translate((0, 0, -5))
    displaced.label = "bottom"
    altered["parts"][4] = displaced
    checks = validate_geometry(altered, p)
    assert checks["flat_closed_profiles"]["status"] == "FAIL"
    assert checks["assembled_no_interference"]["status"] == "FAIL"


def test_reversed_side_vertical_orientation_cannot_seat(nominal):
    p, m = nominal
    parts = {part.label: part for part in m["parts"]}
    side = parts["side_1"].mirror(Plane(origin=(0, 0, p.leg_height + p.height/2),
                                          z_dir=(0, 0, 1)))
    assert intersection_volume(side, parts["end_1"]) > 1
