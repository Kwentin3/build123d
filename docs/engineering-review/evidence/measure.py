import sys
sys.dont_write_bytecode = True
import argparse, hashlib, importlib.util, importlib.metadata, json
from pathlib import Path

parser = argparse.ArgumentParser(description='Measure nominal filter-holder geometry and service path.')
parser.add_argument('input_root', nargs='?', type=Path,
                    default=Path('D:/Users/Roman/Desktop/Проекты/build123d/output/issue3-worktree/output/engineering-review/pilot-input'),
                    help='Product input directory containing models/filter_holder/model.py')
parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent,
                    help='Directory for measurements.json; use a fresh directory to retain previous evidence')
args = parser.parse_args()
ROOT = args.input_root.resolve()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)

import OCP
from build123d import Box, Pos
SOURCE = ROOT / 'models/filter_holder/model.py'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location('reviewed_filter_holder', SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
parts = model.make_holder()
frame, cartridge = parts['frame'], parts['cartridge']

def bounds(s):
    bb = s.bounding_box()
    return dict(min=list(bb.min), max=list(bb.max), size=list(bb.size))

def volume(s):
    return 0.0 if s is None else s.volume

def body(s):
    return dict(valid=s.is_valid, solids=len(s.solids()), faces=len(s.faces()),
                volume_mm3=s.volume, bounds_mm=bounds(s))

# Finite probes isolate actual source-generated frame features in the relevant
# cartridge depth and width region. Report probe bounds to make scope explicit.
probes = dict(
    rails=Pos(0,0,10)*Box(80,60,8),
    backing=Pos(0,0,-10)*Box(50,60,40),
    shelf=Pos(0,-25,10)*Box(50,50,8),
    crossbar=Pos(0,42.5,10)*Box(50,15,8))
sections={name:frame & probe for name,probe in probes.items()}
rail_solids=sorted(sections['rails'].solids(),key=lambda solid:solid.bounding_box().min.X)
cb=cartridge.bounding_box()
shelf_bb=sections['shelf'].bounding_box()
bar_bb=sections['crossbar'].bounding_box()
back_bb=sections['backing'].bounding_box()
clearances=dict(left_x=cb.min.X-rail_solids[0].bounding_box().max.X,
                right_x=rail_solids[1].bounding_box().min.X-cb.max.X,
                backing_z=cb.min.Z-back_bb.max.Z,
                lower_shelf_y=cb.min.Y-shelf_bb.max.Y,
                crossbar_y=bar_bb.min.Y-cb.max.Y)
first=bar_bb.min.Y-cb.max.Y
last=bar_bb.max.Y-cb.min.Y
peak_first=bar_bb.max.Y-cb.max.Y
peak_last=bar_bb.min.Y-cb.min.Y
max_overlap=cb.size.X*cb.size.Z*bar_bb.size.Y
poses=[]
for shift in (0, 4, 4.001, 10, 45, 74, 79.999, 80, 90):
    moving = Pos(0, shift, 0) * cartridge
    poses.append(dict(shift_y_mm=shift, overlap_volume_mm3=volume(frame & moving),
                      distance_mm=frame.distance_to(moving)))
# SOURCE constructs the entire moving body as a single axis-aligned Box.
# Its exact continuous union under translation [0,90] is another Box.
b = cartridge.bounding_box()
travel = 90.0
sweep = Pos((b.min.X+b.max.X)/2, (b.min.Y+b.max.Y+travel)/2,
            (b.min.Z+b.max.Z)/2) * Box(b.size.X, b.size.Y+travel, b.size.Z)
obstruction = frame & sweep
# Localize by reproducing the explicit single crossbar, without modifying frame.
bar = Pos(0,model.CROSSBAR_Y,model.CROSSBAR_Z) * Box(
    model.FRAME_WIDTH, model.CROSSBAR_HEIGHT, model.FRAME_DEPTH)
remaining = obstruction - bar

report=dict(
    source=str(SOURCE), source_sha256=sha(SOURCE), script_sha256=sha(Path(__file__)),
    packages={'build123d':importlib.metadata.version('build123d'),'OCP':getattr(OCP,'__version__','unknown')},
    requirement=dict(direction=[0,1,0], travel_mm=90, frame_fixed=True,
                     rotation_allowed=False, xz_motion_allowed=False),
    bodies={k:body(v) for k,v in parts.items()},
    nominal_clearances_mm=clearances,
    feature_probes={name:dict(probe=bounds(probes[name]), intersection=bounds(shape))
                    for name,shape in sections.items()},
    poses=poses,
    continuous_sweep=dict(method='Exact swept union of source-defined axis-aligned rectangular Box translated along +Y, 0..90 mm',
                          bounds_mm=bounds(sweep), obstruction=body(obstruction),
                          obstruction_outside_crossbar_mm3=volume(remaining)),
    analytic_collision=dict(method='400 * max(0, min(35+s,45)-max(-35+s,39)); s in [0,90]',
                            first_contact_mm=first, positive_overlap_open_interval_mm=[first,last],
                            maximum_overlap_mm3=max_overlap, maximum_overlap_shift_closed_interval_mm=[peak_first,peak_last],
                            last_contact_mm=last),
    limitations=['Nominal rigid geometry only; no flexibility, force, loads, tolerances, material or process assessed.',
                 'No STEP export or image used; conclusions concern source-generated BREP.',
                 'External housing clearance accepted as supplied in README; external housing absent.'])
(OUT/'measurements.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))