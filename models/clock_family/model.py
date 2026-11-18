"""Three prototype clock housings. All dimensions mm; X right, Y up, Z rear.

Run from the repository root with .venv/Scripts/python.exe.
The purchased module is an installation envelope, not a detailed OEM CAD model.
"""

DESK_DIAMETER = 108.0
DESK_DEPTH = 28.0
FOOT_WIDTH = 144.0
FOOT_HEIGHT = 12.0
FOOT_DEPTH = 108.0
WALL_DIAMETER = 140.0
WALL_DEPTH = 30.0
PORTABLE_WIDTH = 110.0
PORTABLE_HEIGHT = 116.0
PORTABLE_DEPTH = 28.0
CORNER_RADIUS = 10.0
REAR_RELIEF = 98.0

import argparse
from contextlib import chdir
import hashlib
import json
from pathlib import Path
import platform
import sys

from build123d import (Box, Compound, Cylinder, Pos, RectangleRounded,
                      export_step, export_stl, extrude, import_step, import_stl)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.clock_family.interface import (
    DIAMETRAL_ALLOWANCE, INSTALL_DEPTH, installation_envelope, socket_cut)
from models.clock_family.rear_joint import (
    COVER_THICKNESS as LID_THICKNESS, add_rear_joint, cover_hardware, coupon,
    wall_hardware, wall_keyholes)

OUTPUT_DIR = ROOT / "output" / "clock_family"


def cylinder_at(diameter, z0, z1, x=0, y=0):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(diameter / 2, z1 - z0)


def make_family(clearance=DIAMETRAL_ALLOWANCE):
    """Small explicit family, with one shared cut; no universal enclosure layer."""
    socket = socket_cut(clearance)
    desk = cylinder_at(DESK_DIAMETER, 0, DESK_DEPTH)
    desk += Pos(0, -58, 10) * Box(FOOT_WIDTH, FOOT_HEIGHT, FOOT_DEPTH)
    desk = desk - socket - cylinder_at(REAR_RELIEF, INSTALL_DEPTH, DESK_DEPTH + 1)
    desk_lid = cylinder_at(DESK_DIAMETER, DESK_DEPTH, DESK_DEPTH+LID_THICKNESS)
    # The retained foot extends behind the case. Keep its upper face clear.
    desk_lid -= Pos(0, -101.8, DESK_DEPTH+LID_THICKNESS/2) * Box(200, 100, 20)
    desk, desk_lid = add_rear_joint(desk, desk_lid, DESK_DEPTH)

    wall = cylinder_at(WALL_DIAMETER, 0, WALL_DEPTH)
    wall = wall - socket - cylinder_at(118, INSTALL_DEPTH, WALL_DEPTH + 1)
    wall_lid = cylinder_at(WALL_DIAMETER, WALL_DEPTH, WALL_DEPTH+LID_THICKNESS)
    wall, wall_lid = add_rear_joint(wall, wall_lid, WALL_DEPTH)
    wall_lid = wall_keyholes(wall_lid, WALL_DEPTH)

    outline = RectangleRounded(PORTABLE_WIDTH, PORTABLE_HEIGHT, CORNER_RADIUS)
    portable = extrude(outline, amount=PORTABLE_DEPTH)
    portable = portable - socket - cylinder_at(REAR_RELIEF, INSTALL_DEPTH, PORTABLE_DEPTH + 1)
    portable += cylinder_at(20, 25, 33, y=64)
    portable += Pos(0, 55, 26.5) * Box(14, 10, 13)
    portable -= cylinder_at(5, 24, 34, y=64)
    lid = Pos(0, 0, PORTABLE_DEPTH) * extrude(outline, amount=LID_THICKNESS)
    # An open notch lets the lid leave while the reinforced ear stays on body.
    lid -= Pos(0, 74.75, 30.5) * Box(17, 50, 12)
    portable, lid = add_rear_joint(portable, lid, PORTABLE_DEPTH)

    result = {}
    for name, parts in (("desk", {"body": desk, "lid": desk_lid}),
                        ("wall", {"body": wall, "lid": wall_lid}),
                        ("portable", {"body": portable, "lid": lid})):
        for label, shape in parts.items():
            shape.label = label
        hardware = cover_hardware(WALL_DEPTH if name == "wall" else PORTABLE_DEPTH)
        if name == "wall":
            hardware.update(wall_hardware(WALL_DEPTH))
        result[name] = dict(name=name, parts=parts, hardware=hardware)
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def volume(shape):
    return sum(s.volume for s in shape.solids())


