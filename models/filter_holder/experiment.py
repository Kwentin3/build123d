"""Reproduce the known-outcome controls after the independent review.

Not an input to that review. Never rewrites the teaching model or older releases.
"""

import argparse
from contextlib import chdir
import hashlib
import json
from pathlib import Path
import sys

from build123d import Compound, export_step, import_step

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.filter_holder.model import make_holder
from models.filter_holder.validation import review_geometry, symmetric_difference


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, z in (("as_described", 10), ("alternate_crossbar", -8)):
        parts = make_holder(z)
        dest = out / name
        dest.mkdir(parents=True, exist_ok=True)
        checks = review_geometry(parts)
        restored = {}
        with chdir(dest):
            for label, shape in parts.items():
                if not export_step(shape, f"{label}.step"):
                    raise RuntimeError(f"STEP export failed: {name}/{label}")
                restored[label] = import_step(f"{label}.step")
                delta = symmetric_difference(shape, restored[label])
                checks[f"{label}_step"] = dict(status="PASS" if restored[label].is_valid
                    and len(restored[label].solids()) == 1 and delta < 1e-3 else "FAIL",
                    symmetric_difference_mm3=delta)
            if not export_step(Compound(children=list(parts.values())), "assembly.step"):
                raise RuntimeError("Assembly export failed")
            assembly = import_step("assembly.step")
            delta = symmetric_difference(Compound(children=list(parts.values())), assembly)
            checks["assembly_step"] = dict(status="PASS" if assembly.is_valid and
                len(assembly.solids()) == 2 and delta < 1e-3 else "FAIL", symmetric_difference_mm3=delta)
        checks.update({f"step_{k}": v for k, v in review_geometry(restored).items()})
        results[name] = checks
    missing = review_geometry(make_holder(), stroke=None)
    results["unknown_service_contract"] = missing
    # This status accepts the experiment, not the intentionally obstructed design.
    accepted = (results["as_described"]["service_path"]["status"] == "FAIL"
                and results["alternate_crossbar"]["service_path"]["status"] == "PASS"
                and results["as_described"]["step_service_path"]["status"] == "FAIL"
                and results["alternate_crossbar"]["step_service_path"]["status"] == "PASS"
                and missing["service_path"]["status"] == "NOT_CHECKED"
                and all(v["status"] == "PASS" for checks in results.values()
                    for key, v in checks.items() if key.endswith("_step") or key == "valid_solids"))
    report = dict(experiment_status="PASS" if accepted else "FAIL", variants=results,
        source_sha256={p.relative_to(ROOT).as_posix(): digest(p) for p in
                       sorted(Path(__file__).parent.iterdir()) if p.suffix in (".py", ".md")},
        dependency_sha256={"requirements.txt": digest(ROOT/"requirements.txt")},
        artifact_sha256={p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob("*.step"))},
        limits="Synthetic controlled case, no physical/strength qualification and no universal detection-rate claim")
    (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:{n:v["status"] for n,v in checks.items()} for k,checks in results.items()}, indent=2))
    return int(not accepted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"output/filter_holder")
    args = parser.parse_args()
    raise SystemExit(run(args.output_dir))
