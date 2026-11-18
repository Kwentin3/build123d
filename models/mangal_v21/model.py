"""Mangal 2.1: five plates, V seats and free lower guides; no retaining keys."""
from dataclasses import asdict, dataclass
from contextlib import chdir
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if not __package__:
    sys.path.insert(0,str(ROOT))

from build123d import Compound, Plane, Pos, export_step, extrude, import_step
from models.mangal_v2.model import Params as V2Params, make_model as make_v2, rect, release_screenshots
from models.mangal.exports import export_flat

RELEASE='2.1'
OUTPUT_DIR=ROOT/'output'/'mangal_v21'


@dataclass(frozen=True)
class Params(V2Params):
    """Editable release2.1 parameters; changing these never edits release2.0."""
    length: float = 500
    width: float = 300
    height: float = 160
    thickness: float = 3
    leg_height: float = 180
    clearance: float = .6
    bottom_gap: float = 3
    wedge_angle_deg: float = 40
    guide_vertical_clearance: float = 1.2
    guide_up_allowance: float = .7
    release_margin: float = .15
    density: float = 7850


def make_model(p=Params()):
    previous=make_v2(p)
    side=previous['profiles']['side']
    # Close the former cross-lap retaining slots. The whole upper half of
    # each upper projection is now solid; the V at its bottom is unchanged.
    for a,b in ((-p.tab_reach,0),(p.length,p.length+p.tab_reach)):
        side+=rect(a,b,p.upper_tab_base+14,p.upper_tab_base+30)
    profiles=dict(side=side,end=previous['profiles']['end'],bottom=previous['profiles']['bottom'])
    flats={n:extrude(s,amount=p.thickness) for n,s in profiles.items()}
    side_plane=Plane(origin=(0,0,0),x_dir=(1,0,0),z_dir=(0,-1,0))
    parts=[]
    for name,shape in (('side_1',side_plane*flats['side']),
        ('side_2',Pos(0,p.width+p.thickness,0)*(side_plane*flats['side']))):
        shape.label=name;parts.append(shape)
    parts.extend(s for s in previous['parts'] if s.label in ('end_1','end_2','bottom'))
    remaining=[s.label for s in parts];motions=[]
    for name,moving,delta,remove in (
        ('raise_both_sides',['side_1','side_2'],(0,0,p.release_lift),False),
        ('end_2',['end_2'],(p.tab_reach+10,0,0),True),
        ('bottom',['bottom'],(p.tab_reach+10,0,0),True),
        ('withdraw_both_sides',['side_1','side_2'],(p.tab_reach+10,0,0),True)):
        motions.append(dict(name=name,moving=moving,delta=delta,
                            fixed=[n for n in remaining if n not in moving]))
        if remove:
            for n in moving:remaining.remove(n)
    layout=[];y=0
    for name,count in (('side',2),('end',2),('bottom',1)):
        solid=flats[name];bb=solid.bounding_box()
        for i in range(count):
            q=Pos(i*(bb.size.X+12)-bb.min.X,y-bb.min.Y,0)*solid
            q.label=f'{name}_{i+1}';layout.append(q)
        y+=bb.size.Y+12
    return dict(profiles=profiles,flats=flats,parts=parts,motions=motions,layout=layout)


def step_roundtrip(m,out):
    with chdir(out):
        export_step(Compound(children=m['parts']),'assembly.step')
        restored=list(import_step('assembly.step').solids())
    differences=[]
    for a in m['parts']:
        if not restored:break
        b=min(restored,key=lambda s:(s.center()-a.center()).length);restored.remove(b)
        differences.append(abs(a.volume+b.volume-2*(a&b).volume))
    return dict(status='PASS' if len(differences)==5 and not restored and max(differences)<.01 else 'FAIL',
        actual=dict(solid_count=len(differences),symmetric_difference_mm3=differences),
        reason='Spatially matched five separate re-imported STEP solids')


def run(p=Params(),output_dir=OUTPUT_DIR,take_screenshots=False):
    from models.mangal_v21.validation import validate_geometry
    from models.mangal_v21.exports import export_documents
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    report=dict(release=RELEASE,parameters=asdict(p),checks={},artifacts={},errors=[])
    try:
        m=make_model(p)
        report['checks'].update(validate_geometry(m,p))
        report['checks']['step_roundtrip']=step_roundtrip(m,out)
        report['checks'].update(export_flat(m,p,out))
        export_documents(m,p,out,report)
        report['checks']['viewer_images']=dict(status='NOT_CHECKED',reason='Run --screenshots with OCP CAD Viewer')
        if take_screenshots:
            report['artifacts']['screenshots']=release_screenshots(m,p,out)
            report['checks']['viewer_images']=dict(status='PASS',reason='Fresh images, visual acceptance separate')
        report['checks']['visual_review']=dict(status='NOT_CHECKED',reason='Open current release PNGs')
        baseline=OUTPUT_DIR/'previous_versions_sha256.json'
        if baseline.exists():
            hashes=json.loads(baseline.read_text(encoding='utf-8'))
            changed=[n for n,h in hashes.items() if not (ROOT/n).exists()
                     or hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h]
            report['checks']['previous_versions_preserved']=dict(status='FAIL' if changed else 'PASS',
                actual=dict(files=len(hashes),changed=changed))
    except Exception as exc:
        import traceback;traceback.print_exc()
        report['errors'].append(dict(kind='technical',message=str(exc)))
    physical={'viewer_images','visual_review','physical_assembly','hot_performance',
              'manual_release','stability_strength','manufacturing_fit'}
    geometry=[v for n,v in report['checks'].items() if n not in physical]
    report['geometry_status']='FAIL' if any(v['status']=='FAIL' for v in geometry) else (
        'PASS' if geometry and all(v['status']=='PASS' for v in geometry) else 'NOT_CHECKED')
    report['execution_status']='FAIL' if report['errors'] else 'PASS'
    report['production_approval']='NOT_CHECKED'
    report['source_sha256']={s.name:hashlib.sha256(s.read_bytes()).hexdigest()
                            for s in Path(__file__).parent.glob('*.py')}
    deps=('models/mangal/model.py','models/mangal/exports.py','models/mangal/validation.py',
          'models/mangal/documentation.py','models/mangal_v2/model.py','models/mangal_wedge/mechanics.py')
    report['dependency_source_sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in deps}
    report['artifacts']['sha256']={s.name:hashlib.sha256(s.read_bytes()).hexdigest()
        for s in out.iterdir() if s.is_file() and s.suffix!='.zip'
        and s.name not in ('report.json','visual_review.json','verification.json')}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f"Release {RELEASE}: geometry={report['geometry_status']}; execution={report['execution_status']}; {out/'report.json'}")
    return 2 if report['errors'] or report['geometry_status']=='NOT_CHECKED' else 1 if report['geometry_status']=='FAIL' else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('length','width','height','thickness'):
        parser.add_argument('--'+n,type=float,default=getattr(Params(),n))
    parser.add_argument('--output-dir',type=Path,default=OUTPUT_DIR)
    parser.add_argument('--screenshots',action='store_true')
    a=parser.parse_args()
    raise SystemExit(run(Params(**{n:getattr(a,n) for n in ('length','width','height','thickness')}),a.output_dir,a.screenshots))
