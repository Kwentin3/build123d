"""Mangal 2.0: gravity-seated upper V-notch, free lower guide. All units mm."""
from dataclasses import dataclass, fields, asdict
from contextlib import chdir
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if not __package__:
    sys.path.insert(0,str(ROOT))

from build123d import Box, Circle, Compound, Plane, Polygon, Pos, export_step, extrude, import_step
from models.mangal.model import Params as PreviousParams, make_model as make_previous, rect, relieved_slot
from models.mangal.exports import export_flat

RELEASE='2.0'
OUTPUT_DIR=ROOT/'output'/'mangal_v2'


@dataclass(frozen=True)
class Params(PreviousParams):
    wedge_angle_deg: float = 40  # EACH straight face measured FROM VERTICAL
    guide_vertical_clearance: float = 1.2  # total lower tab vertical travel
    guide_up_allowance: float = .7  # .5 remaining below at nominal seated pose
    release_margin: float = .15  # raised V mouth clears the end lip before X withdrawal

    @property
    def seat_drop(self): return self.clearance/(2*math.tan(math.radians(self.wedge_angle_deg)))
    @property
    def upper_tab_base(self): return self.upper_z-self.seat_drop
    @property
    def release_lift(self): return self.seat_drop+self.release_margin
    @property
    def wedge_relief_radius(self): return self.thickness*.1
    @property
    def wedge_run_height(self):
        return max(self.thickness/4,self.seat_drop+self.wedge_relief_radius+.1)
    @property
    def guide_down_allowance(self): return self.guide_vertical_clearance-self.guide_up_allowance

    def validate(self):
        super().validate()
        if not all(math.isfinite(v) and v>0 for v in (
            self.wedge_angle_deg,self.guide_vertical_clearance,self.guide_up_allowance,self.release_margin)):
            raise ValueError('Finite positive v2 parameters required')
        if not 35<=self.wedge_angle_deg<=45:
            raise ValueError('Released V-angle envelope is 35..45 degrees from vertical')
        if not 1<=self.guide_vertical_clearance<=1.2 or self.guide_down_allowance<=0:
            raise ValueError('Lower guide needs 1..1.2mm total travel and positive clearance below')
        if self.guide_up_allowance<=self.release_lift:
            raise ValueError('Lower guide roof blocks wedge release')
        if self.upper_tab_base+30+self.release_lift>=self.upper_z+30+self.clearance:
            raise ValueError('Upper window roof blocks wedge release')
        if self.thickness+self.clearance-2*self.wedge_run_height*math.tan(math.radians(self.wedge_angle_deg))<=0:
            raise ValueError('V throat must stay open')


