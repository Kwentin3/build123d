"""Straight, zero-shift involute gear. Millimetres; root transition is simplified."""

TOOTH_COUNT = 24
MODULE = 2.0
PRESSURE_ANGLE_DEG = 20.0
THICKNESS = 10.0
BORE_DIAMETER = 8.0
PROFILE_SHIFT = 0.0
ADDENDUM_COEFFICIENT = 1.0
DEDENDUM_COEFFICIENT = 1.25
HELIX_ANGLE_DEG = 0.0
FLANK_POINTS = 65

import argparse
from contextlib import chdir
import json
import math
from pathlib import Path
import sys

from build123d import Axis, Cylinder, Edge, Face, Pos, Wire, export_step, export_stl, extrude, import_step

if __package__:
    from .validation import CHECK_NAMES, check_gear
else:
    from validation import CHECK_NAMES, check_gear

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "gear"

# Independent acceptance references fixed by the experiment, not by make_gear.
REFERENCE_24 = dict(teeth=24, thickness=10, bore_diameter=8, outer_diameter=52,
                    root_diameter=43, pitch_diameter=48, base_diameter=45.105245797723605,
                    pressure_angle_deg=20)
REFERENCE_30 = dict(teeth=30, thickness=10, bore_diameter=8, outer_diameter=64,
                    root_diameter=55, pitch_diameter=60, base_diameter=56.381557247154504,
                    pressure_angle_deg=20)


def make_gear(teeth=TOOTH_COUNT, module=MODULE, pressure_angle_deg=PRESSURE_ANGLE_DEG,
              thickness=THICKNESS, bore_diameter=BORE_DIAMETER,
              profile_shift=PROFILE_SHIFT, addendum=ADDENDUM_COEFFICIENT,
              dedendum=DEDENDUM_COEFFICIENT, helix_angle_deg=HELIX_ANGLE_DEG):
    if not isinstance(teeth, int) or teeth < 3:
        raise ValueError("teeth must be an integer >= 3")
    if not all(math.isfinite(v) for v in (module, pressure_angle_deg, thickness,
                                         bore_diameter, profile_shift, addendum,
                                         dedendum, helix_angle_deg)):
        raise ValueError("All dimensions must be finite")
    if min(module, thickness, bore_diameter, addendum, dedendum) <= 0:
        raise ValueError("Dimensions and height coefficients must be positive")
    if profile_shift != 0 or helix_angle_deg != 0:
        raise ValueError("This experiment supports only zero shift and straight teeth")
    if not 0 < pressure_angle_deg < 45:
        raise ValueError("pressure angle must be between 0 and 45 degrees")
    alpha = math.radians(pressure_angle_deg)
    pitch_radius = module * teeth / 2
    base_radius = pitch_radius * math.cos(alpha)
    tip_radius = pitch_radius + addendum * module
    root_radius = pitch_radius - dedendum * module
    if not bore_diameter / 2 < root_radius < base_radius < tip_radius:
        raise ValueError("This root construction requires bore < root < base < tip radii")
    base_half_angle = math.pi / (2 * teeth) + math.tan(alpha) - alpha
    t_max = math.sqrt((tip_radius / base_radius) ** 2 - 1)

    def polar(radius, angle):
        return (radius * math.cos(angle), radius * math.sin(angle), 0)

    # Classical involute x=rb(cos(t)+t*sin(t)), y=rb(sin(t)-t*cos(t)).
    # The right flank is mirrored and rotated to give pi*m/2 pitch tooth thickness.
    right = []
    for i in range(FLANK_POINTS):
        t = t_max * i / (FLANK_POINTS - 1)
        radius = base_radius * math.sqrt(1 + t * t)
        angle = base_half_angle - (t - math.atan(t))
        right.append(polar(radius, angle))
    left = [(x, -y, z) for x, y, z in right]
    tip_half_angle = math.atan2(right[-1][1], right[-1][0])
    if tip_half_angle <= 0 or 2 * base_half_angle >= 2 * math.pi / teeth:
        raise ValueError("Tooth tips or roots overlap for these parameters")
    # Involute exists only at r>=rb. Radial connectors below rb are intentional;
    # they are not a generated rack-cutter fillet or trochoidal root.
    tooth_edges = [
        Edge.make_line(polar(root_radius, -base_half_angle), left[0]),
        Edge.make_spline(left, tol=1e-8),
        Edge.make_three_point_arc(left[-1], polar(tip_radius, 0), right[-1]),
        Edge.make_spline(list(reversed(right)), tol=1e-8),
        Edge.make_line(right[0], polar(root_radius, base_half_angle)),
        Edge.make_three_point_arc(polar(root_radius, base_half_angle),
                                  polar(root_radius, math.pi / teeth),
                                  polar(root_radius, 2 * math.pi / teeth - base_half_angle)),
    ]
    outline = Wire([edge.rotate(Axis.Z, 360 * tooth / teeth)
                    for tooth in range(teeth) for edge in tooth_edges])
    gear = Pos(0, 0, -thickness / 2) * extrude(Face(outline), amount=thickness)
    return gear - Cylinder(bore_diameter / 2, thickness)


