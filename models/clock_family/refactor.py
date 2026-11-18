"""Compare the rear-fastener edition with the published, frozen original STEP."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build123d import import_step
from models.clock_family.experiment import load_parts, verify_report
from models.clock_family.model import digest, source_bindings
from models.clock_family.validation import check_refactor

ARCHIVE = ROOT / "output/examples/clock_family/clock-family-prototype.zip"
ARCHIVE_SHA256 = "e6088d91f393575a3bf67a8853124487b9f378baf79acc77d9739dc8ca98d9db"
FROZEN_SHA256 = {
    "desk/body.step": "95259ab9f90a65c7832bffe826d3db154f413064fedda26e3e8345436ee05050",
    "wall/body.step": "9225ae33dd7ea77f463118da836852e269ca4860751d1542f0031c4eaffb4663",
    "portable/body.step": "ab7f16b687d6e813992004afe4f0494a465997befd1191146baabe6f5f45ae7c",
    "portable/lid.step": "1861f153ae84f3b3979c998d48309b6933c36301a1b5339c6afaa5be39dda836",
}


def load_frozen():
    """Read exact accepted bytes; never reconstruct old geometry from new code."""
    if digest(ARCHIVE) != ARCHIVE_SHA256:
        raise ValueError("Published historical archive changed")
    parts = {name: {} for name in ("desk", "wall", "portable")}
    with ZipFile(ARCHIVE) as archive, TemporaryDirectory(prefix="clock-frozen-") as tmp:
        for relative, expected in FROZEN_SHA256.items():
            data = archive.read("output/clock_family/baseline/" + relative)
            if sha256(data).hexdigest() != expected:
                raise ValueError(f"Frozen STEP changed: {relative}")
            name, filename = relative.split("/")
            path = Path(tmp) / f"{name}-{filename}"
            path.write_bytes(data)
            shape = import_step(str(path))
            shape.label = Path(filename).stem
            parts[name][shape.label] = shape
    return parts


def run(candidate, report_path):
    candidate, report_path = Path(candidate).resolve(), Path(report_path).resolve()
    verify_report(candidate)
    before = load_frozen()
    after = load_parts(candidate, before)
    checks = {name: check_refactor(before[name], after[name], name) for name in before}
    report = dict(
        status="PASS" if all(c["status"] == "PASS" for group in checks.values()
                             for c in group.values()) else "FAIL",
        checks=checks,
        historical_git_commit="0c365701b29654990fda00f66cb57ac102d5a70c",
        historical_archive_sha256=ARCHIVE_SHA256,
        historical_step_sha256=FROZEN_SHA256,
        candidate_report_sha256=digest(candidate / "report.json"),
        candidate_step_sha256={f"{n}/{k}.step": digest(candidate / n / f"{k}.step")
                               for n, parts in after.items() for k in parts},
        source_sha256=source_bindings(),
        hash_representation="Exact runtime/archive bytes; no newline normalization",
        scope="Protected old body versus frozen STEP; new/replaced lids independently checked in candidate report",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report_path}: {report['status']}")
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.candidate, args.report))
