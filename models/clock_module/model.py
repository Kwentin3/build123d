"""TFA 60.3065.02 visual purchased component and clock-family assemblies.

Millimetres; +Y up, +Z rear; mounting shoulder z=0. Only the manufacturer's
90x36 and installation 77x22 envelopes are dimensional evidence. Dial/bezel
details and the 14+22 depth split are visualization conventions, not OEM CAD.
"""

BEZEL_INNER_DIAMETER = 82.0  # visual convention, no OEM dimension
DIAL_DIAMETER = 81.8
DIAL_RADIUS = 32.0
FRONT_DEPTH = 14.0  # 36-22; assumed shoulder position for illustration
DIAL_Z = -11.6
HAND_TIME = (10, 10, 30)

import argparse
from contextlib import chdir
from html import escape
import json
from math import cos, radians, sin
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from build123d import (Box, Color, Compound, Cylinder, ExportSVG, Pos, Rot,
                      Text, export_step, extrude, import_step)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.clock_family.interface import (BEZEL_DIAMETER, INSTALL_DEPTH,
                                          INSTALL_DIAMETER, OVERALL_DEPTH)
from models.clock_family.model import digest, make_family, symmetric_difference, volume

OUTPUT = ROOT / "output/clock_module"
COLORS = {"rear_envelope": "#444b50", "bezel": "#bfc6cb", "dial": "#fffdf5",
          "dial_graphics": "#20262b", "hour_hand": "#20262b",
          "minute_hand": "#20262b", "second_hand": "#b99c57", "hub": "#b99c57"}
TITLES = {"desk": "Настольные часы", "wall": "Настенные часы",
          "portable": "Переносные часы"}


def cylinder(diameter, z0, z1):
    return Pos(0, 0, (z0 + z1) / 2) * Cylinder(diameter / 2, z1 - z0)


def hand(length, width, angle, z):
    # Front is viewed from -Z. Clockwise screen angles require +world-Z rotation.
    return Rot(0, 0, angle) * Pos(0, length / 2 - 2, z) * Box(width, length + 4, .22)


def make_module():
    rear = cylinder(INSTALL_DIAMETER, 0, INSTALL_DEPTH)
    bezel = cylinder(BEZEL_DIAMETER, -FRONT_DEPTH, 0)
    bezel -= cylinder(BEZEL_INNER_DIAMETER, -FRONT_DEPTH - 1, -11.4)
    dial = cylinder(DIAL_DIAMETER, DIAL_Z, -11.4)
    marks = []
    for hour in range(1, 13):
        a = radians(hour * 30)
        x, y = -DIAL_RADIUS * sin(a), DIAL_RADIUS * cos(a)
        if hour % 3 == 0:
            # Text faces the camera at -Z, rather than its mirrored back face.
            marks.append(Pos(x, y, DIAL_Z - .03) * Rot(0, 180, 0) *
                         extrude(Text(str(hour), font_size=9, font="Arial"), amount=.06))
        else:
            marks.append(Rot(0, 0, hour * 30) * Pos(0, 34, DIAL_Z - .06) * Box(.8, 5, .08))
    for tick in range(60):
        marks.append(Rot(0, 0, tick * 6) * Pos(0, 39.2, DIAL_Z - .06) * Box(.22, 1, .08))
    h, m, s = HAND_TIME
    parts = dict(rear_envelope=rear, bezel=bezel, dial=dial,
                 dial_graphics=Compound(children=marks),
                 hour_hand=hand(23, 2.1, h * 30 + m / 2, -12.05),
                 minute_hand=hand(32, 1.45, m * 6, -12.35),
                 second_hand=hand(35, .42, s * 6, -12.65),
                 hub=cylinder(4, -13, -12.7))
    for label, part in parts.items():
        part.label = label
        part.color = Color(COLORS[label])
    return parts


