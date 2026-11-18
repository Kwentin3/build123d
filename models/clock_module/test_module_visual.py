"""A visual insert must preserve the published envelope and accepted housings."""

import pytest
from build123d import Pos

from models.clock_module.model import make_module, validate_module


@pytest.fixture(scope="module")
def module():
    return make_module()


def test_published_envelopes_and_explicit_unknowns(module):
    checks = validate_module(module)
    assert checks["published_outer_envelope"]["status"] == "PASS"
    assert checks["published_installation_envelope"]["status"] == "PASS"
    assert checks["valid_bodies"]["status"] == "PASS"
    assert checks["oem_profile_and_shoulder"]["status"] == "NOT_CHECKED"


def test_a_displaced_rear_component_fails_installation_contract(module):
    moved = dict(module, rear_envelope=Pos(1, 0, 0) * module["rear_envelope"])
    assert validate_module(moved)["published_installation_envelope"]["status"] == "FAIL"