def make_model(p=Params()):
    p.validate()
    old=PreviousParams(**{f.name:getattr(p,f.name) for f in fields(PreviousParams)})
    original=make_previous(old)
    L,W,t,c,R=p.length,p.width,p.thickness,p.clearance,p.tab_reach
    side=original['profiles']['side']
    # Reuse the existing independent plate shapes; change only upper projections,
    # their key slots, and lower receiver windows. Existing models stay untouched.
    for a,b in ((-R,0),(L,L+R)):
        side-=rect(a,b,p.upper_z-.001,p.upper_z+30.001)
        side+=rect(a,b,p.upper_tab_base,p.upper_tab_base+30)
    key_x=(-t-p.key_float-t,L+t+p.key_float)
    for x in key_x:
        side-=relieved_slot(x-c/2,x+t+c/2,p.upper_tab_base+15,p.upper_tab_base+31,p.relief_radius)
    for cx in (-t/2,L+t/2):
        mouth=t+c
        throat=mouth-2*p.wedge_run_height*math.tan(math.radians(p.wedge_angle_deg))
        z=p.upper_tab_base
        cut=Polygon((cx-mouth/2,z),(cx+mouth/2,z),
                    (cx+throat/2,z+p.wedge_run_height),
                    (cx-throat/2,z+p.wedge_run_height),align=None)
        # Small corner reliefs at the throat, entirely above the bearing edge;
        # the original .8mm slot relief would remove the working V faces here.
        for x in (cx-throat/2,cx+throat/2):
            cut+=Pos(x,z+p.wedge_run_height)*Circle(p.wedge_relief_radius)
        side-=cut
    end=original['profiles']['end']
    for y in (-t/2,W+t/2):
        # First fill the previous hole, then cut a clean expanded one. Merely
        # overlaying two relieved holes would leave redundant scalloped corners.
        end+=relieved_slot(y-(t+c)/2,y+(t+c)/2,p.lower_z,p.lower_z+20+c,p.relief_radius)
        end-=relieved_slot(y-(t+c)/2,y+(t+c)/2,p.lower_z-p.guide_down_allowance,
                          p.lower_z+20+p.guide_up_allowance,p.relief_radius)
    profiles=dict(side=side,end=end,bottom=original['profiles']['bottom'],key=original['profiles']['key'])
    flats={name:extrude(profile,amount=t) for name,profile in profiles.items()}
    side_plane=Plane(origin=(0,0,0),x_dir=(1,0,0),z_dir=(0,-1,0))
    end_plane=Plane(origin=(0,0,0),x_dir=(0,1,0),z_dir=(1,0,0))
    parts=[]
    def add(name,shape):
        shape.label=name;parts.append(shape)
    add('side_1',side_plane*flats['side'])
    add('side_2',Pos(0,W+t,0)*(side_plane*flats['side']))
    add('end_1',Pos(-t,0,0)*(end_plane*flats['end']))
    add('end_2',Pos(L,0,0)*(end_plane*flats['end']))
    add('bottom',Pos(0,0,p.bottom_z)*flats['bottom'])
    for i,(x,y) in enumerate(((key_x[0],-t/2),(key_x[0],W+t/2),
                             (key_x[1],-t/2),(key_x[1],W+t/2)),1):
        add(f'key_{i}',Pos(x,y,p.upper_tab_base)*(end_plane*flats['key']))
    motions=[];remaining=[s.label for s in parts]
    def motion(name,moving,delta,remove=True):
        fixed=[n for n in remaining if n not in moving]
        motions.append(dict(name=name,moving=moving,delta=delta,fixed=fixed))
        if remove:
            for n in moving:remaining.remove(n)
    for i in range(1,5):motion(f'key_{i}',[f'key_{i}'],(0,0,40))
    motion('raise_both_sides',['side_1','side_2'],(0,0,p.release_lift),False)
    motion('end_2',['end_2'],(R+10,0,0))
    motion('bottom',['bottom'],(R+10,0,0))
    motion('withdraw_both_sides',['side_1','side_2'],(R+10,0,0))
    layout=[];y=0
    for name,count in (('side',2),('end',2),('bottom',1),('key',4)):
        solid=flats[name];bb=solid.bounding_box()
        for i in range(count):
            q=Pos(i*(bb.size.X+12)-bb.min.X,y-bb.min.Y,0)*solid;q.label=f'{name}_{i+1}'
            layout.append(q)
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
    ok=len(differences)==9 and not restored and max(differences)<.01
    return dict(status='PASS' if ok else 'FAIL',actual={'solid_count':len(differences),
                'symmetric_difference_mm3':differences},reason='Independent spatial matching of nine re-imported STEP solids')


