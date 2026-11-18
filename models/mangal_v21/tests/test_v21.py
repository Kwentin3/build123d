"""V2.1 keyless acceptance and native-geometry defect regressions."""
from dataclasses import replace
from copy import copy
import hashlib
import json
from pathlib import Path

import pytest
from build123d import Box, Compound, Plane, Polygon, Pos, Rectangle, export_step, extrude, import_step

from models.mangal_v21.model import Params, make_model, run
from models.mangal_v21.validation import check_guide_change, validate_geometry
from models.mangal.validation import motion_collision


@pytest.fixture(scope="module")
def nominal():
    p = Params()
    model = make_model(p)
    return p, model, validate_geometry(model, p)


def test_v21_nominal_acceptance(nominal):
    _, model, checks = nominal
    assert len(model["parts"]) == 5
    assert set(model["profiles"]) == {"side", "end", "bottom"}
    assert not any(q.label.startswith("key") for q in model["parts"])
    assert checks["no_retaining_slots"]["status"] == "PASS"
    assert checks
    assert {n: c for n, c in checks.items() if c["status"] != "PASS"} == {}
    assert len([n for n in checks if n.startswith("motion_")]) == 4
    assert checks["disassembly_terminal_inventory"]["actual"] == ["end_1"]


@pytest.fixture(scope="module")
def guide_variant(nominal):
    p, _, _ = nominal
    q = replace(p, guide_up_allowance=.8)
    return q, make_model(q)


def _with_part(model, label, replacement):
    replacement.label = label
    return dict(model, parts=[replacement if part.label == label else part for part in model["parts"]])


def test_guide_change_noop_copy_and_reordered_inventory(nominal):
    p, model, _ = nominal
    copied = dict(model, parts=[copy(part) for part in reversed(model["parts"])])
    checks = check_guide_change(model, copied, p, p)
    assert all(c["status"] == "PASS" for c in checks.values())
    assert all(c["actual"]["symmetric_difference_mm3"] < .01
               for name, c in checks.items() if name != "guide_change_scope")


def test_guide_change_measures_both_translated_receivers(nominal, guide_variant):
    p, model, _ = nominal
    q, candidate = guide_variant
    assert all(c["status"] == "PASS" for c in validate_geometry(candidate, q).values())
    checks = check_guide_change(model, candidate, p, q)
    assert all(c["status"] == "PASS" for c in checks.values())
    for name in ("side_1", "side_2", "bottom"):
        assert checks["guide_change_"+name]["actual"]["symmetric_difference_mm3"] < .01
    for name in ("end_1", "end_2"):
        actual = checks["guide_change_"+name]["actual"]
        assert actual["added_mm3"] > 1
        assert actual["removed_mm3"] > 1
        assert actual["unexpected_mm3"] < .01


@pytest.mark.parametrize("defect", ["side_cut", "upper_notch", "central_lower_cut", "translated_end",
                                  "only_one_end"])
def test_guide_change_rejects_unrelated_valid_material_changes(nominal, guide_variant, defect):
    p, model, _ = nominal
    q, candidate = guide_variant
    parts = {part.label: part for part in candidate["parts"]}
    label = "side_1" if defect == "side_cut" else "end_1"
    if defect == "side_cut":
        replacement = parts[label]-Pos(100, -q.thickness/2, 250)*Box(4, q.thickness+2, 4)
    elif defect == "upper_notch":
        replacement = parts[label]-Pos(-q.thickness/2, q.width/2, q.leg_height+q.height-2)*Box(
            q.thickness+2, 4, 10)
    elif defect == "central_lower_cut":
        replacement = parts[label]-Pos(-q.thickness/2, q.width/2, q.lower_z+10)*Box(
            q.thickness+2, 4, 4)
    elif defect == "translated_end":
        replacement = parts[label].translate((.1, 0, 0))
        assert replacement.volume == pytest.approx(parts[label].volume)
    else:
        label = "end_2"
        replacement = copy(next(part for part in model["parts"] if part.label == label))
    damaged = _with_part(candidate, label, replacement)
    assert replacement.is_valid and len(replacement.solids()) == 1
    checks = check_guide_change(model, damaged, p, q)
    assert checks["guide_change_"+label]["status"] == "FAIL"
    assert checks["guide_change_"+label]["actual"]["unexpected_mm3"] > .01
    if defect == "side_cut":
        # Existing dimensional and motion acceptance does not protect arbitrary
        # material away from its probes. The baseline contract must still fail.
        assert all(c["status"] == "PASS" for c in validate_geometry(damaged, q).values())


