"""Manufacturing exports and bounded evidence for the flat-plate prototype."""
import csv
import json
import math
from pathlib import Path

import ezdxf
from build123d import Axis, CenterOf, Compound, ExportDXF, ExportSVG, Face, Unit, Wire, import_dxf


SOURCES = [
    ('Hawthorn: detachable corner slots and bottom tabs, 4 mm steel',
     'https://www.metalplasmacutting.co.uk/metalwork/p/hawthorn-slot-together-fire-pit'),
    ('Upper Cut FlatMate: five flat plates in 3 mm mild steel',
     'https://www.uppercutco.com.au/flat-pack-fire-pit'),
    ('SendCutSend: individual and stacked tab/slot tolerances',
     'https://sendcutsend.com/blog/how-to-add-precision-to-your-sheet-metal-parts/'),
    ('SendCutSend: cutting capabilities and nominal geometry / kerf compensation',
     'https://sendcutsend.com/services/sheet-cutting/'),
    ('Protolabs: notch and tab proportions',
     'https://www.protolabs.com/resources/blog/designing-sheet-metal-notches-and-tabs/'),
    ('Next Day Laser: minimum features, internal radii and reliefs',
     'https://www.nextdaylaser.co.uk/guides/designing-for-laser-cutting/'),
    ('Steel Construction Institute P080: elevated-temperature expansion',
     'https://www.steelconstruction.info/images/d/da/SCI_P80.pdf'),
]


def _entity_key(e):
    """Canonical geometry, excluding DXF handles, layers and provenance."""
    def xyz(v): return tuple(round(float(x), 6) for x in v)
    kind = e.dxftype()
    if kind == 'LINE':
        return kind, tuple(sorted((xyz(e.dxf.start), xyz(e.dxf.end))))
    if kind == 'CIRCLE':
        return kind, xyz(e.dxf.center), round(e.dxf.radius, 6)
    if kind == 'ARC':
        return (kind, xyz(e.dxf.center), round(e.dxf.radius, 6),
                round(e.dxf.start_angle % 360, 6), round(e.dxf.end_angle % 360, 6))
    raise ValueError(f'Unexpected cutting entity {kind}')


def export_flat(m, p, out):
    out = Path(out)
    checks = {}
    for name, profile in m['profiles'].items():
        path = out / f'{name}.dxf'
        exporter = ExportDXF(unit=Unit.MM)
        exporter.add_shape(profile.wires())
        exporter.write(path)
        doc = ezdxf.readfile(path)
        entities = list(doc.modelspace())
        keys = [_entity_key(e) for e in entities]
        audit = doc.audit()
        imported = import_dxf(path)
        wires = list(Wire.combine(imported, tol=1e-5))
        src_bb, dst_bb = profile.bounding_box(), Compound(children=imported).bounding_box()
        bbox_error = max(abs(getattr(getattr(src_bb, bound), axis)
                             - getattr(getattr(dst_bb, bound), axis))
                         for bound in ('min', 'max') for axis in ('X', 'Y'))
        # Each profile has one connected planar face, with zero or more holes.
        areas = sorted((abs(Face(w).area) for w in wires), reverse=True)
        area = areas[0] - sum(areas[1:]) if areas else 0
        original_area = profile.area
        original_wires = len(profile.wires())
        closed = bool(wires) and all(w.is_closed for w in wires)
        ok = (int(doc.header['$INSUNITS']) == 4 and not audit.errors
              and len(keys) == len(set(keys)) and closed
              and len(wires) == original_wires and abs(area-original_area) < .01
              and bbox_error < 1e-4)
        checks[f'dxf_{name}'] = {
            'status': 'PASS' if ok else 'FAIL',
            'actual': dict(unit_code=int(doc.header['$INSUNITS']), scale=1,
                           entities=len(entities), duplicate_entities=len(keys)-len(set(keys)),
                           audit_errors=len(audit.errors), closed=closed, bbox_error_mm=bbox_error,
                           wire_count=len(wires), expected_wire_count=original_wires,
                           imported_area_mm2=area, source_area_mm2=original_area),
        }
    # Export only the bottom XY face of each placed solid: no doubled back edges.
    svg = ExportSVG(unit=Unit.MM, scale=1, margin=10, fill_color=None,
                    line_color=(0, 0, 0), line_weight=.15)
    for solid in m['layout']:
        svg.add_shape(solid.faces().sort_by(Axis.Z)[0].wires())
    svg.write(out / 'layout.svg')
    checks['flat_layout'] = {'status': 'PASS', 'actual': {
        'parts': len(m['layout']), 'unit': 'mm', 'scale': 1,
        'method': 'native SVG; one bottom planar face per placed plate; contours only'},
        'reason': 'Physical-size layout; no sheet-stock nesting optimization'}
    return checks