def run_gear(teeth=TOOTH_COUNT, output_dir=OUTPUT_DIR, *, expected=None,
             show_model=False, screenshots=False):
    """Use the pilot's PASS/FAIL/NOT_CHECKED and exit 0/1/2 conventions for this gear."""
    output_dir = Path(output_dir).resolve()
    reference = {24: REFERENCE_24, 30: REFERENCE_30}.get(teeth)
    expected = dict(expected if expected is not None else reference or {})
    parameters = dict(teeth=teeth, module=MODULE, pressure_angle_deg=PRESSURE_ANGLE_DEG,
                      thickness=THICKNESS, bore_diameter=BORE_DIAMETER,
                      profile_shift=PROFILE_SHIFT, addendum=ADDENDUM_COEFFICIENT,
                      dedendum=DEDENDUM_COEFFICIENT, helix_angle_deg=HELIX_ANGLE_DEG,
                      flank_points=FLANK_POINTS)
    report = dict(model="gear", units={"length": "mm", "angle": "degree", "volume": "mm^3"},
                  parameters=parameters, expected_parameters=expected, actual=None,
                  step_actual=None, checks={}, errors=[], artifacts={})
    checks = report["checks"]
    physical_checks = [name for name in CHECK_NAMES if name not in ("pitch_circle", "base_circle")]
    required = ["build", *physical_checks, "step_export", "stl_export", "step_import",
                *(f"step_{name}" for name in physical_checks)]
    for name in [*required, "pitch_circle", "base_circle", "step_pitch_circle", "step_base_circle",
                 "viewer", "image_top", "image_side", "image_iso", "visual_review",
                 "strength", "wear", "manufacturability", "mating_gear_operation"]:
        checks[name] = {"status": "NOT_CHECKED", "reason": "Not evaluated in this run"}
    checks["visual_review"]["reason"] = "Capture is not visual acceptance; inspect fresh PNGs separately"
    stage = "build"
    try:
        nonfinite = False
        for values in (parameters, expected):
            for key, value in values.items():
                if isinstance(value, float) and not math.isfinite(value):
                    values[key], nonfinite = repr(value), True
        if nonfinite or not expected:
            raise ValueError("Finite parameters and explicit experiment references are required")
        gear = make_gear(teeth=teeth)
        checks["build"] = {"status": "PASS"}
        stage = "geometry"
        report["actual"], measured = check_gear(gear, expected)
        checks.update(measured)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Established Windows Unicode workaround: native exporter sees ASCII basename.
        with chdir(output_dir):
            for kind, exporter in (("step", export_step), ("stl", export_stl)):
                stage = f"{kind}_export"
                path = output_dir / f"gear_{teeth}.{kind}"
                if not exporter(gear, path.name) or path.stat().st_size == 0:
                    raise RuntimeError(f"{kind} export failed")
                checks[stage] = {"status": "PASS", "bytes": path.stat().st_size}
                report["artifacts"][kind] = str(path)
        stage = "step_import"
        imported = import_step(report["artifacts"]["step"])
        checks[stage] = {"status": "PASS"}
        stage = "step_geometry"
        report["step_actual"], measured = check_gear(imported, expected)
        checks.update({f"step_{key}": value for key, value in measured.items()})
    except Exception as exc:
        checks[stage] = {"status": "FAIL", "kind": "technical", "reason": f"{type(exc).__name__}: {exc}"}
        report["errors"].append({"kind": "technical", "stage": stage, "message": checks[stage]["reason"]})

    if (show_model or screenshots) and report["actual"] is not None:
        try:
            from ocp_vscode import Camera, get_port, save_screenshot, show, status
            port = get_port()
            if port is None:
                raise RuntimeError("Start OCP CAD Viewer: Open viewer in VS Code")
            show(gear, port=port, names=[f"Involute gear {teeth}"], reset_camera=Camera.ISO)
            live = status(port=port)
            if not live or "states" not in live:
                raise RuntimeError("No live scene status from viewer")
            checks["viewer"] = {"status": "PASS", "port": port}
            if screenshots:
                from PIL import Image
                for view, camera in (("top", Camera.TOP), ("side", Camera.RIGHT), ("iso", Camera.ISO)):
                    path = output_dir / f"{view}.png"
                    path.unlink(missing_ok=True)
                    show(gear, port=port, names=[f"Involute gear {teeth}"], reset_camera=camera, ortho=True)
                    save_screenshot(str(path), port=port, timeout_s=5)
                    with Image.open(path) as png:
                        if png.format != "PNG" or min(png.size) <= 0:
                            raise RuntimeError("Invalid screenshot")
                        png.verify()
                    checks[f"image_{view}"] = {"status": "PASS", "reason": "Fresh PNG, not visual acceptance"}
                    report["artifacts"][f"image_{view}"] = str(path)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            report["errors"].append({"kind": "technical", "stage": "visual_feedback", "message": message})
            for name in ("viewer", "image_top", "image_side", "image_iso"):
                if checks[name]["status"] == "NOT_CHECKED":
                    checks[name]["reason"] = message
    for name, check in checks.items():
        if check["status"] == "FAIL" and check.get("kind") != "technical":
            report["errors"].append({"kind": "engineering", "check": name,
                                     "message": "Measured gear does not meet the fixed experiment reference"})
    missing = [name for name in required if checks[name]["status"] == "NOT_CHECKED"]
    if missing:
        report["errors"].append({"kind": "technical", "stage": "coverage", "message": f"Unchecked: {missing}"})
    technical = any(e["kind"] == "technical" for e in report["errors"])
    engineering = any(e["kind"] == "engineering" for e in report["errors"])
    required_pass = all(checks[name]["status"] == "PASS" for name in required)
    report["engineering_status"] = "FAIL" if engineering else "PASS" if required_pass else "NOT_CHECKED"
    report["execution_status"] = "FAIL" if technical else "PASS"
    report["status"] = "FAIL" if technical or engineering else "PASS"
    exit_code = 2 if technical else 1 if engineering else 0
    report["exit_code"] = exit_code
    report["limitations"] = [
        "Involute is a numerically interpolated B-spline; verification is sampled to 1e-4 mm.",
        "Root uses radial connectors below base circle, no generated trochoid or cutter fillet.",
        "Pitch/base circles are design references, not directly measured physical circles.",
        "No strength, wear, manufacturing or mating-gear operation calculation.",
    ]
    path = output_dir / "report.json"
    report["artifacts"]["report"] = str(path)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"Technical report error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"Report: {path}; status={report['status']}; exit_code={exit_code}")
    if report["actual"]:
        print(f"Teeth: {report['actual']['tooth_count']}; OD: {report['actual']['outer_diameter_mm']} mm")
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teeth", type=int, default=TOOTH_COUNT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--screenshots", action="store_true")
    args = parser.parse_args()
    return run_gear(args.teeth, args.output_dir, show_model=args.show, screenshots=args.screenshots)


if __name__ == "__main__":
    raise SystemExit(main())
