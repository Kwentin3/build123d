"""Valid BREP and clear endpoints must not mask a blocked service operation."""

import pytest
from build123d import Pos

from models.filter_holder.model import make_holder
from models.filter_holder.validation import review_geometry, service_check


def test_valid_initial_and_final_poses_do_not_prove_the_service_path():
    checks = review_geometry(make_holder())
    assert checks["valid_solids"]["status"] == "PASS"
    assert checks["installed_clearance"]["status"] == "PASS"
    path = checks["service_path"]
    assert path["initial_collision_mm3"] == pytest.approx(0, abs=1e-5)
    assert path["final_collision_mm3"] == pytest.approx(0, abs=1e-5)
    assert path["continuous_path_collision_mm3"] == pytest.approx(2400, abs=1e-5)
    assert path["status"] == "FAIL"


def test_alternative_retains_a_clear_service_path_without_claiming_strength():
    checks = review_geometry(make_holder(-8))
    assert checks["service_path"]["status"] == "PASS"
    assert checks["structural_capacity"]["status"] == "NOT_CHECKED"
    assert checks["manufactured_fit"]["status"] == "NOT_CHECKED"


def test_missing_path_contract_is_unknown_instead_of_accepting_default_motion():
    path = service_check(make_holder(), None)
    assert path["status"] == "NOT_CHECKED"
    assert path["needed"] and path["next_action"]


def test_exact_sweep_rejects_a_different_cartridge_geometry():
    parts = make_holder()
    parts["cartridge"] = Pos(1, 0, 0) * parts["cartridge"]
    with pytest.raises(ValueError, match="specified full rectangular"):
        service_check(parts)