def source_bindings():
    files = [*Path(__file__).parent.glob("*.py"), *Path(__file__).parent.glob("*.md"),
             ROOT / "models/clock_family/model.py", ROOT / "models/clock_family/interface.py",
             ROOT / "models/clock_family/rear_joint.py",
             ROOT / "requirements.txt"]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}


def validate_module(parts):
    shape = Compound(children=list(parts.values()))
    b = shape.bounding_box()
    expected = (-45, -45, -14, 45, 45, 22)
    actual = (*b.min, *b.max)
    checks = {"published_outer_envelope": dict(
        status="PASS" if max(abs(a-e) for a, e in zip(actual, expected)) < 1e-5 else "FAIL",
        measured_mm=list(actual), expected_mm=list(expected)),
        "valid_bodies": dict(status="PASS" if all(p.is_valid for p in parts.values()) else "FAIL"),
        "oem_profile_and_shoulder": dict(status="NOT_CHECKED", reason=
            "No OEM detail drawing: 14+22 split, bezel, dial graphics and hands are visual conventions."),
        "physical_retention": dict(status="NOT_CHECKED", reason=
            "OEM mounting ring, threads, tolerances, lens and internal mechanism are not reproduced.")}
    rear = parts["rear_envelope"]
    target = cylinder(77, 0, 22)
    delta = symmetric_difference(rear, target)
    checks["published_installation_envelope"] = dict(
        status="PASS" if delta < 1e-5 else "FAIL", unexpected_mm3=delta)
    return checks


def export_checked(parts, path):
    shape = Compound(children=list(parts.values()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with chdir(path.parent):
        if not export_step(shape, path.name):
            raise RuntimeError(f"STEP export failed: {path}")
        restored = import_step(path.name)
    # Match each solid geometrically, without a costly Boolean of the entire
    # dial (many disconnected minute marks). The sorted key establishes an
    # independent geometric match rather than trusting STEP occurrence order.
    def key(solid):
        box = solid.bounding_box()
        return tuple(round(v, 5) for v in (*box.min, *box.max, solid.volume, solid.area,
                                          *solid.center()))
    before, after = sorted(shape.solids(), key=key), sorted(restored.solids(), key=key)
    # Full Booleans verify the mechanical solids; tiny disconnected lettering
    # and ticks are checked by their individual geometric signatures. Running
    # a Boolean for each graphic exhausts the shared Job's 2 GiB commit budget.
    delta = sum(symmetric_difference(a, b) for a, b in zip(before, after) if a.volume > 1000)
    signatures_match = len(before) == len(after) and all(key(a) == key(b) for a, b in zip(before, after))
    return dict(status="PASS" if restored.is_valid and
                signatures_match and delta < .001 else "FAIL",
                solids=len(restored.solids()), expected_solids=len(shape.solids()),
                per_solid_bounds_volume_area_centroid_match=signatures_match,
                mechanical_solid_boolean_difference_mm3=delta,
                boolean_min_volume_mm3=1000)


def export_in_child(name, out):
    """Release OCCT's Boolean/export memory between independent STEP files.

    The child inherits the managed Windows Job, process/memory limits and TTL.
    No detached process, secondary server or increased resource limit.
    """
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                             "--output-dir", str(out), "--step-only", name],
                            timeout=180, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"STEP child {name}: {result.returncode}: {result.stderr[-2000:]}")
    return json.loads((out / f"{name}-step-check.json").read_text(encoding="utf-8"))


def native_projection(parts, path, eye):
    visible, _ = Compound(children=list(parts.values())).project_to_viewport(
        eye, (0, 1, 0), look_at=(0, 0, 0))
    svg = ExportSVG(scale=1, margin=0, line_weight=.18, line_color="#243c49")
    svg.add_shape(visible)
    svg.write(path)


def embedded_svg(path, x, y, width, height):
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    root.set("x", str(x)); root.set("y", str(y))
    root.set("width", str(width)); root.set("height", str(height))
    return ET.tostring(root, encoding="unicode")


