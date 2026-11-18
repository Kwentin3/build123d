"""Bore-only dependent change against frozen, hash-verified exported STEP.

Baseline -> intended change -> unrelated defect FAIL -> restored PASS.
The design allowance changes; the manufacturer's dimensions do not.
"""

from pathlib import Path
import argparse
import json
import sys

from build123d import Box, Pos, import_step

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.clock_family.interface import CHANGE_ALLOWANCE, DIAMETRAL_ALLOWANCE
from models.clock_family.model import digest, make_family, run, source_bindings
from models.clock_family.validation import check_change, validate_variant


def verify_report(out):
    """Reject stale or missing bindings before using old acceptance evidence."""
    out = Path(out).resolve()
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    if report["status"] != "PASS" or report["source_sha256"] != source_bindings():
        raise ValueError("Baseline report failed or source set/hashes changed; rerun baseline")
    if not report["dependency_source_sha256"] or not report["artifacts_sha256"]:
        raise ValueError("Missing baseline bindings")
    for name, expected in report["dependency_source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Stale dependency: {name}")
    for name, expected in report["artifacts_sha256"].items():
        if digest(out / name) != expected:
            raise ValueError(f"Stale artifact: {name}")
    return report


def load_parts(out, names):
    family = {}
    for name in names:
        parts = {}
        for label in ("body", "lid"):
            path = Path(out) / name / f"{label}.step"
            if path.exists():
                parts[label] = import_step(str(path))
                parts[label].label = label  # identity comes from the bound per-part path
        family[name] = parts
    return family


def passed(checks):
    return bool(checks) and all(c["status"] == "PASS" for c in checks.values())


def experiment(baseline, out):
    baseline, out = Path(baseline).resolve(), Path(out).resolve()
    if baseline == out or baseline in out.parents or out in baseline.parents:
        raise ValueError("Baseline and variant must be separate sibling directories")
    accepted = verify_report(baseline)
    if accepted["allowance_mm"] != DIAMETRAL_ALLOWANCE:
        raise ValueError("Expected accepted 0.4 mm baseline")
    names = ("desk", "wall", "portable")
    before = load_parts(baseline, names)
    baseline_steps = {f"{n}/{label}.step": digest(baseline / n / f"{label}.step")
                      for n in names for label in before[n]}
    report = dict(status="NOT_CHECKED", checks={}, negative_cases={},
                  baseline_report_sha256=digest(baseline / "report.json"),
                  baseline_step_sha256=baseline_steps,
                  change=dict(parameter="diametral_allowance_mm", before=.4, after=1.,
                              allowed="Only enlarged coaxial body bore, z=0..22; every other part and placement protected"))
    if run(out, CHANGE_ALLOWANCE, drawings=True):
        raise RuntimeError("Dependent variant CAD/export checks failed; inspect its report.json")
    after = load_parts(out, names)
    for name in names:
        report["checks"][name] = check_change(before[name], after[name], .4, 1.)
    # An off-socket 1 mm3 internal notch must fail the change contract even if
    # the intended bore still measures correctly. Never modify accepted files.
    defective = dict(after["desk"])
    defective["body"] = defective["body"] - Pos(52, 0, 6) * Box(1, 1, 1)
    defective["body"].label = "body"
    defect_checks = check_change(before["desk"], defective, .4, 1.)
    report["negative_cases"]["unrelated_material_removed"] = {
        "expected": "FAIL", "observed": defect_checks,
        "detected": defect_checks.get("change_body", {}).get("status") == "FAIL"}
    stale_checks = validate_variant(dict(name="wall", parts=before["wall"]), 1.)
    # Ordinary functional checks must detect a forgotten update in one member.
    report["negative_cases"]["wall_kept_old_bore"] = {
        "expected": "FAIL", "observed": stale_checks,
        "detected": any(c["status"] == "FAIL" for c in stale_checks.values())}
    # Recovery uses the independently exported clean candidate, not acceptance
    # of the defective geometry or a changed requirement.
    restored_checks = check_change(before["desk"], after["desk"], .4, 1.)
    report["checks"]["recovered_desk"] = restored_checks
    report["baseline_unchanged"] = all(digest(baseline / n) == h for n, h in baseline_steps.items())
    report["status"] = "PASS" if (all(passed(c) for c in report["checks"].values()) and
        all(c["detected"] for c in report["negative_cases"].values()) and report["baseline_unchanged"]) else "FAIL"
    report["source_sha256"] = source_bindings()
    report["variant_report_sha256"] = digest(out / "report.json")
    (out / "change-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{out / 'change-report.json'}: {report['status']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "output/clock_family/baseline")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/clock_family/change")
    args = parser.parse_args()
    raise SystemExit(experiment(args.baseline, args.output_dir))
