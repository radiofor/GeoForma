"""Final audit of actual completed jobs and unchanged imagery, not semantic accuracy."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoforma.raster import fingerprint
OUT=ROOT/'experiments/sam_versions'
manifest=json.loads((OUT/'manifest.json').read_text());fixtures=json.loads((OUT/'fixtures/manifest.json').read_text())
checks={'human_ground_truth_available':False,'official_public_checkpoints':11,'models':[]}
assert len(manifest['models'])==11
for image in fixtures['images']:assert fingerprint(image['path'])==image['fingerprint'],'Source changed during evaluation'
checks['source_fingerprints_unchanged']=True
for model in manifest['models']:
    name=model['id'];base=OUT/'windows'/name;r=json.loads((base/'cuda/results.json').read_text())
    assert r['ok'] and len(r['trials'])==59
    assert all(t['prompt_reuses_encoder'] and t['delete_negative_reapply_exact'] and t['coordinate_roundtrip_error_px']<1e-6 and t.get('disk_restore_exact',True) for t in r['trials'])
    assert json.loads((base/'cpu/results.json').read_text())['ok']
    assert json.loads((base/'cuda/fresh_process_restore.json').read_text())=={'ok':True,'encoder_calls':0,'pixel_exact':True,'fixture':'low_L01'}
    full=[]
    for provider,expected in [('low',9),('high',484)]:
        q=json.loads((base/('full_'+provider+'_grid8/results.json')).read_text())
        assert q['ok'] and len(q['tiles'])==expected
        assert sorted(t['tile'] for t in q['tiles'])==list(range(expected))
        assert q['total_candidates']==sum(t['count'] for t in q['tiles'])
        assert q['additional_encoder_calls']==expected
        full.append({'provider':provider,'tiles':expected,'candidates':q['total_candidates']})
    dense=json.loads((base/'dense_small/results.json').read_text());assert dense['ok'] and len(dense['trials'])==(2 if model['generation']=='sam1' else 4)
    expanded=json.loads((base/'expanded/results.json').read_text());assert expanded['ok'] and len(expanded['trials'])==2
    multi=json.loads((base/'multilake/results.json').read_text());assert multi['ok'] and len(multi['trials'])==2 and all(t['undo_reapply_exact'] for t in multi['trials'])
    checks['models'].append({'id':name,'interactive_trials':59,'cpu':True,'fresh_process_cache':True,'full_images':full,'dense_small_cases':len(dense['trials']),'expanded_cases':2})
for name in ['sam2.1_small','sam2.1_large']:
    base=OUT/'windows'/name/'cuda_bf16';q=json.loads((base/'results.json').read_text());assert q['ok'] and len(q['trials'])==59;assert json.loads((base/'fresh_process_restore.json').read_text())['ok']
checks['bf16_models']=2
exports=json.loads((OUT/'export_verification.json').read_text());assert len(exports)==22 and all(r['mask_polygon_raster_exact'] and r['original_grid_exact'] for r in exports)
checks['spatial_export_cases']=22;checks['multilake_models']=11;checks['ok']=True
(OUT/'final_verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');print(json.dumps(checks,indent=2),flush=True)
