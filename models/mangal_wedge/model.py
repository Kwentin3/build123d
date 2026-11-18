"""Reproduce the wedge investigation; no original CAD files are rewritten."""
from dataclasses import asdict, replace
import argparse
import csv
import hashlib
import json
from pathlib import Path
import math

if __package__:
    from .mechanics import Case, evaluate, sensitivity_cases, stop_tolerance_bounds, short_taper_comparison
    from .statics import (wedge_contacts, lower_shoulder, lower_stop, normal_range,
                          solve_equilibrium, maximum_upward_load)
    from .reporting import write_report
else:
    from mechanics import Case, evaluate, sensitivity_cases, stop_tolerance_bounds, short_taper_comparison
    from statics import (wedge_contacts, lower_shoulder, lower_stop, normal_range,
                         solve_equilibrium, maximum_upward_load)
    from reporting import write_report

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output'/'mangal_wedge'
ANGLES=(20,30,40)
FRICTION=(.1,.2,.3,.4,.6,.8,1.0)


def _csv(path,rows,keys):
    with path.open('w',newline='',encoding='utf-8-sig') as stream:
        w=csv.DictWriter(stream,fieldnames=keys,extrasaction='ignore')
        w.writeheader();w.writerows(rows)


def _reference_inputs(reference_dir):
    """Check the original model's receipts and measured evidence before reuse.

    These unsigned receipts establish freshness and consistency, not authenticity.
    """
    reference=Path(reference_dir)
    raw={name:(reference/name).read_bytes() for name in ('report.json','bom.json')}
    report=json.loads(raw['report.json'])
    bom=json.loads(raw['bom.json'])
    sources={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
             for f in (ROOT/'models'/'mangal').glob('*.py')}
    if not sources or report['source_sha256']!=sources:
        raise ValueError('Original mangal source set or SHA256 changed')
    if (report['execution_status']!='PASS' or report['geometry_status']!='PASS'
            or report['errors']!=[]):
        raise ValueError('Original mangal execution and geometry must be PASS without errors')
    if report['artifacts']['sha256']['bom.json']!=hashlib.sha256(raw['bom.json']).hexdigest():
        raise ValueError('Original mangal BOM SHA256 changed')
    checks=report['checks']
    for name in ('valid_single_solids','sheet_thickness','clearance_side_vertical'):
        if checks[name]['status']!='PASS':
            raise ValueError(f'Original mangal measured check must be PASS: {name}')
    if not isinstance(bom,list):
        raise ValueError('Original mangal BOM must be a list')
    sides=[row for row in bom if row['part']=='side']
    if len(sides)!=1:
        raise ValueError('Original mangal BOM must contain exactly one side row')
    side=sides[0]

    def positive(value, name):
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
            raise ValueError(f'Original mangal {name} must be finite and positive')
        return value

    def same(actual, expected, name, absolute=1e-9):
        actual=positive(actual,name)
        if not math.isclose(actual,expected,rel_tol=1e-9,abs_tol=absolute):
            raise ValueError(f'Original mangal {name} disagrees with measured report')

    p=report['parameters']
    density=positive(p['density'],'density')
    thickness=positive(p['thickness'],'thickness')
    clearance=positive(p['clearance'],'clearance')
    volumes=checks['valid_single_solids']['actual']
    volume=positive(volumes['side_1']['volume_mm3'],'side_1 volume')
    for label in ('side_1','side_2'):
        measured=volumes[label]
        if measured['valid'] is not True or measured['solid_count']!=1:
            raise ValueError(f'Original mangal {label} must be one valid solid')
        same(measured['volume_mm3'],volume,f'{label} volume',1e-5)
        same(checks['sheet_thickness']['actual'][label],thickness,f'{label} thickness')
    same(side['volume_mm3'],volume,'BOM side volume',1e-5)
    same(side['density_kg_m3'],density,'BOM side density')
    same(side['thickness_mm'],thickness,'BOM side thickness')
    if side['quantity']!=2:
        raise ValueError('Original mangal BOM side quantity must be two')
    same(side['unit_mass_kg'],volume*density*1e-9,'BOM side unit mass')
    same(side['total_mass_kg'],2*side['unit_mass_kg'],'BOM side total mass')
    travel=checks['clearance_side_vertical']
    same(travel['expected']['nominal_travel_mm'],clearance,'side vertical nominal travel')
    bracket=travel['actual']['travel_bracket_mm']
    if len(bracket)!=2:
        raise ValueError('Original mangal side vertical travel bracket must have two limits')
    for actual,expected in zip(bracket,(clearance-.01,clearance+.01)):
        same(actual,expected,'side vertical travel bracket')
    return side['unit_mass_kg'],clearance,{name:hashlib.sha256(data).hexdigest()
                                           for name,data in raw.items()}


