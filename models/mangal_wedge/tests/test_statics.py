"""Hand-calculation checks for the independent unilateral statics LP."""

from math import cos, radians, sin, tan

import pytest

from models.mangal_wedge.statics import (
    Contact, lower_shoulder, lower_stop, maximum_upward_load,
    normal_range, solve_equilibrium, wedge_contacts,
)


def test_frictionless_symmetric_normals():
    a, weight = radians(30), 10
    result = solve_equilibrium(wedge_contacts(30, 0), weight)
    assert result.feasible
    for normal, tangent in result.forces.values():
        assert normal == pytest.approx(weight / (2*sin(a)))
        assert tangent == pytest.approx(0)
    assert result.residual == pytest.approx((0, 0, 0), abs=1e-9)


@pytest.mark.parametrize("angle", [20, 30, 40])
def test_minimum_normal_at_upward_friction_limit(angle):
    a, weight, mu = radians(angle), 9.2868, 0.2
    result = solve_equilibrium(wedge_contacts(angle, mu), weight)
    expected = weight / (2*(sin(a)+mu*cos(a)))
    for normal, tangent in result.forces.values():
        assert normal == pytest.approx(expected)
        assert tangent == pytest.approx(mu*normal)


def test_self_locking_threshold_distinguishes_finite_and_unbounded():
    angle, weight = 30, 10
    critical = tan(radians(angle))
    _, finite = normal_range(wedge_contacts(angle, critical-0.01), weight, "left")
    assert finite.feasible
    assert finite.objective == pytest.approx(weight / (2*(sin(radians(angle))-(critical-0.01)*cos(radians(angle)))))
    for mu in (critical, critical+0.1):
        minimum, maximum = normal_range(wedge_contacts(angle, mu), weight, "left")
        assert minimum.feasible
        assert maximum.status == "unbounded"
        assert "not infinite" in maximum.message


def test_first_end_only_cantilever_cannot_balance_without_guide():
    result = solve_equilibrium(wedge_contacts(30, 0), 18.5736, eccentricity=250)
    assert result.status == "infeasible"
    assert result.forces == {}


def test_engaged_guide_balances_moment_with_positive_reactions():
    # With frictionless flanks, N_R+N_L=W/sin(a). The guide force G
    # satisfies 80 G + (t/2)sin(a)(N_R-N_L) = W e and
    # cos(a)(N_R-N_L)+G=0.
    a, weight, e, half_t, drop = radians(30), 10, 10, 1.5, 80
    guide = weight*e / (drop-half_t*tan(a))
    difference = -guide/cos(a)
    total = weight/sin(a)
    contacts = (*wedge_contacts(30, 0), lower_shoulder(1))
    result = solve_equilibrium(contacts, weight, eccentricity=e)
    assert result.feasible
    assert result.forces["guide"] == pytest.approx((guide, 0))
    assert result.forces["left"][0] == pytest.approx((total-difference)/2)
    assert result.forces["right"][0] == pytest.approx((total+difference)/2)
    assert all(n >= 0 for n, _ in result.forces.values())
    assert result.residual == pytest.approx((0, 0, 0), abs=1e-9)
    assert solve_equilibrium((*wedge_contacts(30, 0), lower_shoulder(-1)), weight, e).status == "infeasible"


def test_reverse_pull_requires_retained_normal_and_correct_friction_sign():
    a, mu, normal, weight = radians(30), 0.8, 20, 10
    result = maximum_upward_load(wedge_contacts(30, mu), weight, {"left": normal, "right": normal})
    assert result.feasible
    assert result.upward_load == pytest.approx(weight+2*normal*(mu*cos(a)-sin(a)))
    for n, tangent in result.forces.values():
        assert n == pytest.approx(normal)
        assert tangent == pytest.approx(-mu*normal)
    assert result.residual == pytest.approx((0, 0, 0), abs=1e-9)


def test_optional_stop_can_bypass_wedge_so_is_not_wedge_acceptance():
    result = solve_equilibrium((*wedge_contacts(30, 0), lower_stop()), 10)
    assert result.feasible
    assert result.forces["left"][0] == pytest.approx(0)
    assert result.forces["right"][0] == pytest.approx(0)
    assert result.forces["stop"] == pytest.approx((10, 0))


def test_invalid_contact_and_preload_are_rejected():
    with pytest.raises(ValueError):
        Contact("invalid", (0, 0), (1, 0), (1, 0), 0.2)
    with pytest.raises(ValueError):
        solve_equilibrium(wedge_contacts(30, 0), 10, fixed_normals={"left": -1})
    with pytest.raises(ValueError):
        maximum_upward_load(wedge_contacts(30, 0), 10, {})
