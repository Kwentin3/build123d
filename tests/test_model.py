import math
import json
import hashlib
from contextlib import chdir
from pathlib import Path
import subprocess
import sys

import pytest
from build123d import GeomType, import_step, import_stl

from models.plate.model import make_plate
from models.plate.validation import check_plate


def check_geometry(plate, width):
    assert plate.is_valid
    assert len(plate.solids()) == 1
    size = plate.bounding_box().size
    assert (size.X, size.Y, size.Z) == pytest.approx((width, 60, 8))
    assert plate.volume == pytest.approx(width * 60 * 8 - math.pi * 6**2 * 8)
    bores = plate.faces().filter_by(GeomType.CYLINDER)
    assert len(bores) == 1
    bore = bores[0]
    assert bore.radius == pytest.approx(6)
    bounds = bore.bounding_box()
    assert tuple(bounds.min) == pytest.approx((-6, -6, -4))
    assert tuple(bounds.max) == pytest.approx((6, 6, 4))
    # Circular rims on both surfaces prove an open, centred through hole.
    rims = plate.edges().filter_by(GeomType.CIRCLE)
    assert len(rims) == 2
    assert sorted(edge.arc_center.Z for edge in rims) == pytest.approx([-4, 4])
    for edge in rims:
        assert edge.radius == pytest.approx(6)
        assert (edge.arc_center.X, edge.arc_center.Y) == pytest.approx((0, 0))


@pytest.mark.parametrize("width", [100, 120])
def test_geometry(width):
    check_geometry(make_plate(width=width), width)


@pytest.mark.parametrize("width", [100, 120])
def test_cli_exports(tmp_path, width):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "models" / "plate" / "model.py"),
         "--width", str(width), "--output-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["engineering_status"] == "PASS"
    assert report["errors"] == []
    assert report["checks"]["step_through_hole"]["status"] == "PASS"
    assert report["checks"]["visual_review"]["status"] == "NOT_CHECKED"
    assert report["checks"]["image_top"]["status"] == "NOT_CHECKED"
    root = Path(__file__).parents[1]
    assert report["source_sha256"] == {
        name: hashlib.sha256((root / "models/plate" / name).read_bytes()).hexdigest()
        for name in ("model.py", "validation.py")}
    assert report["dependency_source_sha256"] == {
        "requirements.txt": hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()}
    step = tmp_path / f"plate_{width}.step"
    stl = tmp_path / f"plate_{width}.stl"
    assert step.stat().st_size > 0
    assert stl.stat().st_size > 0
    assert report["artifacts"]["sha256"] == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (step, stl)}
    check_geometry(import_step(str(step)), width)
    # The native Windows STL reader has the same Unicode path limitation.
    with chdir(tmp_path):
        size = import_stl(stl.name).bounding_box().size
    assert (size.X, size.Y, size.Z) == pytest.approx((width, 60, 8), abs=1e-5)


def test_wrong_expectation_produces_failure_report(tmp_path):
    code = (
        "from models.plate.model import run_plate; import sys; "
        "sys.exit(run_plate(width=100, output_dir=sys.argv[1], expected="
        "dict(width=120,height=60,thickness=8,hole_diameter=12)))"
    )
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)],
                            cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=120)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["engineering_status"] == "FAIL"
    assert report["execution_status"] == "PASS"
    assert report["checks"]["dimensions"]["status"] == "FAIL"
    assert report["checks"]["step_dimensions"]["status"] == "FAIL"
    assert report["checks"]["dimensions"]["actual"] == pytest.approx([100, 60, 8])
    assert all(error["kind"] == "engineering" for error in report["errors"])


@pytest.mark.parametrize("bad_width", ["-1", "nan", "inf"])
def test_build_error_is_technical_and_not_geometry_pass(tmp_path, bad_width):
    command = [sys.executable, str(Path(__file__).parents[1] / "models/plate/model.py"),
               "--output-dir", str(tmp_path)]
    previous = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert previous.returncode == 0
    result = subprocess.run(
        [*command, "--width", bad_width],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["execution_status"] == "FAIL"
    assert report["engineering_status"] == "NOT_CHECKED"
    assert report["checks"]["dimensions"]["status"] == "NOT_CHECKED"
    # A prior successful run left STEP/STL files, but the failed run binds none.
    assert report["artifacts"] == {"report": str(tmp_path / "report.json"), "sha256": {}}
    assert report["errors"][0]["kind"] == "technical"


@pytest.mark.parametrize("defect", ["off_centre", "blind", "missing", "thickness"])
def test_checks_detect_geometric_defects(defect):
    from build123d import Box, Cylinder, Pos
    expected = dict(width=100, height=60, thickness=8, hole_diameter=12)
    if defect == "off_centre":
        plate = Box(100, 60, 8) - Pos(10, 0, 0) * Cylinder(6, 8)
        failed_check = "hole_position"
    elif defect == "blind":
        plate = Box(100, 60, 8) - Pos(0, 0, 3) * Cylinder(6, 4)
        failed_check = "through_hole"
    elif defect == "missing":
        plate = Box(100, 60, 8)
        failed_check = "hole_diameter"
    else:
        plate = Box(100, 60, 10) - Cylinder(6, 10)
        failed_check = "thickness"
    _, checks = check_plate(plate, expected)
    assert checks[failed_check]["status"] == "FAIL"
