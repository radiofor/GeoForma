import copy
from shapely.geometry import box,mapping,shape
from geoforma.label_index import partition_labels as partition_candidates


def candidate(identifier,g,score=.9,source='automatic'):
    return {'id':identifier,'image_id':'image','geometry':mapping(g),'score':score,'edge':False,'source':source,'status':'candidate','class_id':None}

def assert_one_partition(items):
    for i,a in enumerate(items):
        for b in items[i+1:]:assert shape(a['geometry']).intersection(shape(b['geometry'])).area==0

def test_prompt_target_priority_and_union_coverage_preserved():
    inputs=[candidate('auto',box(0,0,100,100),.99),candidate('prompt',box(50,0,150,100),.5,'prompt_guided')]
    original=copy.deepcopy(inputs);result=partition_candidates(inputs)
    assert result[0]['id']=='prompt' and shape(result[0]['geometry']).area==10000
    assert sum(shape(l['geometry']).area for l in result)==15000
    assert_one_partition(result);assert inputs==original
    assert result[1]['raw_geometry']==inputs[0]['geometry']

def test_complete_duplicates_and_full_coverage_do_not_produce_another_set():
    inputs=[candidate('a',box(0,0,100,100),.99),candidate('b',box(10,10,20,20),.8),candidate('c',box(0,0,100,100),.7)]
    assert [l['id'] for l in partition_candidates(inputs)]==['a']

def test_confirmed_blockers_and_tiny_remainders_preserved():
    inputs=[candidate('tiny',box(0,0,1,1))];confirmed=[candidate('confirmed',box(0,0,.999,1))]
    result=partition_candidates(inputs,confirmed)
    assert len(result)==1 and 0<shape(result[0]['geometry']).area<.002


