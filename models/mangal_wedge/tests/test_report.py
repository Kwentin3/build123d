"""Acceptance keeps an engineering contradiction explicit, even with green code."""
import json

import pytest

from models.mangal_wedge.mechanics import short_taper_comparison
from models.mangal_wedge.model import run


def test_short_taper_options_keep_clearance_and_stop_tradeoff_explicit():
    choices=short_taper_comparison()
    reserve=choices['reserve_stop']
    assert reserve['cold_corner_cases']==32
    assert reserve['all_cold_corners_contact_before_working_end']
    assert reserve['max_settled_travel_mm']<reserve['working_height_mm']<reserve['stop_travel_mm']
    final=choices['load_bearing_stop']
    assert final['all_tolerances_enter_parallel_land_before_stop']
    assert final['final_clearance_min_mm']==pytest.approx(.1)
    assert final['final_clearance_max_mm']==pytest.approx(.7)
    assert not final['zero_play_guaranteed']


def test_report_exports_do_not_hide_failed_design_requirements(tmp_path):
    assert run(tmp_path)==0  # execution completed, not design acceptance
    r=json.loads((tmp_path/'report.json').read_text(encoding='utf-8'))
    assert r['execution_status']=='PASS'
    assert r['design_requirements_status']=='FAIL'
    assert r['checks']['two_working_faces_force_moment_balance']['status']=='PASS'
    assert r['checks']['zero_play_and_old_stop_for_all_tolerances']['status']=='FAIL'
    assert r['checks']['hand_release_after_cooling_guaranteed']['status']=='NOT_CHECKED'
    assert len(r['friction_sweep'])==21
    assert (tmp_path/'report.md').read_text(encoding='utf-8').startswith('# Клиновое')
    assert all((tmp_path/f).stat().st_size>0 for f in (
        'angle_comparison.csv','friction_sweep.csv','sensitivity.csv','contact_scheme.svg'))