def run(output_dir=OUT, *, reference_dir=None):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    try:
        mass,clearance,input_sha256=_reference_inputs(
            ROOT/'output'/'mangal' if reference_dir is None else reference_dir)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        result=dict(execution_status='FAIL',design_requirements_status='NOT_CHECKED',
            errors=[dict(kind='technical',stage='reference_input',message=str(exc))])
        (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (out/'report.md').write_text('# Клиновое исследование: технический сбой\n\n'
            'Execution=FAIL; design requirements=NOT_CHECKED.\n\n'
            f'Исходные данные mangal отклонены: {exc}\n\n'
            'Ранее сохранённые CSV/SVG не являются результатами текущего запуска.\n',encoding='utf-8')
        print(f"Execution=FAIL; reference input rejected: {exc}")
        return 2
    c=Case(mass_wall_kg=mass,stop_travel_mm=clearance)
    nominal=[evaluate(replace(c,angle_deg=a)) for a in ANGLES]
    # Same coefficient on both moving/limiting faces in this primary sweep.
    friction=[evaluate(replace(c,angle_deg=a,mu_static=mu,mu_seating=mu))
              for a in ANGLES for mu in FRICTION]
    sensitivity=sensitivity_cases(c)
    tolerance=[stop_tolerance_bounds(a) for a in ANGLES]
    rigid=[];crosschecks=[]
    for a in ANGLES:
        for mu in FRICTION:
            contacts=wedge_contacts(a,mu)
            lo,hi=normal_range(contacts,c.mass_wall_kg*c.gravity_m_s2*.5,'left')
            if not lo.feasible: raise RuntimeError('Symmetric contact reference infeasible')
            W=c.mass_wall_kg*c.gravity_m_s2*.5
            expected=W/(2*(math.sin(math.radians(a))+mu*math.cos(math.radians(a))))
            crossed=abs(lo.forces['left'][0]-expected)<1e-7
            predicted_unbounded=mu>=math.tan(math.radians(a))
            crossed=crossed and ((hi.status=='unbounded')==predicted_unbounded)
            retained=maximum_upward_load(contacts,W,{'left':lo.forces['left'][0],
                                                    'right':lo.forces['right'][0]})
            expected_up=W+2*lo.forces['left'][0]*(mu*math.cos(math.radians(a))-math.sin(math.radians(a)))
            crossed=crossed and retained.feasible and abs(retained.upward_load-expected_up)<1e-7
            crosschecks.append(crossed)
            rigid.append(dict(scenario='symmetric_no_guide',angle_deg=a,mu=mu,
                minimum=asdict(lo),maximum=asdict(hi),reverse_fixed_normal=asdict(retained)))
        # This is an optional, genuinely engaged X shoulder, NOT a fictitious
        # replacement for the lower slot's Y side faces.
        for e in (0,10,50,250):
            contacts=(*wedge_contacts(a,.3),lower_shoulder(1,.3))
            rigid.append(dict(scenario='conditional_X_shoulder',angle_deg=a,mu=.3,
                eccentricity_mm=e,weight_N=c.mass_wall_kg*c.gravity_m_s2,
                result=asdict(solve_equilibrium(contacts,c.mass_wall_kg*c.gravity_m_s2,eccentricity=e))))
        contacts=(*wedge_contacts(a,.3),lower_stop())
        rigid.append(dict(scenario='stop_can_bypass_wedge',angle_deg=a,
            result=asdict(solve_equilibrium(contacts,c.mass_wall_kg*c.gravity_m_s2*.5,
                fixed_normals={'left':0,'right':0}))))
    # Save per-face force, play, release, and separate imposed-stop scenarios.
    cols=['angle_deg','mu_static','mu_seating','mode','first_contact_travel_mm','settled_travel_mm',
          'free_play_mm','normal_per_face_N','weight_per_joint_N','guide_friction_N',
          'stop_reaction_N','peak_up_force_per_joint_N','initial_up_force_signed_N',
          'extra_down_force_to_force_stop_N','forced_stop_normal_per_face_N',
          'self_lock_threshold_mu','self_locking']
    _csv(out/'angle_comparison.csv',nominal,cols)
    _csv(out/'friction_sweep.csv',friction,cols)
    _csv(out/'sensitivity.csv',sensitivity,['varied_parameter','varied_value',*cols,
        'normal_stiffness_N_mm','gap_mm','stop_travel_mm','thermal_gap_change_mm',
        'guide_normal_N','retained_extra_normal_N','joint_weight_share'])
    checks={
        'sketch_gap_decreases_downward':dict(status='PASS',reason='Female notch widens downward; dg/dq=-2 tan(alpha)<0'),
        'two_working_faces_force_moment_balance':dict(status='PASS' if all(crosschecks) else 'FAIL',
            reason='21 independent Coulomb LP references crosscheck minimum normal, locking threshold and reverse force'),
        'lower_guide_included':dict(status='PASS',reason='0.6 mm vertical stroke, conditional X shoulder, separate Y bearing/friction sensitivity'),
        'tolerance_bounds_evaluated':dict(status='PASS',reason='Finished feature +/-0.15mm, stock +/-0.15mm, angle +/-1deg: illustrative envelopes'),
        'zero_play_and_old_stop_for_all_tolerances':dict(status='FAIL',reason='All three angles admit both residual play and forced interference at tolerance corners'),
        'gravity_seating_for_all_guide_loads':dict(status='FAIL',reason='Assumed guide normal60N at mu0.3 gives friction capacity18N > joint weight9.287N'),
        'no_self_lock_for_all_tested_conditions':dict(status='FAIL',reason='20/30 can lock within mu<=0.8;40 can lock at stress-test mu1.0; guide may independently bind'),
        'hand_release_after_cooling_guaranteed':dict(status='NOT_CHECKED',reason='Actual friction, retained normal, guide bearing, deformation, force target and grip unknown'),
        'actual_friction_and_stiffness':dict(status='NOT_CHECKED',reason='Both must be measured on cut/heat-cycled coupon'),
        'local_contact_stress_and_strength':dict(status='NOT_CHECKED',reason='Corner radius, contact patch, elastic/plastic contact and hot properties unknown'),
        'full_3D_contact_load_distribution':dict(status='NOT_CHECKED',reason='Planar friction-cone statics + explicit transverse bearing envelope; no elastic 6DOF solution'),
        'thermal_permanent_deformation':dict(status='NOT_CHECKED',reason='Gap and retained-normal scenarios are inputs, not predicted residual thermal state'),
        'physical_coupon_test':dict(status='NOT_CHECKED',reason='No fabricated specimen or measured forces'),
    }
    baseline=OUT/'baseline_sha256.json'
    if baseline.exists():
        receipts=json.loads(baseline.read_text(encoding='utf-8'))
        changed=[n for n,d in receipts.items() if not (ROOT/n).exists()
                 or hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=d]
        checks['previous_design_preserved']=dict(status='FAIL' if changed else 'PASS',actual=changed,
            reason='SHA256 of all 27 previous source/production files; bytecode caches excluded')
    else:
        checks['previous_design_preserved']=dict(status='NOT_CHECKED',reason='Initial baseline receipt unavailable')
    result=dict(parameters=asdict(c),reference=dict(previous_mass_kg=mass,input_sha256=input_sha256,
        mass_scope='Previous side wall is only a load proxy: new wall geometry not released',
        old_slot_width_axis='Y',old_slot_vertical_stroke_mm=.6,
        upper_lower_contact_center_spacing_mm=80,
        entrance_gap_scope='New V entrance clearance .6mm is an explicit assumption, not an existing V dimension',
        sketch='User image: female cutout widens toward lower opening; no dimensions or angle datum given'),
        nominal=nominal,friction_sweep=friction,sensitivity=sensitivity,
        tolerance_bounds=tolerance,rigid_contact_cases=rigid,short_taper_options=short_taper_comparison(c),checks=checks,
        execution_status='PASS',design_requirements_status='FAIL',
        decision='40deg is only the preferred coupon candidate among tested angles; no robust self-seating/no-jam guarantee. Final-stop option needs finite clearance or adjustment/compliance.',
        source_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                       for f in Path(__file__).parent.glob('*.py')})
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    write_report(out,result)
    print(f"Execution=PASS; design requirements=FAIL (identified contradiction). Report: {out/'report.md'}")
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--reference-dir',type=Path,default=ROOT/'output'/'mangal')
    args=parser.parse_args()
    raise SystemExit(run(args.output_dir,reference_dir=args.reference_dir))
