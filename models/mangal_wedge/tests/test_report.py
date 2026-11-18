"""Acceptance keeps an engineering contradiction explicit, even with green code."""
import json
import hashlib
import shutil
import subprocess
import sys

import pytest

from models.mangal_wedge.mechanics import short_taper_comparison
from models.mangal_wedge.model import run
from models.mangal_wedge import model as wedge_model


@pytest.fixture(scope='session')
def native_reference(tmp_path_factory):
    from models.mangal.model import run as run_mangal

    out=tmp_path_factory.mktemp('wedge-native-mangal')
    assert run_mangal(output_dir=out)==0
    return out


@pytest.fixture
def reference(native_reference,tmp_path):
    return shutil.copytree(native_reference,tmp_path/'reference')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def rehash_bom(reference,report):
    report['artifacts']['sha256']['bom.json']=hashlib.sha256((reference/'bom.json').read_bytes()).hexdigest()
    write_json(reference/'report.json',report)


def assert_rejected(out,reference):
    assert run(out,reference_dir=reference)==2
    result=read_json(out/'report.json')
    assert result['execution_status']=='FAIL'
    assert result['design_requirements_status']=='NOT_CHECKED'
    assert result['errors'][0]['stage']=='reference_input'
    assert result['errors'][0]['message']
    assert 'nominal' not in result and 'parameters' not in result and 'reference' not in result
    assert 'Execution=FAIL' in (out/'report.md').read_text(encoding='utf-8')


def test_short_taper_options_keep_clearance_and_stop_tradeoff_explicit():
    choices=short_taper_comparison()
    reserve=choices['reserve_stop']
    assert reserve['cold_corner_cases']==32
    assert reserve['all_cold_corners_contact_before_working_end']
    assert reserve['max_settled_travel_mm']<reserve['working_height_mm']<reserve['stop_travel_mm']
    final=choices['load_bearing_stop']
    assert final['all_tolerances_enter_parallel_land_before_stop']
    assert final['final_clearance_min_mm']==pytest.approx(.1)
    assert final['final_clearance_max_mm']==pytest.approx(.7)
    assert not final['zero_play_guaranteed']


def test_report_exports_do_not_hide_failed_design_requirements(tmp_path,native_reference):
    assert run(tmp_path,reference_dir=native_reference)==0  # execution completed, not design acceptance
    r=json.loads((tmp_path/'report.json').read_text(encoding='utf-8'))
    assert r['execution_status']=='PASS'
    assert r['design_requirements_status']=='FAIL'
    assert r['checks']['two_working_faces_force_moment_balance']['status']=='PASS'
    assert r['checks']['zero_play_and_old_stop_for_all_tolerances']['status']=='FAIL'
    assert r['checks']['hand_release_after_cooling_guaranteed']['status']=='NOT_CHECKED'
    assert len(r['friction_sweep'])==21
    assert (tmp_path/'report.md').read_text(encoding='utf-8').startswith('# Клиновое')
    assert all((tmp_path/f).stat().st_size>0 for f in (
        'angle_comparison.csv','friction_sweep.csv','sensitivity.csv','contact_scheme.svg'))
    assert r['reference']['input_sha256']=={
        name:hashlib.sha256((native_reference/name).read_bytes()).hexdigest()
        for name in ('report.json','bom.json')}
    source_report=read_json(native_reference/'report.json')
    side=next(row for row in read_json(native_reference/'bom.json') if row['part']=='side')
    assert r['parameters']['mass_wall_kg']==side['unit_mass_kg']
    assert r['parameters']['stop_travel_mm']==source_report['parameters']['clearance']


@pytest.mark.parametrize('missing',('report.json','bom.json'))
def test_missing_reference_input_is_a_technical_failure(reference,tmp_path,missing):
    (reference/missing).unlink()
    assert_rejected(tmp_path/'out',reference)


def test_default_reference_does_not_require_checkout_output(tmp_path,monkeypatch):
    monkeypatch.setattr(wedge_model,'ROOT',tmp_path)
    assert run(tmp_path/'out')==2
    assert read_json(tmp_path/'out'/'report.json')['execution_status']=='FAIL'


