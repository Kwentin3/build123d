"""Nine flat laser-cut plates; millimetres. No kerf compensation."""
from dataclasses import dataclass, asdict
import argparse
from contextlib import chdir
import csv
import hashlib
import json
import math
from pathlib import Path

from build123d import (Rectangle, Circle, Pos, Plane, Compound, GeomType, extrude,
                       ExportDXF, ExportSVG, export_step, import_step, Unit)

# Editable nominal dimensions, mm. L/W are inside faces, H is wall height.
@dataclass(frozen=True)
class Params:
    length: float = 500
    width: float = 300
    height: float = 160
    thickness: float = 3
    leg_height: float = 180
    clearance: float = .6  # total cold slot clearance, not kerf
    bottom_gap: float = 3
    key_float: float = 3  # axial clearance between end face and retaining key
    relief_radius: float = .8
    density: float = 7850  # kg/m3, provisional plain carbon steel

    @property
    def bottom_z(self): return self.leg_height + 10
    @property
    def tab_reach(self): return 3*self.thickness + self.key_float + 10
    @property
    def upper_z(self): return self.leg_height + 110
    @property
    def lower_z(self): return self.leg_height + 35
    @property
    def key_x(self): return self.thickness + self.key_float

    def validate(self):
        if not all(math.isfinite(v) and v > 0 for v in asdict(self).values()):
            raise ValueError('All parameters must be finite and positive')
        if not (350 <= self.length <= 700 and 220 <= self.width <= 450
                and 155 <= self.height <= 220 and 2 <= self.thickness <= 5
                and 100 <= self.leg_height <= 250 and .4 <= self.clearance <= 1.2
                and 3 <= self.bottom_gap <= 6 and self.relief_radius <= 1):
            raise ValueError('Outside supported prototype envelope; redesign and validation required')


def rect(x0, x1, y0, y1):
    return Pos((x0+x1)/2, (y0+y1)/2) * Rectangle(x1-x0, y1-y0)


def relieved_slot(x0, x1, y0, y1, r):
    """Explicit dogbones avoid relying on an impossible sharp laser corner."""
    s = rect(x0, x1, y0, y1)
    for x in (x0, x1):
        for y in (y0, y1): s += Pos(x,y)*Circle(r)
    return s


def make_model(p=Params()):
    p.validate()
    L,W,H,t,B,c = p.length,p.width,p.height,p.thickness,p.leg_height,p.clearance
    r,g,R = p.relief_radius,p.bottom_gap,p.tab_reach
    side = rect(0,L,B,B+H)
    for a,b in ((-R,0),(L,L+R)):
        side += rect(a,b,p.lower_z,p.lower_z+20)
        side += rect(a,b,p.upper_z,p.upper_z+30)
    # Cross-lap retaining keys: top-open in tongue, bottom-open in key.
    key_positions = (-t-p.key_float-t, L+t+p.key_float)
    for x in key_positions:
        side -= relieved_slot(x-c/2,x+t+c/2,p.upper_z+15,p.upper_z+31,r)
    for i in range(9):
        x = L*(i+1)/10
        side -= rect(x-5,x+5,B+H-8,B+H+1)
    for i in range(12):
        side -= Pos(L*(i+1)/13,B+30)*Circle(5)
    end = rect(-t-20,W+t+20,B,B+H)
    # End frames are single plates: two broad legs, no separate feet.
    end += rect(-t-20,35,0,B+5)
    end += rect(W-35,W+t+20,0,B+5)
    end += rect(-t-20,W+t+20,B-35,B+5)
    for y in (-t/2,W+t/2):
        for z,h in ((p.lower_z,20),(p.upper_z,30)):
            end -= relieved_slot(y-(t+c)/2,y+(t+c)/2,z,z+h+c,r)
    for y in (.3*W,.7*W):
        end -= relieved_slot(y-17,y+17,p.bottom_z,p.bottom_z+t+c,r)
    for y in (.2*W,.4*W,.6*W,.8*W):
        end -= Pos(y,B+30)*Circle(5)
    bottom = rect(g,L-g,g,W-g)
    for y in (.3*W,.7*W):
        bottom += rect(-t,L+t,y-15,y+15)
    key = rect(-15,15,0,30) - relieved_slot(-(t+c)/2,(t+c)/2,-1,15,r)
    profiles = dict(side=side,end=end,bottom=bottom,key=key)
    flats = {n:extrude(s,amount=t) for n,s in profiles.items()}
    # Plane mappings: local(u,v,w) -> world(x,y,z).
    side_plane = Plane(origin=(0,0,0),x_dir=(1,0,0),z_dir=(0,-1,0))
    end_plane = Plane(origin=(0,0,0),x_dir=(0,1,0),z_dir=(1,0,0))
    parts=[]
    def add(name, shape):
        shape.label=name
        parts.append(shape)
    add('side_1',side_plane*flats['side'])
    add('side_2',Pos(0,W+t,0)*(side_plane*flats['side']))
    add('end_1',Pos(-t,0,0)*(end_plane*flats['end']))
    add('end_2',Pos(L,0,0)*(end_plane*flats['end']))
    add('bottom',Pos(0,0,p.bottom_z)*flats['bottom'])
    for i,(x,y) in enumerate(((key_positions[0],-t/2),(key_positions[0],W+t/2),
                              (key_positions[1],-t/2),(key_positions[1],W+t/2)),1):
        add(f'key_{i}',Pos(x,y,p.upper_z)*(end_plane*flats['key']))
    # Reverse of assembly. Exact translation envelopes checked by validator.
    motions=[]
    fixed=[q.label for q in parts]
    for name,delta in [('key_3',(0,0,40)),('key_4',(0,0,40)),
                       ('end_2',(R+10,0,0)),('bottom',(R+10,0,0)),
                       ('key_1',(0,0,40)),('key_2',(0,0,40)),
                       ('side_1',(R+10,0,0)),('side_2',(R+10,0,0))]:
        fixed.remove(name)
        motions.append(dict(name=name,moving=[name],delta=delta,fixed=fixed.copy()))
    layout=[]
    # Simple rows, deliberately not nesting optimization.
    y=0
    for name,count in [('side',2),('end',2),('bottom',1),('key',4)]:
        shape=flats[name]; bb=shape.bounding_box()
        for i in range(count):
            placed=Pos(i*(bb.size.X+12)-bb.min.X,y-bb.min.Y,0)*shape
            placed.label=f'{name}_{i+1}'
            layout.append(placed)
        y+=bb.size.Y+12
    return dict(profiles=profiles,parts=parts,flats=flats,layout=layout,motions=motions)


