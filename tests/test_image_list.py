"""VRT references become individual TIFF records without loading a mosaic."""
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
from geoforma.image_list import plan_import,read_vrt_sources


def write_vrt(folder,sources,name='images.vrt',bands=1):
    path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
    root=ET.Element('VRTDataset',rasterXSize='10',rasterYSize='10')
    for index in range(bands):
        band=ET.SubElement(root,'VRTRasterBand',dataType='Byte',band=str(index+1))
        for source in sources:
            item=ET.SubElement(band,'SimpleSource');filename=ET.SubElement(item,'SourceFilename',relativeToVRT='1');filename.text=str(source)
            ET.SubElement(item,'SourceBand').text='1'
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    return path


def test_vrt_band_duplicates_expand_once_and_mixed_selections_deduplicate(tmp_path):
    vrt=write_vrt(tmp_path,['区域 A/一.tif','影像二.tiff'],bands=3)
    first=str((tmp_path/'区域 A/一.tif').resolve());second=str((tmp_path/'影像二.tiff').resolve())
    plan=plan_import([vrt,first,vrt])
    assert [path for path,_ in plan.entries]==[first,second] and plan.duplicates==2 and not plan.errors
    assert plan.entries[0][1]=={'source':str(vrt),'source_paths':[str(vrt)]}
    assert not plan_import([vrt],existing=[first,second]).entries


def test_nested_and_warped_vrts_keep_source_order_and_provenance(tmp_path):
    nested=write_vrt(tmp_path,['tile.tif'],name='parts/nested.vrt')
    root=write_vrt(tmp_path,['parts/nested.vrt','other.tif'])
    plan=plan_import([root]);assert not plan.errors
    assert [Path(p).name for p,_ in plan.entries]==['tile.tif','other.tif']
    assert plan.entries[0][1]['source_paths']==[str(root),str(nested)]
    warped=tmp_path/'warped.vrt'
    warped.write_text('<VRTDataset><GDALWarpOptions><SourceDataset relativeToVRT="1">images.vrt</SourceDataset></GDALWarpOptions></VRTDataset>',encoding='utf-8')
    assert len(plan_import([warped]).entries)==2


@pytest.mark.parametrize('payload',['<broken','<VRTDataset/>','<OGRVRTDataSource/>','<!DOCTYPE VRTDataset [<!ENTITY p "x">]><VRTDataset/>'])
def test_invalid_or_empty_vrt_is_reported_without_blocking_other_tiffs(tmp_path,payload):
    path=tmp_path/'invalid.vrt';path.write_text(payload,encoding='utf-8')
    plan=plan_import([path,tmp_path/'good.tif'])
    assert len(plan.errors)==1 and [Path(p).name for p,_ in plan.entries]==['good.tif']


def test_cycles_and_unsupported_sources_are_skipped_without_losing_good_tiffs(tmp_path):
    root=write_vrt(tmp_path,['nested.vrt','other.png','good.tif'])
    write_vrt(tmp_path,['images.vrt'],name='nested.vrt')
    plan=plan_import([root])
    assert [Path(p).name for p,_ in plan.entries]==['good.tif'] and len(plan.errors)==2
    assert '循环' in plan.errors[0]


def test_custom_yaml_list_is_no_longer_supported(tmp_path):
    path=tmp_path/'images.yaml';path.write_text('format: geoforma-image-list',encoding='utf-8')
    plan=plan_import([path]);assert not plan.entries and '不再支持' in plan.errors[0]


def test_size_limit_and_cancellation(tmp_path,monkeypatch):
    import geoforma.image_list as module
    path=write_vrt(tmp_path,['a.tif']);monkeypatch.setattr(module,'MAX_BYTES',10)
    with pytest.raises(ValueError,match='8 MiB'):read_vrt_sources(path)
    def cancel():raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError,match='cancelled'):plan_import([path],check=cancel)


def test_relative_and_absolute_sources_and_missing_vrt(tmp_path):
    absolute=(tmp_path/'other'/'one.tif').resolve();vrt=write_vrt(tmp_path,[absolute,'local.tif'])
    assert read_vrt_sources(vrt)==[absolute,(tmp_path/'local.tif').resolve()]
    assert len(plan_import([tmp_path/'missing.vrt']).errors)==1