@pytest.mark.parametrize("defect", ["missing", "duplicate", "extra", "invalid_body"])
def test_guide_change_refuses_malformed_inventory(nominal, defect):
    p, model, _ = nominal
    parts = [copy(part) for part in model["parts"]]
    if defect == "missing":
        parts.pop()
    elif defect == "duplicate":
        parts[-1].label = parts[0].label
    elif defect == "extra":
        parts.append(copy(parts[0]))
    else:
        parts[-1] = Rectangle(1, 1)
        parts[-1].label = "bottom"
    with pytest.raises(ValueError, match="five unique|single-solid"):
        check_guide_change(model, dict(model, parts=parts), p, p)


def test_guide_change_refuses_other_parameter_changes(nominal):
    p, model, _ = nominal
    with pytest.raises(ValueError, match="only guide_up_allowance"):
        check_guide_change(model, model, p, replace(p, length=p.length+1))


def test_guide_change_step_roundtrip_requires_unambiguous_labels(nominal, guide_variant, tmp_path):
    p, model, _ = nominal
    q, candidate = guide_variant
    path = tmp_path/"guide.step"
    export_step(Compound(children=[copy(part) for part in candidate["parts"]]), str(path))
    restored = import_step(str(path))
    imported = dict(candidate, parts=list(restored.children))
    labels = [part.label for part in imported["parts"]]
    if len(set(labels)) != 5:
        # Shared STEP products can lose occurrence labels. Refuse that actual
        # import instead of repairing identities by position or list order.
        with pytest.raises(ValueError, match="five unique"):
            check_guide_change(model, imported, p, q)
    else:
        assert all(c["status"] == "PASS" for c in check_guide_change(model, imported, p, q).values())


def test_guide_change_checks_individually_bound_step_parts(nominal, guide_variant, tmp_path):
    p, model, _ = nominal
    q, candidate = guide_variant
    imported_parts = []
    for part in candidate["parts"]:
        path = tmp_path/(part.label+".step")
        export_step(part, str(path))
        restored = import_step(str(path))
        # One explicit file per source label preserves the correspondence
        # without guessing which repeated product an assembly occurrence was.
        restored.label = path.stem
        imported_parts.append(restored)
    checks = check_guide_change(model, dict(candidate, parts=imported_parts), p, q)
    assert all(c["status"] == "PASS" for c in checks.values())


def test_v21_sequential_pose_is_required(nominal):
    p, model, checks = nominal
    parts = {q.label: q for q in model["parts"]}
    # Initial sidewalls catch the end corners. The
    # accepted end withdrawal must use the endpoint of the preceding lift.
    hits = motion_collision(parts, ["end_2"], ["side_1", "side_2"], (p.tab_reach+10, 0, 0))
    assert hits
    assert checks["v_restrains_end"]["status"] == "PASS"
    end_motion = next(m for m in model["motions"] if m["moving"] == ["end_2"])
    assert checks["motion_"+end_motion["name"]]["actual"]["collision_witnesses"] == []


@pytest.mark.parametrize("changes", [{"thickness": 2}, {"thickness": 4},
                                     {"length": 600, "width": 350}])
def test_v21_supported_variants(changes):
    p = replace(Params(), **changes)
    checks = validate_geometry(make_model(p), p)
    assert {n: c for n, c in checks.items() if c["status"] != "PASS"} == {}


def _rect(x0, x1, y0, y1):
    return Pos((x0+x1)/2, (y0+y1)/2)*Rectangle(x1-x0, y1-y0)