def screenshots(model,out):
    from ocp_vscode import Camera, get_port, show, save_screenshot, status
    from PIL import Image
    port=get_port()
    if port is None: raise RuntimeError('Start OCP CAD Viewer')
    paths=[]
    for name,shapes,camera in [('assembly_iso',model['parts'],Camera.ISO),
                               ('assembly_top',model['parts'],Camera.TOP),
                               ('layout',model['layout'],Camera.TOP)]:
        palette={'side':'#687F91','end':'#B18A5B','bottom':'#666666','key':'#C9A240'}
        show(*shapes,names=[s.label for s in shapes],
             colors=[palette[s.label.split('_')[0]] for s in shapes],
             port=port,reset_camera=camera,ortho=True,transparent=False,
             glass=False,axes=False,axes0=False,grid=(False,False,False))
        path=out/(name+'.png')
        path.unlink(missing_ok=True)
        save_screenshot(str(path),port=port,timeout_s=10)
        with Image.open(path) as im: im.verify()
        paths.append(str(path))
    return paths


def run(p=Params(),output_dir=None,take_screenshots=False):
    if __package__:
        from .validation import validate_geometry
    else:
        from validation import validate_geometry
    out=Path(output_dir or Path(__file__).resolve().parents[2]/'output'/'mangal').resolve()
    out.mkdir(parents=True,exist_ok=True)
    report=dict(parameters=asdict(p),checks={},artifacts={},errors=[])
    try:
        m=make_model(p)
        report['checks'].update(validate_geometry(m,p))
        parts={s.label:s for s in m['parts']}
        vents=[f for n in ('side_1','side_2','end_1','end_2')
               for f in parts[n].faces().filter_by(GeomType.CYLINDER)
               if abs(f.radius-5)<1e-6]
        report['checks']['ventilation_geometry']={'status':'PASS' if len(vents)==32 else 'FAIL',
            'actual':{'holes':len(vents),'diameter_mm':10,'open_area_mm2':len(vents)*math.pi*25},
            'reason':'Geometry only; draft, ash blockage and combustion performance not tested'}
        skewer_evidence=[]
        for n,y in (('side_1',-p.thickness/2),('side_2',p.width+p.thickness/2)):
            solid=parts[n].solids()[0]
            for i in range(1,10):
                x=p.length*i/10; z=p.leg_height+p.height
                skewer_evidence.append(not solid.is_inside((x,y,z-4))
                    and solid.is_inside((x,y,z-9))
                    and solid.is_inside((x-10,y,z-4))
                    and solid.is_inside((x+10,y,z-4)))
        report['checks']['skewer_notches']={'status':'PASS' if all(skewer_evidence) else 'FAIL',
            'actual':{'opposed_pairs':9,'nominal_width_mm':10,'nominal_depth_mm':8,
                      'pitch_mm':p.length/10,'native_point_probes':skewer_evidence},
            'reason':'Nominal recess geometry; actual skewers and loaded use not tested'}
        report['checks']['flat_storage']={'status':'PASS','actual':{
            'ideal_stack_envelope_mm':[max(s.bounding_box().size.X for s in m['flats'].values()),
                max(s.bounding_box().size.Y for s in m['flats'].values()),len(m['parts'])*p.thickness]},
            'reason':'All nine plates may be stacked parallel; no case, straps or handling clearance included'}
        report['actual']={'assembly_bounds_mm':list(Compound(children=m['parts']).bounding_box().size),
                         'usable_depth_above_bottom_mm':p.leg_height+p.height-p.bottom_z-p.thickness}
        with chdir(out):
            export_step(Compound(children=m['parts']),'assembly.step')
            imported=import_step('assembly.step')
        original=m['parts']; received=list(imported.solids())
        step_ok=(len(received)==len(original) and all(s.is_valid for s in received)
                 and abs(sum(s.volume for s in original)-sum(s.volume for s in received))<.01)
        # Match unordered imported solids spatially and compare symmetric difference.
        differences=[]
        remaining=received.copy()
        for a in original:
            if not remaining: break
            b=min(remaining,key=lambda s:(s.center()-a.center()).length)
            remaining.remove(b)
            differences.append(abs(a.volume+b.volume-2*(a&b).volume))
        step_ok=step_ok and len(differences)==len(original) and max(differences)<.01
        report['checks']['step_roundtrip']={'status':'PASS' if step_ok else 'FAIL',
            'actual':{'solids':len(received),'symmetric_difference_mm3':differences}}
        if __package__:
            from .exports import export_flat, export_documents
        else:
            from exports import export_flat, export_documents
        report['checks'].update(export_flat(m,p,out))
        export_documents(m,p,out,report)
        report['checks']['viewer_images']={'status':'NOT_CHECKED','reason':'Run --screenshots with OCP CAD Viewer'}
        if take_screenshots:
            try:
                report['artifacts']['screenshots']=screenshots(m,out)
                report['checks']['viewer_images']={'status':'PASS','reason':'Fresh PNGs, visual review separate'}
            except Exception as exc:
                report['errors'].append({'kind':'technical','stage':'viewer','message':str(exc)})
        report['checks']['visual_review']={'status':'NOT_CHECKED','reason':'Agent must open current PNGs'}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        report['errors'].append({'kind':'technical','message':str(exc)})
    mandatory=[n for n in report['checks'] if n.startswith(('motion_','dxf_'))]
    mandatory+=['valid_single_solids','flat_closed_profiles','dimensions','assembled_no_interference',
                'step_roundtrip','sheet_thickness','part_inventory','keys_restrain_end']
    report['geometry_status']=('FAIL' if any(c['status']=='FAIL' for c in report['checks'].values()) else
        'PASS' if all(report['checks'].get(n,{}).get('status')=='PASS' for n in mandatory)
        and len([n for n in mandatory if n.startswith('motion_')])==8 else 'NOT_CHECKED')
    report['execution_status']='FAIL' if report['errors'] else 'PASS'
    report['production_approval']='NOT_CHECKED'
    report['source_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                            for f in Path(__file__).parent.glob('*.py')}
    report['artifacts']['sha256']={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()
        for f in out.rglob('*') if f.is_file() and f.name not in ('report.json','visual_review.json')}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Report: {out/'report.json'} geometry={report['geometry_status']} execution={report['execution_status']}")
    return 2 if report['errors'] or report['geometry_status']=='NOT_CHECKED' else 1 if report['geometry_status']=='FAIL' else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('length','width','height','thickness'):
        parser.add_argument('--'+name,type=float,default=getattr(Params(),name))
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--screenshots',action='store_true')
    args=parser.parse_args()
    raise SystemExit(run(Params(**{n:getattr(args,n) for n in ('length','width','height','thickness')}),args.output_dir,args.screenshots))
