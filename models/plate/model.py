"""Parametric plate; all dimensions are in millimetres."""

WIDTH = 100.0  # X; change to 120 or use --width 120
HEIGHT = 60.0  # Y
THICKNESS = 8.0  # Z
HOLE_DIAMETER = 12.0

import argparse
from contextlib import chdir
import json
import math
from pathlib import Path
import sys

from build123d import Box, Cylinder, export_step, export_stl, import_step, import_stl

if __package__:
    from .validation import CHECK_NAMES, check_plate
else:
    from validation import CHECK_NAMES, check_plate

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "plate"


def make_plate(width=WIDTH, height=HEIGHT, thickness=THICKNESS,
               hole_diameter=HOLE_DIAMETER):
    if min(width, height, thickness, hole_diameter) <= 0:
        raise ValueError("Dimensions must be positive")
    if hole_diameter >= min(width, height):
        raise ValueError("Hole must fit inside the plate")
    # Both primitives are centred on the origin. The bore spans all of Z.
    plate = Box(width, height, thickness) - Cylinder(hole_diameter / 2, thickness)
    if not plate.is_valid or len(plate.solids()) != 1:
        raise RuntimeError("Construction did not produce one valid solid")
    expected_volume = (width * height - math.pi * (hole_diameter / 2) ** 2) * thickness
    if not math.isclose(plate.volume, expected_volume, rel_tol=1e-9):
        raise RuntimeError("Unexpected plate volume")
    return plate


def export_plate(plate, output_dir, name):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = (output_dir / f"{name}.step", output_dir / f"{name}.stl")
    # OCCT's Windows STL writer fails on Unicode absolute paths. Passing
    # an ASCII basename from the destination directory keeps native export.
    with chdir(output_dir):
        for exporter, path in zip((export_step, export_stl), paths):
            if not exporter(plate, path.name) or path.stat().st_size == 0:
                raise RuntimeError(f"Export failed: {path}")
    return paths