def symmetric_difference(a, b):
    return volume(a - b) + volume(b - a)


def source_bindings():
    own = Path(__file__).parent
    return {p.name: digest(p) for p in sorted(own.iterdir())
            if p.suffix in (".py", ".md")}


def export_variant(model, out):
    """Per-part round trips avoid relying on STEP occurrence ordering/labels."""
    out.mkdir(parents=True, exist_ok=True)
    checks, restored = {}, {}
    with chdir(out):
        for name, part in model["parts"].items():
            for suffix, exporter in (("step", export_step), ("stl", export_stl)):
                path = Path(f"{name}.{suffix}")
                options = dict(tolerance=.001, angular_tolerance=.02) if suffix == "stl" else {}
                if not exporter(part, str(path), **options) or not path.stat().st_size:
                    raise RuntimeError(f"Empty/failed export: {out / path}")
            step = import_step(f"{name}.step")
            step.label = name
            restored[name] = step
            unexpected = symmetric_difference(part, step)
            checks[f"{name}_step_roundtrip"] = {
                "status": "PASS" if step.is_valid and len(step.solids()) == 1 and unexpected < 1e-3 else "FAIL",
                "unexpected_mm3": unexpected, "tolerance_mm3": 1e-3}
            stl = import_stl(f"{name}.stl")  # native Unicode-path workaround
            a, b = part.bounding_box(), stl.bounding_box()
            delta = max(abs(x - y) for x, y in zip((*a.min, *a.max), (*b.min, *b.max)))
            checks[f"{name}_stl_bounds"] = {"status": "PASS" if delta < .02 else "FAIL",
                                           "max_delta_mm": delta, "tolerance_mm": .02}
        assembly = Compound(children=list(model["parts"].values()))
        if not export_step(assembly, "housing.step"):
            raise RuntimeError("Housing STEP export failed")
        imported = import_step("housing.step")
        delta = symmetric_difference(assembly, imported)
        checks["assembly_step_roundtrip"] = {
            "status": "PASS" if imported.is_valid and len(imported.solids()) == len(model["parts"]) and delta < 1e-3 else "FAIL",
            "solid_count": len(imported.solids()), "unexpected_mm3": delta}
        # Explicit envelope is in a separate non-printing STEP.
        export_step(Compound(children=[*model["parts"].values(), installation_envelope()]),
                    "with_installation_envelope.step")
        if model.get("hardware"):
            for filename, shapes in (
                    ("hardware.step", list(model["hardware"].values())),
                    ("with_hardware.step", [*model["parts"].values(), *model["hardware"].values()])):
                supplied = Compound(children=shapes)
                if not export_step(supplied, filename):
                    raise RuntimeError(f"Non-printing assembly export failed: {filename}")
                returned = import_step(filename)
                def key(solid):
                    bb = solid.bounding_box()
                    return tuple(round(v, 5) for v in (*bb.min, *bb.max, solid.volume, solid.area))
                a, b = sorted(supplied.solids(), key=key), sorted(returned.solids(), key=key)
                equal = len(a) == len(b) and all(key(x) == key(y) for x, y in zip(a, b))
                checks[filename+"_roundtrip"] = dict(status="PASS" if returned.is_valid and equal else "FAIL",
                    solid_count=len(b), expected_solids=len(a),
                    scope="Per-solid bounds/volume/area; printed parts separately checked by Boolean difference")
    return checks, dict(name=model["name"], parts=restored)