def drawing(out):
    # Native BREP projections; only the annotations and dimension lines are SVG.
    front = embedded_svg(out / "front.svg", 70, 150, 400, 400)
    side = embedded_svg(out / "side.svg", 650, 150, 160, 400)
    iso = embedded_svg(out / "isometric.svg", 980, 155, 350, 380)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="900" viewBox="0 0 1400 900">
<defs><marker id="a" markerWidth="7" markerHeight="7" refX="3" refY="3" orient="auto-start-reverse"><path d="M6 0L0 3L6 6" fill="none" stroke="#294552"/></marker></defs>
<rect width="1400" height="900" fill="white"/><g font-family="Arial,sans-serif" fill="#233e4a">
<text x="45" y="48" font-size="28">TFA 60.3065.02 — габаритный чертёж модуля</text>
<text x="45" y="82" font-size="18">Размеры в мм · покупная деталь · внешнее оформление упрощено по фото изготовителя</text>
<g font-size="20"><text x="180" y="125">Вид спереди</text><text x="675" y="125">Вид сбоку</text><text x="1040" y="125">Общий вид</text></g>
{front}{side}{iso}
<g fill="none" stroke="#294552" stroke-width="1.3">
<path d="M70 555V595M470 555V595M70 580H470"/><path d="M650 555V595M810 555V595M650 580H810"/>
<path d="M817 150H890M817 550H890M875 150V550"/>
<path d="M712.22 140V610" stroke-dasharray="7 5"/>
<path d="M712.22 620H810M712.22 605V634M810 605V634"/>
</g><g font-size="19" text-anchor="middle">
<text x="270" y="607">Ø90</text><text x="730" y="607">36</text>
<text x="908" y="355" transform="rotate(-90 908 355)">Ø90</text>
<text x="761" y="658">22*</text></g>
<path d="M810 390L937 440" fill="none" stroke="#294552"/><text x="940" y="447" font-size="19">Ø77*</text>
<text x="50" y="705" font-size="19">Подтверждено изготовителем: общий Ø90 × 36; установочный Ø77 × 22; питание 1 × AA.</text>
<text x="50" y="741" font-size="18">* Установочный цилиндр показан номинально. Положение буртика и деление глубины 14 + 22 условны.</text>
<text x="50" y="775" font-size="18">Профиль обода, циферблат и стрелки — для визуализации. Стекло, кольцо и внутренности не воспроизведены.</text>
<text x="50" y="809" font-size="18">Не является заводским чертежом: допуски и фактическая посадка требуют измерения реального модуля.</text>
<text x="50" y="858" font-size="15">Источник: tfa-dostmann.de · Analogue quartz clock 60.3065 · инструкция 60.3065.02 · 2026-11-18</text>
</g></svg>'''
    (out / "module-drawing.svg").write_text(svg, encoding="utf-8")
    (out / "module-drawing.html").write_text('''<!doctype html><meta charset="utf-8"><style>
