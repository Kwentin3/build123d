"""A/C: edit a source copy, reject valid collateral geometry, fix and rerun."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from build123d import Box, Cylinder, export_step, import_step

from models.plate.model import make_plate
from models.plate.validation import check_bore_change, check_plate


EXPECTED = dict(width=100, height=60, thickness=8, hole_diameter=14)
ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("diameter", [10, 12, 14])
def test_only_bore_diameter_may_change(diameter):
    before, after = make_plate(), make_plate(hole_diameter=diameter)
    check = check_bore_change(before, after, dict(EXPECTED, hole_diameter=diameter))["bore_change"]
    assert check["status"] == "PASS"
    assert check["actual"]["unexpected_mm3"] <= .001
    assert check["actual"]["symmetric_difference_mm3"] == pytest.approx(
        abs(before.volume - after.volume), abs=.001)


def test_valid_same_size_same_volume_body_shift_is_unexpected():
    after = Box(100, 60, 8).translate((.2, 0, 0)) - Cylinder(7, 8)
    assert after.is_valid
    assert all(c["status"] == "PASS" for c in check_plate(after, EXPECTED)[1].values())
    check = check_bore_change(make_plate(), after, EXPECTED)["bore_change"]
    assert check["status"] == "FAIL"
    assert check["actual"]["unexpected_mm3"] == pytest.approx(192, abs=.001)


def test_wrong_baseline_is_not_accepted():
    with pytest.raises(ValueError, match="Baseline"):
        check_bore_change(make_plate(width=120), make_plate(hole_diameter=14), EXPECTED)


def test_source_copy_edit_detect_fix_and_step(tmp_path):
    source = ROOT / "models/plate/model.py"
    original_bytes = source.read_bytes()
    baseline_path = tmp_path / "accepted.step"
    export_step(make_plate(), str(baseline_path))
    variant = tmp_path / "models/plate"
    variant.mkdir(parents=True)
    shutil.copy2(source.with_name("validation.py"), variant / "validation.py")
    shutil.copy2(ROOT / "requirements.txt", tmp_path / "requirements.txt")
    candidate = variant / "model.py"
    intended = source.read_text(encoding="utf-8").replace("HOLE_DIAMETER = 12.0", "HOLE_DIAMETER = 14.0")
    reports = []
    for name, text, expected_exit in (
        ("intended", intended, 0),
        ("unexpected", intended.replace("Box(width, height, thickness) -",
                                        "Box(width, height, thickness).translate((.2, 0, 0)) -"), 1),
        ("fixed", intended, 0),
    ):
        candidate.write_text(text, encoding="utf-8")
        out = tmp_path / name
        result = subprocess.run(
            [sys.executable, str(candidate), "--output-dir", str(out), "--bore-baseline", str(baseline_path)],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == expected_exit, result.stdout + result.stderr
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        reports.append(report)
        assert report["bore_baseline"]["sha256"] == hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        assert report["source_sha256"]["model.py"] == hashlib.sha256(candidate.read_bytes()).hexdigest()
        assert report["execution_status"] == "PASS"
        assert report["checks"]["hole_diameter"]["actual"] == pytest.approx([14])
        assert report["checks"]["step_through_hole"]["status"] == "PASS"
        assert report["checks"]["bore_change"]["status"] == ("FAIL" if expected_exit else "PASS")
        assert report["checks"]["step_bore_change"]["status"] == ("FAIL" if expected_exit else "PASS")
        restored = import_step(str(out / "plate_100.step"))
        assert restored.is_valid
    assert reports[0]["source_sha256"] != reports[1]["source_sha256"]
    assert reports[0]["source_sha256"] == reports[2]["source_sha256"]
    assert source.read_bytes() == original_bytes


def test_unreadable_baseline_is_technical_not_pass(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "models/plate/model.py"), "--output-dir", str(tmp_path),
         "--bore-baseline", str(tmp_path / "missing.step")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["execution_status"] == "FAIL"
    assert report["engineering_status"] == "NOT_CHECKED"
    assert report["checks"]["step_bore_change"]["status"] == "NOT_CHECKED"