def capture_viewer(family, out):
    """Optional existing OCP Viewer; never start an unmanaged local service."""
    from ocp_vscode import Camera, get_port, save_screenshot, show
    port = get_port()
    if port is None:
        return {"status": "NOT_CHECKED", "reason": "No running OCP Viewer; use native SVG/PNG projections"}
    for name, model in family.items():
        path = out / name / "viewer.png"
        path.unlink(missing_ok=True)
        options = dict(names=list(model["parts"]), port=port, up="Y", ortho=True,
                       position=(180, 120, -240), target=(0, 0, 0),
                       colors=["#648a9b" if label == "body" else "#c59b62" for label in model["parts"]],
                       axes=False, axes0=False, grid=(False, False, False), zoom=1,
                       clip_slider_0=0, clip_slider_1=0, clip_slider_2=0, clip_planes=False)
        show(*model["parts"].values(), reset_camera=Camera.RESET, **options)
        save_screenshot(str(path), port=port, timeout_s=5)
        from PIL import Image
        with Image.open(path) as png:
            png.verify()
    return {"status": "PASS", "reason": "Native OCP screenshots captured; visual review separate"}


def write_report(report, out):
    report["hash_representation"] = "Observed runtime/export file bytes; preserved in release ZIP, not Git checkout text"
    report["source_sha256"] = source_bindings()
    report["dependency_source_sha256"] = {"requirements.txt": digest(ROOT / "requirements.txt")}
    report["artifacts_sha256"] = {p.relative_to(out).as_posix(): digest(p)
                                  for p in sorted(out.rglob("*")) if p.is_file()
                                  and p.name not in ("report.json", "change-report.json")}
    statuses = [c["status"] for c in report["checks"].values()]
    report["cad_status"] = "FAIL" if "FAIL" in statuses else "PASS"
    report["execution_status"] = "FAIL" if report["errors"] else "PASS"
    report["status"] = "FAIL" if report["errors"] or report["cad_status"] == "FAIL" else "PASS"
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(output_dir=OUTPUT_DIR, clearance=DIAMETRAL_ALLOWANCE, screenshots=False, drawings=False):
    from models.clock_family.validation import validate_variant
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(model="clock_family", units="mm", allowance_mm=clearance,
                  python=platform.python_version(), checks={}, errors=[], variants={})
    try:
        family = make_family(clearance)
        for name, model in family.items():
            checks = validate_variant(model, clearance)
            roundtrip, restored = export_variant(model, out / name)
            checks.update(roundtrip)
            checks.update({f"step_{k}": v for k, v in validate_variant(restored, clearance).items()})
            report["checks"].update({f"{name}/{k}": v for k, v in checks.items()})
            report["variants"][name] = {label: dict(volume_mm3=volume(s),
                bounds_mm=[list(s.bounding_box().min), list(s.bounding_box().max)])
                for label, s in model["parts"].items()}
        with chdir(out):
            for label, part in coupon().items():
                stem = f"pilot-coupon-{label}"
                if not export_step(part, stem+".step") or not export_stl(
                        part, stem+".stl", tolerance=.001, angular_tolerance=.02):
                    raise RuntimeError("Pilot coupon export failed")
                restored_coupon = import_step(stem+".step")
                delta = symmetric_difference(part, restored_coupon)
                report["checks"][f"pilot_coupon_{label}_step"] = dict(
                    status="PASS" if restored_coupon.is_valid and delta < 1e-3 else "FAIL", unexpected_mm3=delta)
        if screenshots:
            report["checks"]["ocp_viewer"] = capture_viewer(family, out)
        if drawings:
            from models.clock_family.drawings import export_drawings
            export_drawings(family, out, clearance)
            report["checks"]["native_projections"] = {"status": "PASS", "reason": "OCCT HLR exported as SVG; inspect raster previews separately"}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        report["errors"].append(dict(kind="technical", message=f"{type(exc).__name__}: {exc}"))
    write_report(report, out)
    print(f"{out / 'report.json'}: {report['status']}")
    return 2 if report["errors"] else (1 if report["cad_status"] == "FAIL" else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--clearance", type=float, default=DIAMETRAL_ALLOWANCE)
    parser.add_argument("--screenshots", action="store_true")
    parser.add_argument("--drawings", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.output_dir, args.clearance, args.screenshots, args.drawings))