@page{size:A3 landscape;margin:8mm}body{margin:0;background:white}img{width:100%;height:auto}</style>
<img src="module-drawing.svg">''', encoding="utf-8")


def capture_viewer(module, family, out):
    from ocp_vscode import Camera, get_port, save_screenshot, show
    port = get_port()
    if port is None:
        return dict(status="NOT_CHECKED", reason="Existing OCP Viewer unavailable")
    for name in ("module", *family):
        parts = dict(module) if name == "module" else {
            **{f"housing_{n}": p for n, p in family[name]["parts"].items()},
            **family[name].get("hardware", {}), **module}
        colors = [COLORS.get(n, "#4d7d91" if n == "housing_body" else
                            "#b69a70" if n == "housing_lid" else "#8e9499") for n in parts]
        show(*parts.values(), names=list(parts), colors=colors, port=port,
             reset_camera=Camera.RESET, up="Y", ortho=True,
             position=(155, 100, -285), target=(0, 0, 0), zoom=1.25,
             axes=False, axes0=False, grid=(False, False, False),
             clip_slider_0=0, clip_slider_1=0, clip_slider_2=0, clip_planes=False)
        path = out / f"{name}-assembled.png"
        path.unlink(missing_ok=True)
        save_screenshot(str(path), port=port, timeout_s=10)
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        if name != "module":
            show(*parts.values(), names=list(parts), colors=colors, port=port,
                 reset_camera=Camera.RESET, up="Y", ortho=True,
                 position=(-155, 100, 285), target=(0, 0, 0), zoom=1.15,
                 axes=False, axes0=False, grid=(False, False, False),
                 clip_slider_0=0, clip_slider_1=0, clip_slider_2=0, clip_planes=False)
            save_screenshot(str(out/f"{name}-rear.png"), port=port, timeout_s=10)
            separated = {}
            for label, part in parts.items():
                if label.startswith("wall_screw_"):
                    continue
                shift = 32 if label == "housing_lid" else 48 if label.startswith("cover_screw_") else 0
                # This is a labelled exploded illustration, not a motion proof.
                separated[label] = Pos(0, 0, shift)*part if shift else part
            separated_colors = [COLORS.get(n, "#4d7d91" if n == "housing_body" else
                                "#b69a70" if n == "housing_lid" else "#8e9499") for n in separated]
            show(*separated.values(), names=list(separated), colors=separated_colors, port=port,
                 reset_camera=Camera.RESET, up="Y", ortho=True,
                 position=(-180, 120, 285), target=(0, 0, 20), zoom=1.05,
                 axes=False, axes0=False, grid=(False, False, False),
                 clip_slider_0=0, clip_slider_1=0, clip_slider_2=0, clip_planes=False)
            save_screenshot(str(out/f"{name}-exploded.png"), port=port, timeout_s=10)
    return dict(status="PASS", reason="Current native front/rear/exploded CAD screenshots; inspect images separately")


def assembly_page(out):
    for view, title, note in (
        ("assembled", "Часы в сборе — сплошной фасад", "Модуль и крепёж показаны отдельными покупными деталями."),
        ("rear", "Крепление сзади — три корпуса", "Четыре EJOT 3×12: головки утоплены. Подвес wall — отдельные саморезы в контрольный деревянный щит."),
        ("exploded", "Задние крышки и крепёж", "Разнесённый вид поясняет детали; фактический путь снятия проверяется отдельно. Ушко остаётся на корпусе.")):
        cards = "".join(f'<section><h2>{escape(t)}</h2><img src="{n}-{view}.png">'
                        f'<p>Корпус + TFA 60.3065.02</p></section>' for n, t in TITLES.items())
        (out / f"{view}.html").write_text(f'''<!doctype html><meta charset="utf-8"><style>
