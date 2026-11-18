"""Regress the observed coarse round STL and rejection of stale acceptance."""

import json
from pathlib import Path

import pytest

from models.clock_family.experiment import verify_report
from models.clock_family.model import ROOT, digest, export_variant, make_family, source_bindings


@pytest.fixture(scope="module")
def exported_wall(tmp_path_factory):
    out = tmp_path_factory.mktemp("clock_wall_export")
    checks, restored = export_variant(make_family()["wall"], out)
    return out, checks, restored


def test_wall_stl_preserves_bounds_and_step_preserves_solid(exported_wall):
    _, checks, restored = exported_wall
    assert all(c["status"] == "PASS" for c in checks.values()), checks
    assert checks["body_stl_bounds"]["max_delta_mm"] < .02
    assert len(restored["parts"]["body"].solids()) == 1


def test_changed_step_bytes_invalidate_a_retained_pass(exported_wall, tmp_path):
    out, _, _ = exported_wall
    artifact = tmp_path / "body.step"
    artifact.write_bytes((out / "body.step").read_bytes())
    report = dict(status="PASS", source_sha256=source_bindings(),
                  dependency_source_sha256={"requirements.txt": digest(ROOT / "requirements.txt")},
                  artifacts_sha256={"body.step": digest(artifact)})
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    verify_report(tmp_path)
    artifact.write_bytes(artifact.read_bytes() + b"\nchanged\n")
    with pytest.raises(ValueError, match="Stale artifact"):
        verify_report(tmp_path)


def test_changed_source_binding_invalidates_a_retained_pass(tmp_path):
    source = source_bindings()
    source["interface.py"] = "0" * 64
    (tmp_path / "report.json").write_text(json.dumps(dict(
        status="PASS", source_sha256=source)), encoding="utf-8")
    with pytest.raises(ValueError, match="source set/hashes changed"):
        verify_report(tmp_path)