def export_documents(m, p, out, report):
    out = Path(out)
    rows = []
    for name, quantity in [('side', 2), ('end', 2), ('bottom', 1), ('key', 4)]:
        solid = m['flats'][name]
        bb = solid.bounding_box()
        mass = solid.volume*p.density*1e-9
        rows.append(dict(part=name, quantity=quantity, material='S235JR (provisional)',
                         finish='raw uncoated; no zinc coating', thickness_mm=p.thickness,
                         width_mm=bb.size.X, height_mm=bb.size.Y,
                         area_mm2=m['profiles'][name].area,
                         volume_mm3=solid.volume, density_kg_m3=p.density,
                         unit_mass_kg=mass, total_mass_kg=quantity*mass,
                         cutting_file=f'{name}.dxf'))
    (out/'bom.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (out/'bom.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    total_volume = sum(s.volume for s in m['parts'])
    mass = total_volume*p.density*1e-9
    com = [sum(s.volume*getattr(s.center(CenterOf.MASS), a) for s in m['parts'])/total_volume
           for a in ('X', 'Y', 'Z')]
    contacts = [v.center() for s in m['parts'] for v in s.vertices()
                if abs(v.center().Z) < 1e-6]
    footprint = [min(v.X for v in contacts), max(v.X for v in contacts),
                 min(v.Y for v in contacts), max(v.Y for v in contacts)]
    margin = min(com[0]-footprint[0], footprint[1]-com[0],
                 com[1]-footprint[2], footprint[3]-com[1])
    report['checks']['static_estimate'] = {
        'status': 'NOT_CHECKED', 'actual': dict(mass_kg=mass, center_of_mass_mm=com,
            support_bounds_xy_mm=footprint, unloaded_vertical_projection_margin_mm=margin,
            ideal_tipping_angle_degrees=math.degrees(math.atan2(margin, com[2]))),
        'reason': 'Analytical unloaded estimate on rigid horizontal ground only; no load, wind, '
                  'uneven-ground, joint-flexibility or physical stability verification'}
    strain = 14e-6*580
    expansion = dict(assumed_alpha_per_K=14e-6, assumed_delta_T_K=580,
                     nominal_length_expansion_mm=p.length*strain,
                     nominal_width_expansion_mm=p.width*strain,
                     bottom_total_edge_gap_mm=2*p.bottom_gap,
                     retaining_key_axial_float_mm=p.key_float)
    report['checks']['thermal_estimate'] = {
        'status': 'NOT_CHECKED', 'actual': expansion,
        'reason': 'Free-expansion estimate for a 20 to 600 C scenario. It does not verify '
                  'differential heating, local bottom-tab travel, restrained expansion or warping.'}
    for name, reason in {
        'hot_strength': 'No thermo-mechanical calculation or heated load test',
        'service_durability': 'No firing/cooling cycle, corrosion or wear tests',
        'manufacturing_fit': 'No supplier tolerance agreement, measured stock or cut coupon',
        'physical_assembly': 'CAD translation checks do not replace actual assembly and handling',
    }.items():
        report['checks'][name] = {'status': 'NOT_CHECKED', 'reason': reason}

    manufacturing = f'''# Manufacturing notes — prototype, not production approval

Units are millimetres. Four unique DXF files contain cutting contours at 1:1.
Cut quantities: side 2, end 2, bottom 1, key 4; nine plates total.
Material is provisionally raw uncoated S235JR, thickness {p.thickness:g} mm,
density {p.density:g} kg/m3. Material grade and actual sheet thickness require shop confirmation.
No welding or bending is specified. Deburr all edges; remove sharp handling edges.
Do not add kerf compensation in CAD; the cutter owns process compensation.
No sheet format, nesting yield, cutting cost or supplier capability is approved.

The nominal slot width is t + {p.clearance:g} mm (total clearance, not per side).
Relief radius is {p.relief_radius:g} mm. These are prototype settings, not a universal
laser-cutting tolerance guarantee. Retain the explicit corner reliefs; agree their
capability with the shop. Cut a fit coupon using the actual stock and process before
cutting the full set. Check fit after the same deburring/finishing operation.
CAD modelled perfect geometry does not verify actual fit, dross, taper or sheet variation.
Use uncoated stock around the fire; galvanized or ordinary painted stock is not specified.

Nominal BOM mass: {mass:.3f} kg; actual stock, finish and processing change this value.
STEP is the assembly reference. layout.svg is a physical-size overview, not an optimized
sheet nesting. SVG labels and the separate assembly diagram are not cutting features.
'''
    instructions = '''# Assembly and use — prototype

1. Lay out two long side plates, two end frames, one bottom and four retaining keys.
2. Support the first end frame upright. Insert both side plates' tongues through its
   matching lower and upper slots; install the two keys downward into upper tongue notches.
3. Slide the bottom along the enclosure and locate its two tabs in the first end frame.
4. Slide the second end frame onto side tongues and bottom tabs; install its two keys.
5. Check that every tongue and bottom tab is seated and all four keys are fully down.
   Check all four feet on a rigid horizontal surface before loading. Keys retain the ends;
   they are separate loose pieces. No fasteners, welding or bends are part of this design.

Disassembly is the reverse: cool completely, remove the second end's keys, slide that
end off, withdraw the bottom, then remove the first end's keys and withdraw side plates.
Do not force heat-distorted joints. Never lift or carry a hot or fuel-loaded assembly.
The diagram is schematic; STEP and validated CAD motions define exact geometry.

Use only outdoors on a stable non-combustible surface. Hot metal, falling embers and
the open bottom/ground region require operator care; this prototype has no certification.
No maximum fuel/food load, resistance to tipping, fire clearance, service life or safe
temperature has been verified. Physical cold assembly and supervised firing tests remain.
'''
    research = '''# Research and engineering boundary

Commercial flat-pack fire pits support a five-main-plate, detachable slot-and-tab
concept. They do not prove this prototype's dimensions, temperatures or durability.
SendCutSend publishes about +/-0.127 mm individual laser dimensions and +/-0.254 mm
tab/slot stack-up; larger-part allowances can be greater. Nominal thickness is not an
actual stock measurement. The selected clearance therefore requires a shop coupon.
Protolabs recommends tab widths at least twice sheet thickness. Next Day Laser suggests
internal radii around half thickness or explicit corner reliefs: this design uses reliefs,
whose size must be accepted by the cutter. Published vendor rules vary by process.

SCI P080 gives about 14e-6/K as a useful steel expansion approximation at elevated
temperatures. With the deliberately assumed 580 K rise, free growth is approximately
''' + f'''{expansion['nominal_length_expansion_mm']:.2f} mm along length and
{expansion['nominal_width_expansion_mm']:.2f} mm along width. Nominal bottom edge gaps
total {2*p.bottom_gap:g} mm and key axial float is {p.key_float:g} mm. These values are
recorded for review, not declared sufficient: bottom tabs, temperature differences and
local restraints govern actual freedom to move. Thickness-fit clearance is not a substitute
for longitudinal thermal travel. CAD overlap/clearance checks are cold geometry only.

The report includes computed mass/centre of mass and an ideal unloaded tipping estimate.
Neither static estimates nor successful exports validate hot strength or safety.
There is no FEA, thermal field solution, actual laser-cut coupon, loaded stability test,
physical assembly acceptance, or firing/cooling-cycle test in this delivery.

Sources (manufacturer/institution pages reviewed 2026-11-06):

''' + '\n'.join(f'- {title}: {url}' for title, url in SOURCES) + '\n'
    for name, content in [('manufacturing.md', manufacturing), ('instructions.md', instructions),
                          ('research.md', research)]:
        path = out/name
        path.write_text(content, encoding='utf-8')
        if path.read_text(encoding='utf-8') != content:
            raise RuntimeError(f'UTF-8 document readback failed: {name}')
    # Schematic only, deliberately separate from the native physical cutting layout.
    (out/'assembly.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="300" viewBox="0 0 1000 300">
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="black"/></marker></defs>
<g fill="none" stroke="black" stroke-width="2"><rect x="30" y="85" width="60" height="150"/><rect x="170" y="100" width="230" height="35"/><rect x="170" y="190" width="230" height="35"/><rect x="450" y="140" width="230" height="45"/><rect x="760" y="85" width="60" height="150"/>
<path d="M160 160 H100 M440 160 H410 M745 160 H690" marker-end="url(#arrow)"/></g>
<g font-family="sans-serif" font-size="18"><text x="25" y="55">1. First end</text><text x="180" y="55">2. Two sides + 2 keys</text><text x="470" y="55">3. Bottom</text><text x="730" y="55">4. End + 2 keys</text><text x="30" y="280">SCHEMATIC ONLY — see STEP for geometry. Disassemble after cooling, in reverse order.</text></g></svg>''', encoding='utf-8')
    report['artifacts']['documents'] = ['bom.csv', 'bom.json', 'manufacturing.md',
                                        'instructions.md', 'research.md', 'assembly.svg', 'layout.svg']