@page{{size:A3 landscape;margin:8mm}}body{{font:18px Arial;background:#f2f3ef;color:#243c49;margin:25px}}
h1{{font-size:32px;margin:12px 0}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
section{{background:white;padding:14px;border-radius:10px}}h2{{font-size:22px;margin:8px 0}}
img{{width:100%;height:490px;object-fit:contain}}p{{line-height:1.45}}small{{font-size:16px}}
</style><h1>{escape(title)}</h1><p>{escape(note)}</p>
<div class="cards">{cards}</div><p>Текущая редакция корпусов с задними крышками. Циферблат и стрелки — отдельная покупная деталь.</p>
<small>Нативные снимки фактической CAD-сборки. Модуль габаритный: профиль обода и положение буртика условны.
Стекло, монтажное кольцо и точные профили резьбы не воспроизведены. FDM/PETG-посадка и прочность требуют образца.</small>''', encoding="utf-8")


def rasterize(out, browser):
    from PIL import Image
    profile = out / "chrome-profile"
    common = [str(browser), "--headless", "--disable-gpu", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions", "--disable-background-networking",
              "--hide-scrollbars", f"--user-data-dir={profile}", "--no-pdf-header-footer"]
    for name in ("module-drawing", "assembled", "rear", "exploded"):
        html = out / f"{name}.html"
        for ext in ("png", "pdf"):
            dest = out / f"{name}.{ext}"
            dest.unlink(missing_ok=True)
            option = f"--screenshot={dest}" if ext == "png" else f"--print-to-pdf={dest}"
            result = subprocess.run([*common, "--window-size=1400,900", option, html.as_uri()],
                                    capture_output=True, timeout=45)
            if result.returncode or not dest.is_file() or dest.stat().st_size < 1000:
                raise RuntimeError(f"Chrome {name}.{ext}: exit {result.returncode}")
            if ext == "png":
                with Image.open(dest) as im:
                    im.verify()
            elif not dest.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError(f"Invalid PDF: {dest}")


def run(out=OUTPUT, screenshots=False, browser=None):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(model="clock_module_visual", units="mm", checks={},
                  hash_representation="Observed runtime/export bytes; preserved in release ZIP, not Git checkout text")
    print("Export and reimport module", flush=True)
    report["checks"]["module_step_roundtrip"] = export_in_child("module", out)
    for name in TITLES:
        print(f"Export and reimport {name} assembly", flush=True)
        report["checks"][f"{name}_step_roundtrip"] = export_in_child(name, out)
    module, family = make_module(), make_family()
    report["checks"].update(validate_module(module))
    for name, model in family.items():
        parts = {f"housing_{n}": p for n, p in model["parts"].items()}
        # Compare the new module to every actual body/cap; no housing subtraction.
        def overlaps(a, b):
            aa, bb = a.bounding_box(), b.bounding_box()
            return all(min(u, v) - max(w, x) > 1e-6
                       for u, v, w, x in zip(aa.max, bb.max, aa.min, bb.min))
        intersections = (a.intersect(b) for a in parts.values() for b in module.values()
                         if overlaps(a, b))
        intersection = sum(volume(common) for common in intersections if common is not None)
        report["checks"][f"{name}_module_housing_intersection"] = dict(
            status="PASS" if intersection < 1e-5 else "FAIL", intersection_mm3=intersection,
            scope="Nominal illustrative module only; OEM ring/lens/hardware not modeled")
    for name, eye in (("front", (0, 0, -200)), ("side", (-200, 0, 0)),
                      ("isometric", (155, 100, -285))):
        print(f"Native projection: {name}", flush=True)
        native_projection(module, out / f"{name}.svg", eye)
    drawing(out)
    if screenshots:
        print("Existing OCP Viewer captures", flush=True)
        report["checks"]["ocp_viewer"] = capture_viewer(module, family, out)
        if report["checks"]["ocp_viewer"]["status"] == "PASS":
            assembly_page(out)
    if browser:
        rasterize(out, browser)
    report["source_sha256"] = source_bindings()
    report["artifact_sha256"] = {p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob("*"))
        if p.is_file() and p.name not in ("report.json", "protected.json")
        and not any(n in p.parts for n in ("chrome-profile", "reference", "verification", "pytest-tmp"))}
    report["status"] = "FAIL" if any(c["status"] == "FAIL" for c in report["checks"].values()) else "PASS"
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out / 'report.json'}: {report['status']}")
    return int(report["status"] == "FAIL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--screenshots", action="store_true")
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--step-only", choices=("module", *TITLES), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.step_only:
        out = args.output_dir.resolve()
        out.mkdir(parents=True, exist_ok=True)
        parts = make_module()
        if args.step_only != "module":
            family = make_family()[args.step_only]
            housing = family["parts"]
            parts = {**{f"housing_{n}": p for n, p in housing.items()},
                     **family.get("hardware", {}), **parts}
        name = "module.step" if args.step_only == "module" else f"{args.step_only}-assembled.step"
        result = export_checked(parts, out / name)
        (out / f"{args.step_only}-step-check.json").write_text(json.dumps(result), encoding="utf-8")
        raise SystemExit(int(result["status"] != "PASS"))
    raise SystemExit(run(args.output_dir, args.screenshots, args.browser))
