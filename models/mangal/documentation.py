"""Assemble the existing verified mangal dossier into a self-contained PDF.

Uses Python standard library, existing Pillow, and installed Chrome print-to-PDF.
Does not rebuild CAD or overwrite its acceptance evidence.
"""
import argparse
import base64
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / 'output' / 'mangal'


def data_image(path, crop=False, vector_weight=False):
    data = path.read_bytes()
    if path.suffix == '.svg':
        if vector_weight:
            data = data.replace(b'stroke-width="0.15"', b'stroke-width="0.9"')
        return 'data:image/svg+xml;base64,' + base64.b64encode(data).decode()
    uri = 'data:image/png;base64,' + base64.b64encode(data).decode()
    if crop:
        # Document viewport only: original viewer image remains unchanged.
        with Image.open(path) as im:
            x0, y0, x1, y1 = im.getbbox()
            width, height = im.size
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0-6} {y0-6} {x1-x0+12} {y1-y0+12}">'
               f'<image width="{width}" height="{height}" href="{uri}"/></svg>')
        return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()
    return uri


def table(headers, rows, cls=''):
    return (f'<table class="{cls}"><thead><tr>' + ''.join(f'<th>{escape(str(h))}</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows)
            + '</tbody></table>')


def page(title, body, n, subtitle=''):
    return (f'<section class="page"><header>МАНГАЛ / ИНЖЕНЕРНЫЙ ПРОТОТИП <span>06.11.2026 · редакция 1</span></header>'
            f'<h1>{title}</h1><div class="sub">{subtitle}</div>{body}'
            f'<footer>Параметрический проект build123d · размеры в мм<span>{n} / 8</span></footer></section>')


LABELS = {
    'part_inventory':'Комплектность: 9 отдельных деталей',
    'valid_single_solids':'Валидность и связность каждого тела',
    'flat_closed_profiles':'Плоские замкнутые контуры',
    'sheet_thickness':'Толщина листа всех деталей',
    'dimensions':'Габариты относительно параметров',
    'assembled_no_interference':'Отсутствие пересечений в сборке',
    'keys_restrain_end':'Удержание торца установленными чеками',
    'inverted_side_cannot_seat':'Невозможность посадки перевёрнутой стенки',
    'assembly_motions_present':'Наличие последовательности движений',
    'ventilation_geometry':'32 вентиляционных отверстия Ø10',
    'skewer_notches':'9 пар вырезов под шампуры',
    'flat_storage':'Возможность плоской укладки',
    'step_roundtrip':'Повторный импорт STEP: 9 тел',
    'dxf_side':'DXF: продольная стенка', 'dxf_end':'DXF: торец с ножками',
    'dxf_bottom':'DXF: дно', 'dxf_key':'DXF: чека',
    'flat_layout':'SVG-раскладка полного комплекта',
    'static_estimate':'Устойчивость под нагрузкой',
    'thermal_estimate':'Рабочий тепловой режим и деформации',
    'hot_strength':'Прочность при нагреве',
    'service_durability':'Ресурс и циклы нагрева/охлаждения',
    'manufacturing_fit':'Фактическая посадка после лазерной резки',
    'physical_assembly':'Физическая сборка прототипа',
    'viewer_images':'Снимки OCP CAD Viewer',
    'visual_review':'Осмотр изображений агентом',
    'pytest':'Общая тестовая проверка: 28 passed',
}
PARTS = {'side_1':'стенка 1','side_2':'стенка 2','end_2':'торец 2','bottom':'дно',
         'key_1':'чека 1','key_2':'чека 2','key_3':'чека 3','key_4':'чека 4'}
CLEARANCES = {
    'side_lateral_minus':'Стенка: поперечный ход −Y', 'side_lateral_plus':'Стенка: поперечный ход +Y',
    'side_vertical':'Стенка: вертикальный ход +Z',
    'bottom_lateral_minus':'Дно: поперечный ход −Y', 'bottom_lateral_plus':'Дно: поперечный ход +Y',
    'bottom_axial_minus':'Дно: продольный ход −X', 'bottom_axial_plus':'Дно: продольный ход +X',
    'key_axial_minus':'Чека: продольный ход −X', 'key_axial_plus':'Чека: продольный ход +X',
}


def build(out, browser=None):
    report = json.loads((out/'report.json').read_text(encoding='utf-8'))
    bom = json.loads((out/'bom.json').read_text(encoding='utf-8'))
    # Publish only a dossier whose underlying receipts still match their files.
    for name, digest in report['source_sha256'].items():
        if hashlib.sha256((ROOT/'models'/'mangal'/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'CAD source changed since acceptance: {name}')
    for name, digest in report['artifacts']['sha256'].items():
        if name.endswith(('.pdf','.html')) or name.startswith('documentation_'):
            continue
        if hashlib.sha256((out/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Accepted artifact changed: {name}')
    checks = report['checks']
    p = report['parameters']
    nominal = dict(length=500, width=300, height=160, thickness=3, leg_height=180,
                   clearance=.6, bottom_gap=3, key_float=3, relief_radius=.8, density=7850)
    if p != nominal:
        raise ValueError('This reviewed PDF template describes the nominal prototype; update its text for another parameter set')
    counts = {s:sum(c['status']==s for c in checks.values()) for s in ('PASS','FAIL','NOT_CHECKED')}
    mass = sum(b['total_mass_kg'] for b in bom)
    iso = data_image(out/'assembly_iso.png', crop=True)
    top = data_image(out/'assembly_top.png', crop=True)
    layout = data_image(out/'layout.svg', vector_weight=True)
    css = '''@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;color:#202d38;font:10.5pt/1.43 Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{width:210mm;height:297mm;padding:17mm 18mm 18mm;page-break-after:always;position:relative;overflow:hidden}.page:last-child{page-break-after:auto}
header{font-size:8pt;letter-spacing:.7px;color:#60717e;border-bottom:1px solid #ccd6dc;padding-bottom:3mm;margin-bottom:7mm}header span,footer span{float:right}
h1{font-size:25pt;line-height:1.12;margin:0 0 4mm;color:#173748}h2{font-size:14pt;margin:6mm 0 2mm;color:#173748}h3{font-size:11pt;margin:3mm 0 1mm}
p{margin:2mm 0 3mm}.sub{color:#627482;font-size:10pt;margin-bottom:5mm}footer{position:absolute;bottom:9mm;left:18mm;right:18mm;color:#627482;border-top:1px solid #ccd6dc;padding-top:2mm;font-size:8pt}
table{width:100%;border-collapse:collapse;margin:3mm 0 4mm;font-size:9.4pt}th{background:#eaf0f3;text-align:left}td,th{border-bottom:1px solid #d9e0e4;padding:2mm 1.8mm;vertical-align:top}tr{break-inside:avoid}
.dense{font-size:8pt}.dense td,.dense th{padding:.7mm 1.6mm;line-height:1.15}.dense .small{font-size:7.3pt;line-height:1.15}.dense td:first-child{width:74%}.status{font-size:8.2pt;font-weight:bold;white-space:nowrap}.PASS{color:#196044}.FAIL{color:#a12828}.NOT_CHECKED{color:#886018}
.note{padding:3mm 4mm;border-left:3px solid #b9914a;background:#faf5e9;margin:4mm 0}.small{font-size:9pt;color:#566773}.grid{display:grid;grid-template-columns:1fr 1fr;gap:7mm}.hero{height:103mm;display:block;margin:0 auto 4mm;max-width:100%}.top{width:75mm;height:50mm;object-fit:contain}.layout{width:100%;height:110mm;object-fit:contain}
ol,ul{padding-left:6mm;margin:2mm 0}li{margin-bottom:2.5mm}code{font:8.7pt Consolas,monospace;background:#f0f3f5;padding:1mm;overflow-wrap:anywhere}pre{font:8.5pt/1.6 Consolas,monospace;background:#f0f3f5;padding:3mm;white-space:pre-wrap}a{color:#235774;text-decoration:none;overflow-wrap:anywhere}.sources{font-size:8.5pt;line-height:1.3}.sources li{margin-bottom:2mm}.stamp{font-size:11pt;font-weight:bold;letter-spacing:.5px;color:#886018}'''
    pages=[]
    pages.append(page('Разборный мангал',
        f'<p class="stamp">ДОКУМЕНТАЦИЯ ЦИФРОВОГО ПРОТОТИПА</p><img class="hero" src="{iso}">'
        +table(['Параметр','Номинальное значение'],[
            ('Внутри между стенками','500 × 300 мм'),('Высота стенок / полезная глубина','160 / 147 мм'),
            ('Лист / предварительный материал','3 мм / S235JR, без покрытия'),
            ('Комплект / расчётная масса',f'9 деталей, 4 уникальных контура / {mass:.3f} кг'),
            ('Полный габарит / идеальная стопка','544 × 346 × 340 / 544 × 340 × 27 мм')])
        +f'<div class="note"><b>Статус:</b> инженерный прототип для согласования. Геометрия и экспорты проверены; '
         f'{counts["PASS"]} PASS, {counts["FAIL"]} FAIL, {counts["NOT_CHECKED"]} NOT_CHECKED. '
         'Изготовление и эксплуатация не одобрены автоматически.</div>'
         '<p class="small">Иллюстрация — существующий снимок OCP CAD Viewer. Размеры подтверждены CAD-измерениями, а не изображением.</p>',1,
         'Лазерная резка плоских стальных деталей · без сварки и гибки'))
    pages.append(page('Конструкция и сопряжения',
        '<p>Две продольные стенки соединяются с двумя торцами через закрытые пазы. Торцы одновременно образуют четыре ножки. '
        'Верхние выступы удерживаются четырьмя одинаковыми плоскими чеками. Дно опирается четырьмя язычками на нижние кромки пазов торцов.</p>'
        +table(['Размер или посадка','Значение'],[
            ('Длина / ширина между внутренними гранями','500 / 300'),('Высота стенок / высота ножек до стенок','160 / 180'),
            ('Нижняя поверхность дна над основанием','190'),('Полезная глубина над дном','147'),
            ('Толщина / номинальный паз под толщину','3 / 3,6'),('Вертикальный свободный ход стенки в пазах','0,6'),
            ('Свободный продольный / поперечный ход дна','±3 / ±2'),('Продольный зазор от торца до чеки','3'),
            ('Радиус разгрузочных вырезов','0,8'),('Вентиляция','32 отверстия Ø10; суммарно около 2513 мм²'),
            ('Вырезы под шампуры','9 пар; ширина 10, глубина 8, шаг 50')])
        +'<div class="grid"><div><h2>Почему эта схема</h2><p>Пять крупных пластин и четыре одинаковые чеки позволяют исключить отдельные уголки, '
        'крепёж и гнутые опоры. Все детали вырезаются из плоского листа. Дно заменяемое и съёмное.</p></div>'
        f'<div><img class="top" src="{top}"><p class="small">Вид сверху: дно внутри корпуса.</p></div></div>'
        '<p>Стороны одного типа взаимозаменяемы. Верхние и нижние выступы различаются по высоте и расположению: перевёрнутая стенка не садится в торец. '
        'Чеки устанавливаются прорезью вниз и удерживаются тяжестью.</p>'
        '<div class="note">Зазоры заданы для идеальной холодной геометрии. Фактические толщина, окалина, конусность реза и зачистка требуют пробного купона.</div>',2))
    names={'side':'Продольная стенка','end':'Торец с ножками','bottom':'Дно','key':'Чека'}
    pages.append(page('Спецификация и плоский комплект',
        table(['Деталь / DXF','Кол.','Габарит, мм','Масса 1 шт., кг','Всего, кг'],[
            (f'<b>{names[b["part"]]}</b><br><span class="small">{b["cutting_file"]}</span>',str(b['quantity']),
             f'{b["width_mm"]:g} × {b["height_mm"]:g}',f'{b["unit_mass_kg"]:.3f}',f'{b["total_mass_kg"]:.3f}') for b in bom])
        +f'<p>Все детали: лист {p["thickness"]:g} мм, предварительно S235JR без покрытия. Плотность для оценки массы — {p["density"]:g} кг/м³. '
         f'<b>Итого {mass:.3f} кг.</b></p><img class="layout" src="{layout}">'
        '<p class="small">Векторная раскладка всех девяти деталей. Снизу вверх: две стенки, два торца, дно, четыре чеки. '
        'Масштаб на этой странице уменьшен для размещения в A4; это не шаблон для резки.</p>'
        '<div class="note">Для производства использовать исходные DXF 1:1 в мм. Ширина реза в контурах не компенсирована. '
        'Раскладка демонстрационная: формат листа, выход годного и оптимизация nesting не определены.</div>',3))
    pages.append(page('Сборка и разборка',
        '<h2>Последовательность сборки</h2><ol>'
        '<li>Разложить две стенки, два торца, дно и четыре чеки. Поддерживать первый торец вертикально.</li>'
        '<li>Ввести верхние и нижние выступы обеих стенок в соответствующие пазы первого торца горизонтальным движением. '
        'Опустить две чеки в верхние выступы.</li>'
        '<li>Вдвинуть дно вдоль корпуса: два его язычка должны войти в пазы первого торца и опереться на их нижние кромки.</li>'
        '<li>Надвинуть второй торец на выступы обеих стенок и два свободных язычка дна. Установить оставшиеся две чеки вниз до посадки.</li>'
        '<li>Проверить посадку всех выступов и чек, опирание дна и контакт всех четырёх ножек с ровным жёстким основанием.</li></ol>'
        '<div class="note"><b>Схема порядка:</b><br>Первый торец → две стенки → две чеки → дно → второй торец → две чеки.<br>'
        'Детали вводятся в пазы, а не защёлкиваются с усилием. Геометрически проверен обратимый путь сборки/разборки.</div>'
        '<h2>Последовательность разборки</h2><ol>'
        '<li>Полностью остудить и очистить мангал. Снять две чеки второго торца движением вверх.</li>'
        '<li>Сдвинуть второй торец наружу вдоль длины до выхода всех выступов и язычков.</li>'
        '<li>Выдвинуть дно из пазов первого торца и убрать его.</li>'
        '<li>Снять две оставшиеся чеки. Выдвинуть стенки из первого торца. Уложить все детали параллельно в стопку.</li></ol>'
        '<h2>Ориентация и обращение</h2><p>Торцы ставятся ножками вниз, стенки — вырезами под шампуры вверх, чеки — прорезью вниз. '
        'Дно симметрично. Не силовать соединения, если они деформировались от нагрева.</p>'
        '<p><b>Чеки не имеют защиты от выпадения при переворачивании.</b> Не переносить горячую или загруженную сборку. '
        'Проверенная CAD-траектория не подтверждает удобство сборки руками и фактическую посадку после резки.</p>',4))
    check_rows=[]
    for name,check in checks.items():
        label=LABELS.get(name,name)
        detail=''
        if name.startswith('seated_'): label='Опирание: '+PARTS.get(name[7:],name[7:]);detail='Ход вниз блокируется в пределах 0,1 мм'
        if name.startswith('motion_'): label='Непрерывное движение: '+PARTS.get(name[7:],name[7:]);detail='Объёмная проверка всей траектории'
        if name.startswith('clearance_'):
            label=CLEARANCES[name[10:]]
            detail='Граница хода '+str(check['expected']['nominal_travel_mm']).replace('.',',')+' мм; пробы ±0,01'
        if name.startswith('dxf_'):detail='Аудит, дубликаты, замкнутость, площадь, габариты'
        if name=='step_roundtrip':detail='Симметрическая разность каждого тела < 0,01 мм³'
        if name=='pytest':detail='28 passed; 226,17 с; текущая приёмочная запись'
        if check['status']=='NOT_CHECKED':detail='Оценка или ограничение; физического подтверждения нет'
        check_rows.append((escape(label)+(f'<br><span class="small">{escape(detail)}</span>' if detail else ''),
                           f'<span class="status {check["status"]}">{check["status"]}</span>'))
    for n,rows in ((5,check_rows[:26]),(6,check_rows[26:])):
        pages.append(page('Проверки '+('геометрии' if n==5 else 'и границы приёмки'),
            '<p class="small">Сводка из report.json. PASS означает результат указанной проверки; NOT_CHECKED — отсутствие соответствующей приёмки.</p>'
            +table(['Требование / проверка','Результат'],rows,'dense')
            +('<p class="small">Непрерывные траектории проверены средствами Open Cascade по точным объёмам перемещения поверхностей, без дискретного перебора положений.</p>' if n==5 else
              '<div class="note">Геометрическая пригодность прототипа подтверждена. Производственная посадка, допустимая нагрузка и эксплуатационная безопасность требуют физической проверки.</div>'),n))
    pages.append(page('Ограничения и физический прототип',
        '<h2>Устойчивость и плоские ножки</h2><p>Для пустой идеальной сборки центр масс расположен примерно на высоте 221 мм. '
        'Запас проекции до ближайшей границы опорного прямоугольника — 173 мм; идеальная оценка угла опрокидывания — около 38°. '
        'Основание принято ровным и жёстким. Ветер, перекос, нагрузка и упругость соединений не учтены.</p>'
        '<p>Плоские ножки могут изгибаться из своей плоскости. Расчёта прочности и потери устойчивости нет; допустимая масса топлива и еды не назначена.</p>'
        '<h2>Тепловое расширение и деформации</h2><p>Для условного нагрева 20 → 600 °C при α = 14 × 10⁻⁶/К свободное удлинение составляет '
        '4,06 мм на 500 мм и 2,44 мм на 300 мм. Суммарный продольный ход дна — 6 мм, поперечный — 4 мм.</p>'
        '<p>Эти величины позволяют оценить запас перемещения, но не доказывают отсутствие защемления при неравномерном нагреве. '
        'Возможны коробление дна и стенок, заклинивание пазов, окисление и изменение посадки после циклов. '
        'Тепловое поле, FEM и огневые испытания отсутствуют.</p>'
        '<h2>Перед полной резкой</h2><ol>'
        '<li>Согласовать марку стали, фактическую толщину, допуски, радиусы разгрузки, качество кромок и технологические перемычки.</li>'
        '<li>Вырезать пробный купон соединения на фактическом листе. Оценить посадку после штатной зачистки.</li>'
        '<li>Проверить полный холодный комплект: последовательность сборки, опирание, все чеки, плоскостность и устойчивость с согласованной нагрузкой.</li>'
        '<li>Провести контролируемые циклы нагрева/охлаждения на негорючем основании. После охлаждения повторно проверить деформации и разборность.</li></ol>'
        '<div class="note">Только после физической проверки назначить допустимую нагрузку и режим эксплуатации. '
        'Краевые зазоры и вентиляция не обеспечивают герметичность по золе; чеки могут выпасть при опрокидывании. '
        'Материал без цинкового и обычного лакокрасочного покрытия.</div>',7))
    research=(out/'research.md').read_text(encoding='utf-8')
    source_lines=[line[2:] for line in research.splitlines() if line.startswith('- ') and 'https://' in line]
    sources=''.join(f'<li>{escape(line.split(": https://")[0])}<br><a href="https://{escape(line.split(": https://",1)[1])}">https://{escape(line.split(": https://",1)[1])}</a></li>' for line in source_lines)
    pages.append(page('Файлы, воспроизведение и источники',
        '<p>Все результаты находятся в <code>output/mangal/</code>. Исходники — в <code>models/mangal/</code>. '
        'Единицы CAD и DXF — мм. На иллюстрации в PDF масштаб не переносится.</p>'
        +table(['Файл','Назначение'],[
            ('assembly.step','Сборка из девяти отдельных тел'),('side.dxf × 2; end.dxf × 2','Две стенки и два торца'),
            ('bottom.dxf × 1; key.dxf × 4','Дно и четыре чеки'),('bom.csv / bom.json','Количество, материал, толщина, масса'),
            ('report.json / acceptance.md','Численные проверки и итоговая приёмка'),('layout.svg / PNG','Раскладка и снимки'),
            ('manufacturing.md / instructions.md / research.md','Технологические заметки, сборка, исследование')],'dense')
        +'<h2>Повторное построение</h2><pre>.venv/Scripts/python.exe models/mangal/model.py --screenshots\n.venv/Scripts/python.exe -m pytest -q\n.venv/Scripts/python.exe models/mangal/documentation.py</pre>'
        '<p class="small">Параметры редактируются в Params в начале model.py. Новый запуск CAD требует новой приёмки и осмотра снимков; '
        'эта PDF фиксирует существующие evidence. Для печати PDF используется установленный Chrome.</p>'
        '<h2>Исследованные источники</h2><ol class="sources">'+sources+'</ol>'
        '<p class="small">Источники взяты из research.md, просмотрены при исходном проектировании 06.11.2026. '
        'Примеры коммерческих изделий и правила конкретных изготовителей не являются доказательством прочности этого проекта.</p>',8))
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><title>Разборный мангал — документация прототипа</title><style>'+css+'</style><body>'+''.join(pages)+'</body></html>'
    html_path=out/'documentation.html'
    html_path.write_text(html,encoding='utf-8')
    assert html_path.read_text(encoding='utf-8')==html
    browser = browser or shutil.which('chrome') or 'C:/Program Files/Google/Chrome/Application/chrome.exe'
    pdf=out/'mangal_documentation.pdf'
    with tempfile.TemporaryDirectory(prefix='mangal-pdf-') as profile:
        command=[str(browser),'--headless','--disable-gpu','--disable-extensions','--disable-background-networking',
                 '--no-first-run','--no-default-browser-check','--no-pdf-header-footer',
                 '--allow-file-access-from-files',f'--user-data-dir={profile}',
                 '--virtual-time-budget=2500',f'--print-to-pdf={pdf}',html_path.as_uri()]
        result=subprocess.run(command,capture_output=True,timeout=90,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not pdf.exists() or not pdf.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
    receipt={'pdf':pdf.name,'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
             'documentation_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'source_report_sha256':hashlib.sha256((out/'report.json').read_bytes()).hexdigest(),
             'cad_source_sha256':report['source_sha256'],'check_counts':counts,
             'rendering':'Installed Chrome, A4, embedded images and vector layout; original CAD unchanged'}
    (out/'documentation_manifest.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(pdf)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--browser',type=Path)
    args=parser.parse_args()
    build(args.output_dir.resolve(),args.browser)
