"""Independent force, kinematic and conditional-state acceptance checks."""

from dataclasses import replace
from math import radians, tan

import pytest

from models.mangal_wedge.mechanics import Case, evaluate, sensitivity_cases
from models.mangal_wedge.statics import solve_equilibrium, wedge_contacts


def test_lowering_closes_female_notch_gap_with_two_flanks():
    # At 45 degrees each flank consumes one mm of gap per mm lowering.
    r = evaluate(Case(angle_deg=45, gap_mm=2, stop_travel_mm=0.25))
    assert r["takeup_slope_mm_per_mm"] == pytest.approx(-2)
    assert r["first_contact_travel_mm"] == pytest.approx(1)
    assert r["free_play_mm"] == pytest.approx(1.5)
    assert r["normal_per_face_N"] == pytest.approx(0)


def test_nominal_twenty_degree_wedge_reaches_floor_before_contact():
    r = evaluate(Case(angle_deg=20))
    assert r["mode"] == "on_final_stop"
    assert r["first_contact_travel_mm"] > 0.6
    assert r["free_play_mm"] == pytest.approx(0.1632357189)
    assert r["normal_per_face_N"] == pytest.approx(0)
    assert r["stop_reaction_N"] == pytest.approx(r["weight_per_joint_N"])
    assert r["peak_up_force_per_joint_N"] == pytest.approx(r["weight_per_joint_N"])
    assert r["force_balance_residual_N"] == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("angle", [30, 40])
def test_nominal_steeper_wedges_settle_before_geometric_stop_interference(angle):
    r = evaluate(Case(angle_deg=angle))
    assert r["mode"] == "on_wedge_before_stop"
    assert r["first_contact_travel_mm"] < r["settled_travel_mm"] < 0.6
    assert r["signed_gap_at_stop_mm"] < 0
    assert r["free_play_mm"] == pytest.approx(0)
    assert r["stop_reaction_N"] == pytest.approx(0)
    assert r["force_balance_residual_N"] == pytest.approx(0, abs=1e-9)
    assert r["extra_down_force_to_force_stop_N"] > 0


def test_two_symmetric_frictionless_faces_carry_weight_and_compress_individually():
    # W=10 N, alpha=30 degrees: each N=10 N; 1000 N/mm per
    # normal spring gives 0.01 mm compression, hence 0.02 mm lowering.
    r = evaluate(Case(angle_deg=30, mass_wall_kg=1, gravity_m_s2=10,
                      joint_weight_share=1, mu_static=0, mu_seating=0,
                      gap_mm=0, stop_travel_mm=1, normal_stiffness_N_mm=1000))
    assert r["weight_per_joint_N"] == pytest.approx(10)
    assert r["normal_per_face_N"] == pytest.approx(10)
    assert r["settled_travel_mm"] == pytest.approx(0.02)
    assert r["initial_up_force_signed_N"] == pytest.approx(0, abs=1e-9)
    assert r["peak_up_force_per_joint_N"] == pytest.approx(10)


def test_symmetric_seating_reaction_matches_independent_unilateral_lp():
    case = Case(angle_deg=30, mu_static=0.3, mu_seating=0.3)
    r = evaluate(case)
    lp = solve_equilibrium(wedge_contacts(30, 0.3), r["weight_per_joint_N"])
    assert lp.feasible
    assert lp.forces["left"][0] == pytest.approx(r["normal_per_face_N"])
    assert lp.forces["right"][0] == pytest.approx(r["normal_per_face_N"])
    assert lp.forces["left"][1] == pytest.approx(r["tangent_force_per_face_down_N"])


def test_cooling_retained_normal_is_conditional_and_release_increases_only_for_locking_taper():
    # Assumed retained normal is exercised only after both wedge faces engage.
    locked = Case(angle_deg=30, mu_static=0.8)
    original = evaluate(locked)
    retained = evaluate(replace(locked, retained_extra_normal_N=10))
    assert original["mode"] == retained["mode"] == "on_wedge_before_stop"
    # 20 N extra sum normal: upward friction exceeds upward normal component.
    assert retained["initial_up_force_signed_N"]-original["initial_up_force_signed_N"] == pytest.approx(3.85640646055)
    assert retained["normal_per_face_N"] == pytest.approx(original["normal_per_face_N"])
    assert retained["peak_up_force_per_joint_N"] >= retained["weight_per_joint_N"]
    unlocked = evaluate(Case(angle_deg=30, mu_static=0, retained_extra_normal_N=10))
    assert unlocked["initial_up_force_signed_N"] < unlocked["weight_per_joint_N"]
    assert unlocked["peak_up_force_per_joint_N"] == pytest.approx(unlocked["weight_per_joint_N"])


def test_guide_can_block_entry_without_claiming_limiting_static_force_balance():
    r = evaluate(Case(guide_mu=0.3, guide_normal_N=60))
    assert r["mode"] == "blocked_at_entry"
    assert r["settled_travel_mm"] == pytest.approx(0)
    assert r["normal_per_face_N"] == pytest.approx(0)
    assert r["stop_reaction_N"] == pytest.approx(0)
    # mu*N is the available envelope. Actual static guide friction can be W.
    assert r["force_balance_residual_N"] is None


def test_correlated_stock_thickness_changes_both_weight_and_clearance():
    base = Case()
    rows = [r for r in sensitivity_cases(base)
            if r["angle_deg"] == 30 and r["varied_parameter"] == "actual_stock_thickness_mm"]
    assert len(rows) == 3
    thin, nominal, thick = sorted(rows, key=lambda r: r["varied_value"])
    assert [r["gap_mm"] for r in (thin, nominal, thick)] == pytest.approx([0.75, 0.6, 0.45])
    assert thin["weight_per_joint_N"] / nominal["weight_per_joint_N"] == pytest.approx(0.95)
    assert thick["weight_per_joint_N"] / nominal["weight_per_joint_N"] == pytest.approx(1.05)
    assert thin["first_contact_travel_mm"] > nominal["first_contact_travel_mm"] > thick["first_contact_travel_mm"]


def test_locking_threshold_is_flank_angle_from_vertical_and_zero_stiffness_rejected():
    critical = tan(radians(30))
    assert evaluate(Case(mu_static=critical))["self_locking"]
    assert not evaluate(Case(mu_static=critical-0.001))["self_locking"]
    assert evaluate(Case(mu_static=critical))["static_admissible_normal_per_face_N"][1] is None
    with pytest.raises(ValueError, match="stiffness"):
        evaluate(Case(normal_stiffness_N_mm=0))
