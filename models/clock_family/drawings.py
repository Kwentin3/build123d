"""Native OCCT hidden-line drawings and bounded Chrome raster previews.

The face disk is schematic: the OEM front/rear depth split is not published.
It is never exported as a printable part or used as evidence of exact fit.
"""

from html import escape
from pathlib import Path
import argparse
import json
import subprocess
import sys

from build123d import Compound, Cylinder, ExportSVG, Pos

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.clock_family.interface import INSTALL_DIAMETER

TITLES = {"desk": "Настольный · широкая опора", "wall": "Настенный · два винта",
          "portable": "Переносной · крышка и петля"}
NOTES = {
    "desk": "144 × 118 × 108 мм. Ось часов горизонтальна. Батарея и настройка доступны сзади.",
    "wall": "Ø140 × 30 мм. Два отверстия Ø4.5, межосевое 120 мм. Для обслуживания снять со стены.",
    "portable": "110 × 132 × 31 мм. Четыре M3×35 с гайками; крышку снять для обслуживания. Петля Ø5 мм."}


def projection(parts, path, eye):
    visible, _ = Compound(children=parts).project_to_viewport(eye, (0, 1, 0), look_at=(0, 0, 0))
    svg = ExportSVG(scale=2, margin=6, line_weight=.35, line_color="#244351")
    svg.add_shape(visible)
    svg.write(path)


def export_drawings(family, out, clearance):
    out = Path(out)
    # Front disk only explains which way the purchased insert faces. 14 mm is
    # a drawing convention (36-22), not an independently known bezel thickness.
    face = Pos(0, 0, -7) * Cylinder(45, 14)
    for name, model in family.items():
        dest = out / name
        dest.mkdir(parents=True, exist_ok=True)
        parts = list(model["parts"].values())
        projection([*parts, face], dest / "assembled.svg", (150, 100, -220))
        rear = [model["parts"]["body"]]
        if "lid" in model["parts"]:
            rear.append(Pos(0, 0, 36) * model["parts"]["lid"])
        projection(rear, dest / "service.svg", (-140, 100, 220))
        projection([model["parts"]["body"]], dest / "front.svg", (0, 0, -200))
        cards = "".join(f'<section><h2>{title}</h2><img src="{file}.svg"></section>'
                        for file, title in (("assembled", "С модулем: условный внешний диск"),
                                            ("service", "Сзади: доступ / снятая крышка"),
                                            ("front", "Корпус: вид спереди")))
        page = f'''<!doctype html><meta charset="utf-8"><title>{escape(TITLES[name])}</title>
<style>body{{font:18px Arial;margin:32px;background:#f4f2eb;color:#203b45}}
h1{{font-size:32px}} .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
section{{background:white;border-radius:12px;padding:15px}}h2{{font-size:18px;min-height:44px}}
img{{width:100%;height:540px;object-fit:contain}}p{{line-height:1.5}}small{{font-size:16px}}</style>
<h1>{escape(TITLES[name])}</h1><p>{escape(NOTES[name])}</p><div class="cards">{cards}</div>
<p>Общая посадка: Ø{INSTALL_DIAMETER + clearance:g} × 22 мм. TFA 60.3065.02, одна батарея AA. PETG / FDM — прототип.</p>
<small>Штатная проекция build123d/OCCT. Диск показывает направление модуля; его профиль условный.
Винты и штатное кольцо не показаны. Реальные допуски и удержание кольцом требуют образца.
Это чертёжная иллюстрация, а не подтверждение физической сборки или прочности.</small>'''
        (dest / "preview.html").write_text(page, encoding="utf-8")
    cards = "".join(f'<section><h2>{escape(TITLES[n])}</h2><img src="{n}/assembled.svg">'
                    f'<p>{escape(NOTES[n])}</p></section>' for n in family)
    (out / "overview.html").write_text(f'''<!doctype html><meta charset="utf-8">
<title>Три корпуса для TFA 60.3065.02</title><style>
body{{font:18px Arial;margin:36px;background:#f4f2eb;color:#203b45}}h1{{font-size:36px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}}section{{background:white;padding:20px;border-radius:12px}}
h2{{font-size:21px;min-height:52px}}img{{width:100%;height:510px;object-fit:contain}}p{{line-height:1.55}}</style>
<h1>Одна посадка — три корпуса</h1><p>TFA Dostmann 60.3065.02 · AA · Ø77 × 22 мм по изготовителю</p>
<div class="cards">{cards}</div><p>Общий номинальный зазор: {clearance:g} мм на диаметр.
Профиль модуля показан условно; удержание штатным кольцом и реальные допуски не проверены.</p>
<p>Параметрические прототипы PETG/FDM. Изображения получены из фактической CAD-геометрии через OCCT HLR.</p>''', encoding="utf-8")


def rasterize(out, browser):
    """Must be called under the managed executor: one Chrome, <=4 captures."""
    from PIL import Image
    out = Path(out).resolve()
    profile = out.parent / "clock_family_preview_profile"
    targets = [(out / "overview.html", out / "overview.png")]
    targets += [(out / name / "preview.html", out / name / "preview.png") for name in TITLES]
    records = {}
    for html, png in targets:
        png.unlink(missing_ok=True)
        command = [str(browser), "--headless", "--disable-gpu", "--no-first-run",
                   "--no-default-browser-check", "--disable-extensions", "--disable-background-networking",
                   "--disable-crash-reporter", "--hide-scrollbars", "--window-size=1400,1080",
                   f"--user-data-dir={profile}", f"--screenshot={png}", html.as_uri()]
        result = subprocess.run(command, timeout=40, capture_output=True)
        if result.returncode or not png.exists():
            raise RuntimeError(f"Chrome preview failed for {html.name}: exit {result.returncode}")
        with Image.open(png) as im:
            if im.size != (1400, 1080):
                raise RuntimeError(f"Unexpected PNG size: {im.size}")
            im.verify()
        records[png.relative_to(out).as_posix()] = "Captured; human/agent visual review separate"
    (out / "preview-capture.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/clock_family/baseline")
    parser.add_argument("--browser", type=Path, default=Path("C:/Program Files/Google/Chrome/Application/chrome.exe"))
    args = parser.parse_args()
    rasterize(args.output_dir, args.browser)