def test_cli_accepts_explicit_native_reference(native_reference,tmp_path):
    result=subprocess.run([sys.executable,str(wedge_model.__file__),
        '--reference-dir',str(native_reference),'--output-dir',str(tmp_path/'out')],
        capture_output=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert read_json(tmp_path/'out'/'report.json')['design_requirements_status']=='FAIL'


@pytest.mark.parametrize('mutation',('missing_source','foreign_source','geometry_fail','execution_fail',
                                    'measured_not_checked','missing_bom_hash','clearance_mismatch'))
def test_invalid_native_report_is_rejected(reference,tmp_path,mutation):
    report=read_json(reference/'report.json')
    if mutation=='missing_source':
        report['source_sha256'].pop('model.py')
    elif mutation=='foreign_source':
        report['source_sha256']['foreign_model.py']='0'*64
    elif mutation=='geometry_fail':
        report['geometry_status']='FAIL'
    elif mutation=='execution_fail':
        report['execution_status']='FAIL'
    elif mutation=='measured_not_checked':
        report['checks']['valid_single_solids']['status']='NOT_CHECKED'
    elif mutation=='missing_bom_hash':
        report['artifacts']['sha256'].pop('bom.json')
    else:
        report['parameters']['clearance']+=.1
    write_json(reference/'report.json',report)
    assert_rejected(tmp_path/'out',reference)


def test_changed_actual_owner_source_invalidates_receipt(reference,tmp_path,monkeypatch):
    owner=tmp_path/'models'/'mangal'
    owner.mkdir(parents=True)
    for source in (wedge_model.ROOT/'models'/'mangal').glob('*.py'):
        shutil.copy2(source,owner/source.name)
    changed=owner/'model.py'
    changed.write_bytes(changed.read_bytes()+b'\n# actual source mutation\n')
    monkeypatch.setattr(wedge_model,'ROOT',tmp_path)
    assert_rejected(tmp_path/'out',reference)


@pytest.mark.parametrize('mutation',('changed_bytes','rehashed_mass','duplicate_side','missing_side','nan_mass'))
def test_invalid_bom_is_rejected_even_with_updated_hash(reference,tmp_path,mutation):
    bom=read_json(reference/'bom.json')
    side=next(row for row in bom if row['part']=='side')
    if mutation=='duplicate_side':
        bom.append(side.copy())
    elif mutation=='missing_side':
        bom.remove(side)
    elif mutation=='nan_mass':
        side['unit_mass_kg']=float('nan')
    else:
        side['unit_mass_kg']*=1.1
        side['total_mass_kg']=2*side['unit_mass_kg']
    write_json(reference/'bom.json',bom)
    if mutation!='changed_bytes':
        rehash_bom(reference,read_json(reference/'report.json'))
    assert_rejected(tmp_path/'out',reference)


def test_mixed_native_variant_bom_is_rejected_after_rehash(reference,tmp_path):
    from models.mangal.model import Params,make_model
    from models.mangal.exports import export_documents

    variant=tmp_path/'variant'
    variant.mkdir()
    p=Params(thickness=4)
    export_documents(make_model(p),p,variant,{'checks':{},'artifacts':{}})
    shutil.copy2(variant/'bom.json',reference/'bom.json')
    rehash_bom(reference,read_json(reference/'report.json'))
    assert_rejected(tmp_path/'out',reference)


def test_rejected_rerun_replaces_authoritative_success_and_preserves_evidence(reference,tmp_path):
    out=tmp_path/'out'
    assert run(out,reference_dir=reference)==0
    retained={name:(out/name).read_bytes() for name in (
        'angle_comparison.csv','friction_sweep.csv','sensitivity.csv','contact_scheme.svg')}
    (reference/'bom.json').unlink()
    assert_rejected(out,reference)
    assert 'не являются результатами текущего запуска' in (out/'report.md').read_text(encoding='utf-8')
    assert all((out/name).read_bytes()==data for name,data in retained.items())
