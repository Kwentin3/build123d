"""Gear-specific acceptance; the plate's tests and source stay untouched."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from models.gear.model import REFERENCE_24, REFERENCE_30, make_gear
from models.gear.validation import CHECK_NAMES, check_gear

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", params=[24, 30])
def measured_gear(request):
    teeth = request.param
    expected = REFERENCE_24 if teeth == 24 else REFERENCE_30
    gear = make_gear(teeth=teeth)
    actual, checks = check_gear(gear, expected)
    return teeth, gear, actual, checks


def test_actual_geometry(measured_gear):
    teeth, gear, actual, checks = measured_gear
    assert gear.is_valid
    assert actual["tooth_count"] == teeth
    assert actual["outer_diameter_mm"] == pytest.approx(52 if teeth == 24 else 64, abs=1e-6)
    assert actual["root_diameter_mm"] == pytest.approx(43 if teeth == 24 else 55, abs=1e-6)
    assert actual["thickness_mm"] == pytest.approx(10, abs=1e-6)
    assert actual["observed_pitch_angles_deg"] == pytest.approx([15 if teeth == 24 else 12] * teeth, abs=1e-6)
    for name in CHECK_NAMES:
        assert checks[name]["status"] == ("NOT_CHECKED" if name in ("pitch_circle", "base_circle") else "PASS"), checks[name]


@pytest.mark.parametrize("teeth", [24, 30])
def test_cli_exports_and_step_checks(tmp_path, teeth):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "models/gear/model.py"), "--teeth", str(teeth),
         "--output-dir", str(tmp_path)], cwd=tmp_path, capture_output=True, text=True, timeout=240,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["errors"] == []
    for kind in ("step", "stl"):
        assert Path(report["artifacts"][kind]).stat().st_size > 0
    assert report["step_actual"]["tooth_count"] == teeth
    for name in CHECK_NAMES:
        target = "NOT_CHECKED" if name in ("pitch_circle", "base_circle") else "PASS"
        assert report["checks"][f"step_{name}"]["status"] == target
    assert report["step_actual"]["volume_mm3"] == pytest.approx(report["actual"]["volume_mm3"], rel=1e-9)
    assert report["checks"]["visual_review"]["status"] == "NOT_CHECKED"


def test_wrong_outer_diameter_returns_engineering_failure(tmp_path):
    code = ("import sys; from models.gear.model import run_gear,REFERENCE_24; "
            "expected=dict(REFERENCE_24,outer_diameter=50); "
            "sys.exit(run_gear(output_dir=sys.argv[1],expected=expected))")
    completed = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT,
                               capture_output=True, text=True, timeout=240)
    assert completed.returncode == 1, completed.stdout + completed.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["engineering_status"] == "FAIL"
    assert report["execution_status"] == "PASS"
    assert report["actual"]["outer_diameter_mm"] == pytest.approx(52, abs=1e-6)
    assert report["checks"]["outer_diameter"]["status"] == "FAIL"
    assert report["checks"]["step_outer_diameter"]["status"] == "FAIL"


def test_involute_check_rejects_wrong_pressure_angle():
    gear = make_gear(pressure_angle_deg=25)
    actual, checks = check_gear(gear, REFERENCE_24)
    assert checks["occ_valid"]["status"] == "PASS"
    assert checks["outer_diameter"]["status"] == "PASS"
    assert actual["tooth_count"] == 24
    assert checks["involute_flanks"]["status"] == "FAIL"


def test_tooth_counter_does_not_take_count_from_expected(measured_gear):
    teeth, gear, _, _ = measured_gear
    expected = dict(REFERENCE_24 if teeth == 24 else REFERENCE_30, teeth=99)
    actual, checks = check_gear(gear, expected)
    assert actual["tooth_count"] == teeth
    assert checks["tooth_count"]["status"] == "FAIL"