def _replace_profile(model, p, name, profile):
    """Keep corrupted planar and assembled CAD consistent, without mocks."""
    result = dict(model, profiles=dict(model["profiles"], **{name: profile}))
    flat = extrude(profile, amount=p.thickness)
    if name == "side":
        plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        shapes = {"side_1": plane*flat, "side_2": Pos(0, p.width+p.thickness, 0)*(plane*flat)}
    else:
        plane = Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
        shapes = {"end_1": Pos(-p.thickness, 0, 0)*(plane*flat),
                  "end_2": Pos(p.length, 0, 0)*(plane*flat)}
    result["parts"] = []
    for old in model["parts"]:
        q = shapes.get(old.label, old)
        q.label = old.label
        result["parts"].append(q)
    return result


@pytest.mark.parametrize("defect", ["missing_v", "wrong_slope"])
def test_v21_detects_real_v_geometry_defects(nominal, defect):
    p, model, _ = nominal
    profile = model["profiles"]["side"]
    base = p.upper_z-p.seat_drop
    for center in (-p.thickness/2, p.length+p.thickness/2):
        half = (p.thickness+.6)/2
        profile += _rect(center-half-.01, center+half+.01, base,
                         base+p.wedge_run_height+.1*p.thickness+.01)
        if defect == "wrong_slope":
            # A native trapezoidal notch with 45-degree flanks, despite the
            # parameter still declaring 40 degrees. Validator must read CAD.
            h = p.wedge_run_height
            profile -= Polygon((center-half, base-.01), (center+half, base-.01),
                               (center+half-h, base+h), (center-half+h, base+h), align=None)
    checks = validate_geometry(_replace_profile(model, p, "side", profile), p)
    assert checks["upper_v_geometry"]["status"] == "FAIL"
    assert checks["assembled_no_interference"]["status"] == "FAIL"


def test_v21_insufficient_lower_roof_blocks_release(nominal):
    p, model, _ = nominal
    end = model["profiles"]["end"]
    for center in (-p.thickness/2, p.width+p.thickness/2):
        half = (p.thickness+p.clearance)/2
        end += _rect(center-half-.01, center+half+.01,
                     p.lower_z+20+.2, p.lower_z+20+p.guide_up_allowance+.01)
    checks = validate_geometry(_replace_profile(model, p, "end", end), p)
    assert checks["lower_guide_z_up"]["status"] == "FAIL"
    lift = next(m for m in model["motions"] if m["delta"][2] > 0
                and set(m["moving"]) == {"side_1", "side_2"})
    assert checks["motion_"+lift["name"]]["status"] == "FAIL"


def test_run_binds_only_current_artifacts(tmp_path):
    stale = {"assembly_iso.png": b"old PNG", "old.pdf": b"old PDF"}
    for name, content in stale.items():
        (tmp_path / name).write_bytes(content)
    assert run(output_dir=tmp_path) == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    expected = {"assembly.step", "side.dxf", "end.dxf", "bottom.dxf", "layout.svg",
                "bom.csv", "bom.json", "instructions.md", "manufacturing.md",
                "release_notes.md", "assembly_sequence.svg"}
    assert set(report["artifacts"]["sha256"]) == expected
    for name in expected:
        assert report["artifacts"]["sha256"][name] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    for name, content in stale.items():
        assert (tmp_path / name).read_bytes() == content
    root = Path(__file__).resolve().parents[3]
    assert report["dependency_source_sha256"]["requirements.txt"] == hashlib.sha256(
        (root / "requirements.txt").read_bytes()).hexdigest()
    assert report["checks"]["viewer_images"]["status"] == "NOT_CHECKED"
    from models.mangal_v21.documentation import build
    with pytest.raises(RuntimeError, match="Current screenshots"):
        build(tmp_path)


@pytest.mark.parametrize("status,listed,hashed", [
    ("NOT_CHECKED", True, True), ("PASS", False, True), ("PASS", True, False)])
def test_documentation_requires_current_screenshot_binding(tmp_path, status, listed, hashed):
    from models.mangal_v21.documentation import build
    names = ["assembly_iso.png", "assembly_top.png", "layout.png"]
    report = {"release": "2.1", "checks": {"viewer_images": {"status": status}},
              "artifacts": {"screenshots": names if listed else [],
                            "sha256": dict.fromkeys(names, "unused") if hashed else {}}}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Current screenshots"):
        build(tmp_path)
