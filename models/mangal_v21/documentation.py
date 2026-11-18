"""Self-contained release 2.1 PDF from current evidence, without rebuilding CAD."""
import argparse
from html import escape
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if not __package__:
    sys.path.insert(0, str(ROOT))
from models.mangal.documentation import data_image, table

DEFAULT_OUT = ROOT/'output'/'mangal_v21'


def build(out, browser=None):
    out = Path(out).resolve()
    report_path = out/'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('release') != '2.1':
        raise ValueError('Expected release 2.1 report')
    for name, digest in report['source_sha256'].items():
        if hashlib.sha256((ROOT/'models'/'mangal_v21'/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Source changed since report: {name}; rerun model')
    for name, digest in report.get('dependency_source_sha256', {}).items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Dependency changed since report: {name}; rerun model')
    for name, digest in report['artifacts']['sha256'].items():
        if name.endswith(('.pdf', '.html')) or name.startswith('documentation_'):
            continue
        if hashlib.sha256((out/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Artifact changed since report: {name}')
    p, actual, checks = report['parameters'], report['actual'], report['checks']
    counts = {s: sum(c['status'] == s for c in checks.values()) for s in ('PASS', 'FAIL', 'NOT_CHECKED')}
    bom = json.loads((out/'bom.json').read_text(encoding='utf-8'))
    measured = actual['measured_parameters']
    mech = report['mechanics']
    angle = p['wedge_angle_deg']
    seat = mech['first_contact_CAD_drop_mm']
    lift = seat+p['release_margin']
    images = {name: data_image(out/name, crop=name.endswith('.png'), vector_weight=name == 'layout.svg')
              for name in ('assembly_iso.png', 'assembly_top.png', 'layout.png', 'layout.svg', 'assembly_sequence.svg')}
    joint_image = data_image(out/'upper_joint.png', crop=True) if (out/'upper_joint.png').exists() else images['assembly_top.png']
    css = '''@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;color:#213446;font:10pt/1.4 Arial,sans-serif;print-color-adjust:exact;-webkit-print-color-adjust:exact}
.page{width:210mm;height:297mm;padding:15mm 17mm 18mm;position:relative;page-break-after:always;overflow:hidden}.page:last-child{page-break-after:auto}
header{font-size:8pt;color:#627789;border-bottom:1px solid #bccbd6;padding-bottom:3mm}h1{font-size:23pt;line-height:1.15;margin:7mm 0 5mm}h2{font-size:13pt;margin:5mm 0 2mm}p{margin:3mm 0}
footer{position:absolute;bottom:10mm;left:17mm;right:17mm;color:#627789;border-top:1px solid #bccbd6;padding-top:2mm;font-size:8pt}footer span{float:right}
table{width:100%;border-collapse:collapse;font-size:9pt;margin:4mm 0}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #d8e1e7;padding:2mm}th{background:#edf2f5}
.hero{width:100%;height:98mm;object-fit:contain}.layout{width:100%;height:130mm;object-fit:contain}.smallpic{width:48%;height:60mm;object-fit:contain}.diagram{width:100%;height:48mm;object-fit:contain}
.note{padding:3mm;background:#edf2f5;border-left:3px solid #57768a;margin:4mm 0}.small{font-size:8.5pt;color:#526575}li{margin-bottom:2mm}ol,ul{padding-left:6mm}code,pre{font:8.5pt/1.45 Consolas,monospace;overflow-wrap:anywhere}pre{background:#edf2f5;padding:3mm;white-space:pre-wrap}.checks{font-size:8pt}.checks td{padding:1.2mm}.badge{font-weight:bold;color:#8d5c16}'''
    pages = []
    def add(title, body):
        n = len(pages)+1
        pages.append(f'<section class="page"><header>МАНГАЛ / ЦИФРОВОЙ ПРОТОТИП · ВЫПУСК 2.1</header><h1>{title}</h1>{body}<footer>build123d / Open Cascade · размеры в мм<span>{n} / 7</span></footer></section>')
    add('Разборный мангал 2.1',
        '<p class="badge">ДОКУМЕНТАЦИЯ ПРОТОТИПА — НАТУРНАЯ ПРИЁМКА ОТКРЫТА</p>'
        f'<img class="hero" src="{images["assembly_iso.png"]}">'
        +table(['Измерено по CAD', 'Значение'], [
            ('Внутри / высота стенок', f'{measured["inside_length_mm"]:g} × {measured["inside_width_mm"]:g} / {measured["wall_height_mm"]:g}'),
            ('Низ дна / полезная глубина', f'{measured["bottom_elevation_mm"]:g} / {measured["usable_depth_mm"]:g}'),
            ('Лист / предварительный материал', f'{p["thickness"]:g} / S235JR без покрытия'),
            ('Комплект / расчётная масса', f'5 деталей, 3 уникальных контура / {actual["mass_kg"]:.3f} кг'),
            ('Сборочный габарит XYZ', ' × '.join(f'{v:g}' for v in actual['assembly_bounds_mm']['size']))])
        +f'<div class="note">Текущий отчёт: {counts["PASS"]} PASS; {counts["FAIL"]} FAIL; {counts["NOT_CHECKED"]} NOT_CHECKED. '
        f'Геометрия: {escape(report.get("geometry_status", "не определено"))}. '
        'Статусы цифровых проверок не подтверждают готовность производства, прочность или разборку после огня.</div>'
        '<p class="small">Свежий снимок OCP CAD Viewer иллюстрирует сборку. Численные размеры получены из CAD, а не из изображения.</p>')
    add('Что изменилось в выпуске 2.1',
        table(['Участок', 'Выпуск 2.0', 'Выпуск 2.1'], [
            ('Фиксаторы', '4 плоские чеки', 'Все чеки удалены; покупного крепежа нет'),
            ('Верхние выступы', 'Прорези под чеки', 'Прорези заполнены; вылет выступов не уменьшен'),
            ('V и нижняя направляющая', f'{angle:g}°; Z-зазор {p["guide_vertical_clearance"]:g}', 'Сохранены'),
            ('Разборка', 'Удалить чеки, поднять стенки, снять торец', 'Поднять обе стенки, снять торец, дно и стенки'),
            ('Комплект', '9 деталей, 4 контура', '5 деталей, 3 контура')])
        +f'<h2>Верхняя посадка</h2><p>Два X-угла нижней кромки верхнего окна торца входят в V-вырез '
        f'нижней кромки верхнего выступа стенки. Окончательная CAD-поза — первый контакт: '
        f'выступ опущен примерно на {seat:.2f}. Основной верх стенки остаётся на Z = {measured["main_wall_top_mm"]:g}.</p>'
        f'<p>Разгрузка вершины радиусом {p["thickness"]*.1:g} целиком выше несущей кромки. '
        'Угловые разгрузки окна торца сокращают ширину прямой несущей кромки по Y; '
        'контакт по всей толщине листа и контактные напряжения не подтверждены.</p>'
        '<div class="note">V выбирает зазор в XZ. Поперечный Y-зазор сохраняется: устранение всех люфтов не заявлено. '
        'Нижнее окно служит свободной направляющей. Посаженный V удерживает торец '
        'вдоль X только пока стенки не подняты. Отдельной защиты от подъёма нет: '
        'случайный подъём может освободить торец.</div>'
        f'<img class="smallpic" src="{joint_image}"><img class="smallpic" src="{images["layout.png"]}">')
    names = dict(side='Продольная стенка', end='Торец с ножками', bottom='Дно')
    add('Спецификация и плоский комплект',
        table(['Деталь / файл', 'Кол.', 'Габарит XY', 'кг / шт.', 'кг всего'], [
            (f'{names[b["part"]]}<br>{b["cutting_file"]}', b['quantity'], f'{b["width_mm"]:g} × {b["height_mm"]:g}',
             f'{b["unit_mass_kg"]:.3f}', f'{b["total_mass_kg"]:.3f}') for b in bom])
        +f'<p>Плотность для оценки {p["density"]:g} кг/м³; фактический CAD-объём. '
        f'Масса одной новой стенки {actual["mass_wall_kg"]:.3f} кг. Образец не взвешивался. '
        'Покупные крепёжные детали не требуются.</p>'
        f'<img class="layout" src="{images["layout.svg"]}">'
        '<p class="small">Штатный векторный SVG всей раскладки. На странице масштаб уменьшен; '
        'для резки — отдельные DXF 1:1 в мм. Раскладка не является оптимизированным раскроем листа.</p>')
    selected = [r for r in mech['cases'] if r['normal_stiffness_N_mm'] == 1000]
    add('Условная механика посадки',
        f'<p>Владелец расчёта: <code>{escape(mech["owner"])}</code>. Масса новой стенки '
        f'{actual["mass_wall_kg"]:.3f} кг взята из её CAD-объёма; на каждый торцевой узел '
        'принято 1/2 веса стенки. Симметричны две грани; угол указан от вертикали.</p>'
        +table(['μ', 'Вес / узел, Н', 'N / грань, Н', 'Подъём / узел, Н'], [
            (f'{r["mu_static"]:g}', f'{r["weight_per_joint_N"]:.3f}', f'{r["normal_per_face_N"]:.3f}',
             f'{r["peak_up_force_per_joint_N"]:.3f}') for r in selected])
        +'<p>Таблица — условный силовой конверт при K = 1000 Н/мм на грань. '
        'В report.json также сценарии K = 100 и 10000 Н/мм; μ = 0.1, 0.3, 0.8. '
        'Жёсткость и трение не измерены. Силы в таблице относятся к одному узлу; '
        'они не равны усилию руки для одновременного подъёма двух стенок.</p>'
        f'<h2>Граница самоторможения</h2><p>Для симметричной модели μ ≥ tan({angle:g}°) '
        f'= {mech["self_lock_threshold_mu"]:.6f}. Значения μ ниже этого порога '
        'не гарантируют разборку реального нагретого изделия: возможны перекос, '
        'окисление, загрязнение и остаточное обжатие.</p>'
        '<div class="note">Rigid CAD показывает первый контакт, а не упругое вдавливание '
        'и не положительную измеренную нормальную силу. Положительные N в таблице '
        'получены только из гипотетической податливости. Продолжение расчёта допустимо '
        'лишь пока работают прямые V-грани, без удара, нагрузки нижних направляющих '
        'и остаточного температурного преднатяга.</div>'
        '<p>Расчёт не подтверждает контактные напряжения, прочность, устойчивость '
        'или ручное освобождение после охлаждения. Полные входы и ограничения сохранены в report.json.</p>')
    add('Сборка и разборка',
        '<h2>Сборка холодных деталей</h2><ol><li>Удерживать первый торец вертикально.</li>'
        f'<li>Ввести обе стенки, удерживая их примерно на {lift:.1f} мм выше окончательной посадки.</li>'
        '<li>Ввести дно; стенки оставить приподнятыми.</li><li>Надвинуть второй торец вдоль X.</li>'
        '<li>Одновременно опустить обе стенки до контакта V.</li></ol>'
        '<h2>Разборка только после полного охлаждения</h2><ol>'
        f'<li>Приподнять ОБЕ стенки примерно на {lift:.1f} мм; удерживать их приподнятыми.</li>'
        '<li>Снять второй торец вдоль +X.</li><li>Выдвинуть дно вдоль +X.</li>'
        '<li>Вывести обе приподнятые стенки из первого торца вдоль +X.</li></ol>'
        f'<img class="diagram" src="{images["assembly_sequence.svg"]}">'
        '<div class="note">Дно снимается после освобождения одного торца. Подъём около 0.5 мм '
        '— ориентир; рукой достаточно свободно вывести V без удара и забивания. '
        'Не переносить сборку за стенки: их подъём снимает удержание торцов. '
        'Чек и независимой защиты от случайного подъёма нет.</div>'
        '<p>Критерий натурной приёмки: повторяемая сборка руками без подгонки; после '
        'согласованных циклов нагрева и полного охлаждения — разборка и съём дна '
        'руками без молотка и остаточной деформации. Холодное обращение с ненагруженным '
        'образцом и риск случайного подъёма ещё не испытаны. Режим испытаний и нагрузка не назначены.</p>')
    critical = ['physical_assembly', 'hot_performance', 'manual_release', 'stability_strength', 'manufacturing_fit']
    digital = [(n, c) for n, c in checks.items() if n not in critical]
    failed = [(n, c) for n, c in digital if c['status'] != 'PASS']
    add('Проверки и границы готовности',
        f'<p>Из текущего report.json: <b>{counts["PASS"]} PASS / {counts["FAIL"]} FAIL / '
        f'{counts["NOT_CHECKED"]} NOT_CHECKED</b>. Исполнение: {escape(report.get("execution_status", "не определено"))}; '
        f'геометрия: {escape(report.get("geometry_status", "не определено"))}.</p>'
        '<p>Численные группы: состав и валидность тел, замкнутые плоские профили, '
        'толщина и габариты, пересечения, нативные V-грани и опорные направления, '
        'направляющие, удержание посаженным V и освобождение после подъёма, последовательные непрерывные перемещения, '
        'повторный импорт STEP, контроль DXF и раскладки. Полные значения — в report.json.</p>'
        +table(['Обязательная натурная проверка', 'Статус / причина'], [
            (n, f'{checks[n]["status"]}<br>{escape(checks[n]["reason"])}') for n in critical], 'checks')
        +'<h2>Открытые цифровые пункты</h2>'
        +(table(['Проверка', 'Статус / причина'], [(escape(n), f'{c["status"]}: {escape(c.get("reason", "см. report.json"))}')
                                                for n, c in failed], 'checks') if failed else '<p>Все перечисленные цифровые пункты имеют PASS.</p>')
        +'<div class="note">PASS проверки BREP или перемещения не заменяет физическую сборку. '
        'Снимки не доказывают размеры. Отсутствие проникновения при численном пробном '
        'смещении не является доказательством допуска станка.</div>')
    add('Изготовление и воспроизведение',
        f'<p>Три контура DXF 1:1, пять деталей; лист {p["thickness"]:g} мм; S235JR предварительно, '
        'без покрытия. Не нужны сварка, гибка и покупной крепёж. Снять заусенцы и острые кромки. '
        'Компенсация ширины реза принадлежит CAM исполнителя; в CAD её нет.</p>'
        f'<p>Номинальный суммарный Y-зазор {p["clearance"]:g}; нижний Z-зазор '
        f'{p["guide_vertical_clearance"]:g}, из него вниз '
        f'{p["guide_vertical_clearance"]-p["guide_up_allowance"]:g}, вверх {p["guide_up_allowance"]:g}. '
        'Это практические номиналы. Точные координаты цифрового контакта '
        'сохранены в JSON и не требуют высокоточной обработки.</p>'
        '<p>Измерить реальный лист и согласовать допуски резки, конусность и зачистку. '
        'Сначала вырезать купон с V и нижней направляющей на том же станке. '
        'Варианты 2 и 4 мм перестраиваются параметрами и требуют своей проверки, '
        'а не масштабирования готового DXF.</p>'
        +table(['Источник / результат', 'Назначение'], [
            ('models/mangal_v21/model.py', 'Параметры и редактируемая геометрия'),
            ('validation.py / exports.py / documentation.py', 'Численные проверки, BOM, документы, этот PDF'),
            ('output/mangal_v21/assembly.step', 'Сборка пяти отдельных тел'),
            ('side/end/bottom.dxf; layout.svg', 'Резка и плоский комплект'),
            ('bom.csv/json; report.json', 'Массы, количества и evidence'),
            ('instructions.md; manufacturing.md; release_notes.md', 'Порядок сборки и ограничения')])
        +'<pre>.venv/Scripts/python.exe models/mangal_v21/model.py --screenshots\n.venv/Scripts/python.exe -m pytest -q\n.venv/Scripts/python.exe models/mangal_v21/documentation.py</pre>'
        '<p class="small">Предыдущие модели и результаты сохранены отдельно. При изменении '
        'источников повторить затронутые проверки, осмотр новых PNG и сборку PDF. '
        'Этот документ сверяет SHA-256 источников и артефактов с текущим отчётом. '
        'Исторические исследования находятся в output/mangal/research.md; новые '
        'производственные гарантии из них не выводятся.</p>')
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Мангал 2.1</title><style>'+css+'</style><body>'+''.join(pages)+'</body></html>'
    html_path = out/'documentation.html'
    html_path.write_text(html, encoding='utf-8')
    assert html_path.read_text(encoding='utf-8') == html
    browser = browser or shutil.which('chrome') or 'C:/Program Files/Google/Chrome/Application/chrome.exe'
    pdf = out/'mangal_v21_documentation.pdf'
    with tempfile.TemporaryDirectory(prefix='mangal-v2-pdf-') as profile:
        result = subprocess.run([str(browser), '--headless', '--disable-gpu', '--disable-extensions',
            '--disable-background-networking', '--no-first-run', '--no-default-browser-check',
            '--no-pdf-header-footer', '--allow-file-access-from-files', f'--user-data-dir={profile}',
            '--virtual-time-budget=2500', f'--print-to-pdf={pdf}', html_path.as_uri()],
            capture_output=True, timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not pdf.exists() or not pdf.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
    manifest = dict(pdf=pdf.name, pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    source_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
                    source_sha256=report['source_sha256'], check_counts=counts, pages=7,
                    rendering='Installed Chrome A4; embedded PNG and native SVG; no CAD rebuild')
    (out/'documentation_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(pdf)
    return pdf


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--browser', type=Path)
    args = parser.parse_args()
    build(args.output_dir, args.browser)

