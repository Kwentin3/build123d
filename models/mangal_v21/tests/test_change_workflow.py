"""B/C: copied V2.1 source, changed guides, collateral cut, recovery and exports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

from build123d import export_step

from models.mangal_v21.model import Params, make_model
from models.mangal_v21.validation import validate_geometry


ROOT = Path(__file__).resolve().parents[3]


def test_guide_source_copy_detect_fix_and_exports(tmp_path):
    before_params = Params()
    before = make_model(before_params)
    assert all(c["status"] == "PASS" for c in validate_geometry(before, before_params).values())
    # Preserve each actual accepted body with an explicit filename identity.
    baseline_dir = tmp_path / "accepted"
    baseline_dir.mkdir()
    baseline_hashes = {}
    for part in before["parts"]:
        path = baseline_dir / (part.label + ".step")
        export_step(part, str(path))
        baseline_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    source = ROOT / "models/mangal_v21/model.py"
    original = source.read_bytes()
    variant_root = tmp_path / "variant"
    shutil.copytree(ROOT / "models", variant_root / "models", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "requirements.txt", variant_root / "requirements.txt")
    candidate = variant_root / "models/mangal_v21/model.py"
    intended = source.read_text(encoding="utf-8").replace(
        "guide_up_allowance: float = .7", "guide_up_allowance: float = .8")
    reports = []
    # An extra cut in the side is valid and away from all original joint probes.
    broken = intended.replace("    profiles=dict(side=side", "    side-=rect(98,102,248,252)\n    profiles=dict(side=side")
    for name, text, expected_exit in (("intended", intended, 0), ("unexpected", broken, 1),
                                      ("fixed", intended, 0)):
        candidate.write_text(text, encoding="utf-8")
        module_name = "_guide_experiment_" + name
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        old_path = list(sys.path)
        try:
            spec.loader.exec_module(module)
            out = tmp_path / name
            assert module.run(output_dir=out, guide_baseline=(before, before_params)) == expected_exit
        finally:
            sys.path[:] = old_path
            sys.modules.pop(module_name, None)
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        reports.append(report)
        assert report["execution_status"] == "PASS"
        assert report["parameters"]["guide_up_allowance"] == .8
        assert report["source_sha256"]["model.py"] == hashlib.sha256(candidate.read_bytes()).hexdigest()
        unverified = {"physical_assembly", "hot_performance", "manual_release", "stability_strength",
                      "manufacturing_fit", "viewer_images", "visual_review"}
        ordinary = {n: c for n, c in report["checks"].items()
                    if not n.startswith("guide_change") and n not in unverified}
        assert all(c["status"] == "PASS" for c in ordinary.values())
        assert report["checks"]["guide_change"]["status"] == ("FAIL" if expected_exit else "PASS")
        assert report["checks"]["guide_change_side_1"]["status"] == ("FAIL" if expected_exit else "PASS")
        for part in ("end_1", "end_2", "bottom"):
            assert report["checks"]["guide_change_" + part]["status"] == "PASS"
        for artifact in ("assembly.step", "side.dxf", "end.dxf", "bottom.dxf"):
            path = out / artifact
            assert report["artifacts"]["sha256"][artifact] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert reports[0]["source_sha256"] != reports[1]["source_sha256"]
    assert reports[0]["source_sha256"] == reports[2]["source_sha256"]
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in baseline_dir.glob("*.step")} == baseline_hashes
    assert source.read_bytes() == original
