"""Release 2.0 BOM, engineering limits and assembly instructions; native CAD owner unchanged."""
import csv
import json
import math
from pathlib import Path

from build123d import Compound, GeomType
from models.mangal_wedge.mechanics import Case, evaluate


def export_documents(m, p, out, report):
    out = Path(out)
    rows = []
    for name, quantity in [('side', 2), ('end', 2), ('bottom', 1), ('key', 4)]:
        s = m['flats'][name]
        bb = s.bounding_box()
        mass = s.volume*p.density*1e-9
        rows.append(dict(part=name, quantity=quantity, material='S235JR (provisional)',
                         thickness_mm=p.thickness, width_mm=bb.size.X, height_mm=bb.size.Y,
                         area_mm2=m['profiles'][name].area, volume_mm3=s.volume,
                         density_kg_m3=p.density, unit_mass_kg=mass,
                         total_mass_kg=quantity*mass, cutting_file=f'{name}.dxf'))
    (out/'bom.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (out/'bom.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    bb = Compound(children=m['parts']).bounding_box()
    parts = {s.label: s for s in m['parts']}
    b = {n: s.bounding_box() for n, s in parts.items()}
    wall_mass = rows[0]['unit_mass_kg']
    actual = dict(mass_kg=sum(r['total_mass_kg'] for r in rows), mass_wall_kg=wall_mass,
                  assembly_bounds_mm=dict(min=list(bb.min), max=list(bb.max), size=list(bb.size)),
                  measured_parameters=dict(inside_length_mm=b['end_2'].min.X-b['end_1'].max.X,
                    inside_width_mm=b['side_2'].min.Y-b['side_1'].max.Y,
                    wall_height_mm=b['side_1'].size.Z, bottom_elevation_mm=b['bottom'].min.Z,
                    usable_depth_mm=b['side_1'].max.Z-b['bottom'].max.Z,
                    main_wall_top_mm=b['side_1'].max.Z),
                  mass_method='Native solid volume times assumed density, not a weighed prototype')
    report['actual'] = actual
    flank_ends = []
    for edge in m['profiles']['side'].edges():
        if edge.geom_type != GeomType.LINE:
            continue
        a, z = edge.start_point(), edge.end_point()
        dx, dy = z.X-a.X, z.Y-a.Y
        if abs(dy) < 1e-6 or abs(abs(dx/dy)-math.tan(math.radians(p.wedge_angle_deg))) > 1e-6:
            continue
        if (min(a.Y, z.Y) >= p.upper_tab_base-1e-6
                and max(a.Y, z.Y) <= p.upper_tab_base+p.wedge_run_height+1e-6
                and any(max(abs(a.X-c), abs(z.X-c)) < p.thickness+2
                        for c in (-p.thickness/2, p.length+p.thickness/2))):
            flank_ends.append(max(a.Y, z.Y)-p.upper_tab_base)
    native_flank_limit = min(flank_ends) if len(flank_ends) == 4 else None
    # Cases begin at the open V mouth. The CAD assembled pose is FIRST contact;
    # finite positive normals below come from hypothetical compliance, not BREP.
    cases = []
    for mu in (.1, .3, .8):
        for stiffness in (100, 1000, 10000):
            c = Case(angle_deg=p.wedge_angle_deg, mass_wall_kg=wall_mass,
                     joint_weight_share=.5, gap_mm=p.clearance,
                     stop_travel_mm=p.seat_drop+p.guide_down_allowance,
                     mu_static=mu, mu_seating=mu, normal_stiffness_N_mm=stiffness,
                     guide_normal_N=0)
            r = evaluate(c)
            r['within_native_straight_flank_height'] = (native_flank_limit is not None
                                                       and r['settled_travel_mm'] < native_flank_limit)
            cases.append(r)
    report['mechanics'] = dict(
        owner='models.mangal_wedge.mechanics.Case/evaluate', cases=cases,
        mass_wall_kg=wall_mass, joint_weight_share=.5,
        first_contact_CAD_drop_mm=p.seat_drop,
        native_straight_flank_end_travel_mm=native_flank_limit,
        rigid_CAD_pose_normal_force_N=None,
        self_lock_threshold_mu=math.tan(math.radians(p.wedge_angle_deg)),
        assumptions='Equal end-joint load sharing; two symmetric faces; dry-friction and stiffness scenarios, unmeasured. No guide preload, impact or retained thermal preload.',
        limitations='CAD is rigid first contact, not elastic driving or measured positive normal force. Finite flanks and relief must remain engaged. No manual release guarantee after heating/cooling.')
    checks = report['checks']
    correspondence = all(checks.get(k, {}).get('status') == 'PASS' for k in
                         ('upper_v_geometry', 'seated_side_1', 'seated_side_2', 'upper_corner_relief'))
    checks['mechanical_model_correspondence'] = dict(status='PASS' if correspondence else 'FAIL',
        actual=dict(mass_wall_kg=wall_mass, angle_deg=p.wedge_angle_deg,
                    joint_weight_share=.5, first_contact_drop_mm=p.seat_drop),
        reason='Native V faces and downward seating obstruction agree with the conditional two-face model. Does not validate stiffness/friction or physical force.')
    for name, reason in dict(
        physical_assembly='No physical set assembled; continuous native CAD sweeps are separate evidence.',
        hot_performance='No heating/cooling cycle, differential expansion, warping, wear or hot-load test.',
        manual_release='No cooled physical release test; friction and retained preload unmeasured.',
        stability_strength='No loaded stability, uneven-ground, wind or structural strength acceptance.',
        manufacturing_fit='No measured stock, supplier tolerance agreement or laser-cut fit coupon.').items():
        checks[name] = dict(status='NOT_CHECKED', reason=reason)
    instructions = f'''# Мангал 2.0 — сборка и разборка

Холодная номинальная CAD-геометрия. Все размеры в мм. Две продольные стенки,
два торца с ножками, дно и четыре одинаковые плоские чеки: девять деталей.
Ориентация: X вдоль {p.length:g}; Y поперёк {p.width:g}; Z вверх.
V-вырез выполнен снизу ВЕРХНЕГО выступа продольной стенки. На него опираются
два X-угла нижней кромки верхнего окна торца. Угол каждой грани
{p.wedge_angle_deg:g}° от вертикали. Это выборка зазора в XZ; поперечный
номинальный зазор Y {p.clearance:g} суммарно остаётся. Обнуление всех люфтов не заявлено.

## Сборка

1. Удерживать первый торец вертикально.
2. Ввести обе продольные стенки в первый торец, удерживая их ПРИПОДНЯТЫМИ
   на {p.release_lift:.6f} относительно окончательного положения.
3. Ввести дно в первый торец; удерживать стенки приподнятыми.
4. Надвинуть второй торец вдоль X на выступы стенок и дна.
5. Одновременно опустить обе стенки до контакта верхних V-посадок.
6. Установить все четыре чеки прорезью вниз. Чеки удерживают торцы;
   они не задают измеренный силовой преднатяг V.

## Разборка после полного охлаждения

1. Сначала извлечь ВСЕ ЧЕТЫРЕ чеки вверх.
2. Одновременно приподнять ОБЕ продольные стенки на {p.release_lift:.6f}.
3. Удерживая стенки приподнятыми, снять второй торец вдоль +X.
4. Выдвинуть дно вдоль +X: оно съёмное после освобождения одного торца.
5. Вывести обе приподнятые стенки из первого торца вдоль +X.

Число подъёма — координата цифровой проверки, не требование выдерживать микронный
ход рукой. Поднимать до свободного выхода V, без удара и забивания. Если детали
заклинило после охлаждения, прекратить усилие; ручная разборка не подтверждена.
Приёмка натурного образца: повторяемая сборка руками без подгонки и забивания;
после согласованных циклов нагрева и полного охлаждения — повторяемая разборка
руками и съём дна, без молотка и остаточной деформации. Испытательный режим
и нагрузку согласовать отдельно. До испытаний это цифровой прототип.
'''
    manufacturing = f'''# Мангал 2.0 — изготовление опытного комплекта

Четыре уникальных DXF 1:1 в миллиметрах: side ×2, end ×2, bottom ×1, key ×4.
Исходная геометрия: models/mangal_v2/model.py; STEP — сборка девяти отдельных тел.
Материал предварительно S235JR без покрытия; номинальная толщина {p.thickness:g} мм,
плотность для расчёта массы {p.density:g} кг/м³. Это не сертификат материала.
Сварка и гибка не нужны. Удалить заусенцы и острые кромки. Не применять цинковое
или обычное лакокрасочное покрытие в нагреваемой зоне.

Ширина направляющих окон t + {p.clearance:g}; суммарный Y-зазор {p.clearance:g}.
Нижнее окно: высота 20 + {p.guide_vertical_clearance:g}; свободно снизу
{p.guide_down_allowance:g}, сверху {p.guide_up_allowance:g} в окончательной посадке.
V-грань {p.wedge_angle_deg:g}° от вертикали; короткий ход грани
{p.wedge_run_height:.6f}, разгрузка вершины радиусом {p.wedge_relief_radius:g}
целиком выше несущей кромки. Не заменять её крупной стандартной разгрузкой:
она может удалить рабочую грань. Четыре чеки сохранены, их посадочные места
смещены вниз на {p.seat_drop:.6f}. Основной верх стенок не смещён.

Ширина реза в CAD не компенсирована: компенсация принадлежит CAM изготовителя.
Компоновка layout.svg не является оптимизированным раскроем листа. Размеры
назначены как практические номиналы; численная точность BREP/STEP и проверки
проникновения не являются производственными допусками. Проба на ±0.01 мм
лишь обнаруживает геометрическую границу в CAD, не доказывает точность резки.
Проверить фактическую толщину, конусность реза, окалину и способ зачистки;
сначала изготовить купон с верхней V-посадкой и нижней направляющей на том же
листе и станке. Согласовать реальные допуски с исполнителем, затем собрать
холодный комплект. Варианты 2 и 4 мм строятся отдельными параметрическими
запусками и требуют своей проверки и купона; они не заменяются масштабированием DXF.

Условный расчёт трения использует фактический CAD-объём этой стенки и
предполагаемую плотность, равную долю веса по двум торцам, μ = 0.1/0.3/0.8,
K = 100/1000/10000 Н/мм на грань. Эти коэффициенты НЕ измерены. Порог
самоторможения симметричной модели tan({p.wedge_angle_deg:g}°) =
{math.tan(math.radians(p.wedge_angle_deg)):.6f}; окисление, перекос и остаточное
обжатие после нагрева могут изменить результат. Геометрия CAD соответствует
первому контакту; положительная сила возникает только в условной упругой модели.
Не заявляются ручная разборка после огня, прочность, ресурс или стабильность
под нагрузкой без натурной приёмки.
'''
    release = f'''# Мангал — выпуск 2.0

Отдельная модель models/mangal_v2/ и результаты output/mangal_v2/.
Предыдущие models/mangal/, models/mangal_wedge/ и их результаты не заменяются.

Изменено: нижняя кромка верхнего выступа стенки получила короткий V-вырез
{p.wedge_angle_deg:g}° от вертикали; положение верхнего выступа и его чек
понижено на {p.seat_drop:.6f}. Нижнее окно торца расширено по Z до
20 + {p.guide_vertical_clearance:g} для свободной направляющей и выхода V.
Суммарный поперечный зазор {p.clearance:g} сохранён. Основной верх стенок,
дно, чеки, девять деталей и четыре уникальных контура сохранены.
Внутри {p.length:g} × {p.width:g}, высота стенки {p.height:g}; низ дна
{p.bottom_z:g}; полезная глубина {actual['measured_parameters']['usable_depth_mm']:g}.
Цифровые проверки и условный расчёт не означают разрешение производства.
Текущие статусы и причины: report.json; порядок работы: instructions.md;
производственные ограничения: manufacturing.md.
'''
    for filename, text in [('instructions.md', instructions), ('manufacturing.md', manufacturing), ('release_notes.md', release)]:
        path = out/filename; path.write_text(text, encoding='utf-8')
        assert path.read_text(encoding='utf-8') == text
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 260">
<rect width="1000" height="260" fill="white"/><g font-family="Arial" font-size="17" fill="#243647">
<text x="25" y="30">2.0 — холодная разборка; схема движений, не масштаб</text>
<text x="25" y="85">1. Все 4 чеки ↑</text><text x="280" y="85">2. Обе стенки ↑ {p.release_lift:.4f} мм</text>
<text x="650" y="85">3. Торец 2 → +X</text><text x="25" y="165">4. Дно → +X</text>
<text x="280" y="165">5. Обе поднятые стенки → +X</text>
<text x="25" y="225">Сборка в обратном порядке; опустить обе стенки до установки чек.</text></g></svg>'''
    (out/'assembly_sequence.svg').write_text(svg, encoding='utf-8')
    report['artifacts']['documents'] = ['bom.csv', 'bom.json', 'instructions.md', 'manufacturing.md',
                                         'release_notes.md', 'assembly_sequence.svg']