def release_screenshots(m,p,out):
    """Existing OCP viewer plus an explicitly cropped display-only XZ section."""
    from ocp_vscode import Camera, Render, get_port, show, save_screenshot
    from PIL import Image
    port=get_port()
    if port is None:raise RuntimeError('Start OCP CAD Viewer')
    paths=[]
    palette={'side':'#687F91','end':'#B18A5B','bottom':'#666666','key':'#C9A240'}
    def capture(name,objects,names,colors,camera):
        options=dict(names=names,colors=colors,modes=[Render.ALL]*len(objects),port=port,
            ortho=True,transparent=False,glass=False,axes=False,axes0=False,
            grid=(False,False,False),clip_slider_0=0,clip_slider_1=0,clip_slider_2=0,
            clip_planes=False,zoom=1)
        # Presets retain camera scale; reset first so a small joint section does
        # not inherit the layout's kilometre-like viewing distance. Explicitly
        # reset all clip planes: viewer UI state may otherwise hide real parts.
        show(*objects,reset_camera=Camera.RESET,**options)
        show(*objects,reset_camera=camera,**options)
        path=out/(name+'.png');path.unlink(missing_ok=True)
        save_screenshot(str(path),port=port,timeout_s=10)
        with Image.open(path) as im:im.verify()
        paths.append(str(path))
    for name,objects,camera in (('assembly_iso',m['parts'],Camera.ISO),
                                 ('assembly_top',m['parts'],Camera.TOP),
                                 ('layout',m['layout'],Camera.TOP)):
        capture(name,objects,[s.label for s in objects],
                [palette[s.label.split('_')[0]] for s in objects],camera)
    parts={s.label:s for s in m['parts']}
    band=Pos(-p.thickness/2,-p.thickness/2,p.upper_z)*Box(16,p.thickness/3,7)
    sections=[Compound(children=list(parts[n].intersect(band).solids())).translate(
        (p.thickness/2,p.thickness/2,-p.upper_z)) for n in ('side_1','end_1')]
    capture('upper_joint',sections,['Wall - display section','End - display section'],
            ['#687F91','#B18A5B'],Camera.FRONT)
    return paths


def run(p=Params(),output_dir=OUTPUT_DIR,take_screenshots=False):
    from models.mangal_v2.validation import validate_geometry
    from models.mangal_v2.exports import export_documents
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
            report['checks']['viewer_images']=dict(status='PASS',reason='Fresh PNGs; agent visual inspection recorded separately')
        report['checks']['visual_review']=dict(status='NOT_CHECKED',reason='Open this release PNGs before visual conclusions')
    except Exception as exc:
        import traceback;traceback.print_exc()
        report['errors'].append(dict(kind='technical',message=str(exc)))
    geometry=[v for n,v in report['checks'].items() if n not in (
        'viewer_images','visual_review','physical_assembly','hot_performance','manual_release',
        'stability_strength','manufacturing_fit')]
    report['geometry_status']='FAIL' if any(v['status']=='FAIL' for v in geometry) else (
        'PASS' if geometry and all(v['status']=='PASS' for v in geometry) else 'NOT_CHECKED')
    report['execution_status']='FAIL' if report['errors'] else 'PASS'
    report['production_approval']='NOT_CHECKED'
    report['source_sha256']={s.name:hashlib.sha256(s.read_bytes()).hexdigest()
                             for s in Path(__file__).parent.glob('*.py')}
    report['artifacts']['sha256']={s.name:hashlib.sha256(s.read_bytes()).hexdigest()
        for s in out.iterdir() if s.is_file() and s.name not in ('report.json','visual_review.json','verification.json')}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f"Release{RELEASE}: geometry={report['geometry_status']}; execution={report['execution_status']}; {out/'report.json'}")
    return 2 if report['errors'] or report['geometry_status']=='NOT_CHECKED' else 1 if report['geometry_status']=='FAIL' else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('length','width','height','thickness'):
        parser.add_argument('--'+name,type=float,default=getattr(Params(),name))
    parser.add_argument('--output-dir',type=Path,default=OUTPUT_DIR)
    parser.add_argument('--screenshots',action='store_true')
    a=parser.parse_args()
    raise SystemExit(run(Params(**{n:getattr(a,n) for n in ('length','width','height','thickness')}),a.output_dir,a.screenshots))