def run_plate(width=WIDTH, output_dir=OUTPUT_DIR, *, expected=None,
              show_model=False, screenshots=False):
    """One plate run: report, measured checks, exports and optional native views.

    Exit codes: 0 required checks passed, 1 engineering mismatch, 2 execution error.
    `expected` is separate intent, useful for testing an intentionally wrong target.
    """
    parameters = dict(width=width, height=HEIGHT, thickness=THICKNESS,
                      hole_diameter=HOLE_DIAMETER)
    expected = dict(parameters) if expected is None else dict(expected)
    output_dir = Path(output_dir).resolve()
    report = {"model": "plate", "units": {"length": "mm", "volume": "mm^3"},
              "parameters": parameters, "expected_parameters": expected,
              "actual": None, "step_actual": None, "checks": {}, "errors": [],
              "artifacts": {}, "status": "NOT_CHECKED"}
    checks = report["checks"]
    required = ["build", *CHECK_NAMES, "step_export", "stl_export", "step_import",
                *(f"step_{name}" for name in CHECK_NAMES), "stl_import_bounds"]
    for name in [*required, "viewer", "image_top", "image_side", "image_iso", "visual_review"]:
        checks[name] = {"status": "NOT_CHECKED", "reason": "Stage has not run"}
    checks["visual_review"]["reason"] = "Image capture is not visual acceptance; inspect PNGs separately"
    stage = "build"
    try:
        nonfinite = False
        for values in (parameters, expected):
            for key, value in values.items():
                if isinstance(value, float) and not math.isfinite(value):
                    values[key] = repr(value)  # Preserve invalid input in strict JSON.
                    nonfinite = True
        if nonfinite:
            raise ValueError("Parameters and expected dimensions must be finite")
        plate = make_plate(width=width)
        checks[stage] = {"status": "PASS"}
        stage = "geometry"
        report["actual"], measured = check_plate(plate, expected)
        checks.update(measured)
        stage = "export"
        # Keep the established Unicode-safe native export helper unchanged.
        paths = export_plate(plate, output_dir, f"plate_{width:g}")
        for key, path in zip(("step", "stl"), paths):
            checks[f"{key}_export"] = {"status": "PASS", "bytes": path.stat().st_size}
            report["artifacts"][key] = str(path)
        stage = "step_import"
        imported = import_step(str(paths[0]))
        checks[stage] = {"status": "PASS"}
        stage = "step_geometry"
        report["step_actual"], measured = check_plate(imported, expected)
        checks.update({f"step_{key}": value for key, value in measured.items()})
        stage = "stl_import_bounds"
        with chdir(output_dir):
            size = import_stl(paths[1].name).bounding_box().size
        dimensions = [size.X, size.Y, size.Z]
        target = [expected[key] for key in ("width", "height", "thickness")]
        checks[stage] = {"status": "PASS" if all(math.isclose(a, b, rel_tol=0, abs_tol=1e-5)
                                                for a, b in zip(dimensions, target)) else "FAIL",
                         "actual": dimensions, "expected": target, "tolerance": {"absolute_mm": 1e-5}}
    except Exception as exc:
        # Exception is technical evidence; unevaluated geometry remains NOT_CHECKED.
        checks[stage] = {"status": "FAIL", "kind": "technical", "reason": f"{type(exc).__name__}: {exc}"}
        report["errors"].append({"kind": "technical", "stage": stage,
                                 "message": f"{type(exc).__name__}: {exc}"})

    if (show_model or screenshots) and report["actual"] is not None:
        try:
            from ocp_vscode import Camera, get_port, save_screenshot, show, status
            port = get_port()
            if port is None:
                raise RuntimeError("Viewer is not running: use OCP CAD Viewer: Open viewer in VS Code")
            show(plate, port=port, names=[f"Plate {width:g} mm"], reset_camera=Camera.ISO)
            viewer_status = status(port=port)
            if not viewer_status or "states" not in viewer_status:
                raise RuntimeError("Viewer did not return live scene status")
            checks["viewer"] = {"status": "PASS", "port": port,
                                "reason": "Viewer returned scene status; not visual acceptance"}
            if screenshots:
                from PIL import Image
                for view, camera in (("top", Camera.TOP), ("side", Camera.RIGHT), ("iso", Camera.ISO)):
                    stage = f"image_{view}"
                    path = output_dir / f"{view}.png"
                    # Remove stale images before requesting a fresh native screenshot.
                    path.unlink(missing_ok=True)
                    show(plate, port=port, names=[f"Plate {width:g} mm"], reset_camera=camera, ortho=True)
                    save_screenshot(str(path), port=port, timeout_s=5)
                    with Image.open(path) as png:
                        if png.format != "PNG" or min(png.size) <= 0:
                            raise RuntimeError("Viewer did not create a valid PNG")
                        png.verify()
                    checks[stage] = {"status": "PASS", "reason": "Fresh PNG captured; visual review is separate"}
                    report["artifacts"][stage] = str(path)
        except Exception as exc:
            report["errors"].append({"kind": "technical", "stage": "visual_feedback",
                                     "message": f"{type(exc).__name__}: {exc}"})
            for name in ("viewer", "image_top", "image_side", "image_iso"):
                if checks[name]["status"] == "NOT_CHECKED":
                    checks[name]["reason"] = f"{type(exc).__name__}: {exc}"
    else:
        for name in ("viewer", "image_top", "image_side", "image_iso"):
            checks[name]["reason"] = "Not requested or model unavailable"

    for name, check in checks.items():
        if check["status"] == "FAIL" and check.get("kind") != "technical":
            report["errors"].append({"kind": "engineering", "check": name,
                                     "message": "Measured geometry does not match expected parameters"})
    technical = any(error["kind"] == "technical" for error in report["errors"])
    engineering = any(error["kind"] == "engineering" for error in report["errors"])
    required_pass = all(checks[name]["status"] == "PASS" for name in required)
    report["engineering_status"] = "FAIL" if engineering else ("PASS" if required_pass else "NOT_CHECKED")
    report["execution_status"] = "FAIL" if technical else "PASS"
    report["status"] = "FAIL" if technical or engineering else ("PASS" if required_pass else "NOT_CHECKED")
    exit_code = 2 if technical or not required_pass and not engineering else (1 if engineering else 0)
    report["exit_code"] = exit_code
    path = output_dir / "report.json"
    report["artifacts"]["report"] = str(path)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"Technical error writing report: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"Report: {path}; status={report['status']}; exit_code={exit_code}")
    if report["actual"]:
        print(f"Dimensions: {report['actual']['dimensions_mm']} mm; volume: {report['actual']['volume_mm3']:.6f} mm^3")
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=float, default=WIDTH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--show", action="store_true", help="Send to the VS Code OCP CAD Viewer")
    parser.add_argument("--screenshots", action="store_true", help="Capture top/right/iso PNGs using the running viewer")
    args = parser.parse_args()
    return run_plate(args.width, args.output_dir, show_model=args.show, screenshots=args.screenshots)


if __name__ == "__main__":
    raise SystemExit(main())
