"""Staged GPKG/GeoJSON exports and rollback-safe Shapefile file-set publishing."""
import json,shutil,tempfile
from pathlib import Path
from .export_settings import DEFAULT_LABEL_FIELD
from osgeo import ogr,osr
from rasterio.crs import CRS
from rasterio.warp import transform_geom
from shapely.geometry import mapping
from shapely.affinity import affine_transform
from .atomic_io import replace_file

FORMATS={'.gpkg':'GPKG','.shp':'ESRI Shapefile','.geojson':'GeoJSON'}
SHP_SUFFIXES=('.shp','.shx','.dbf','.prj','.cpg','.qix','.sbn','.sbx','.shp.xml','.metadata.json')


def _check_shapefile_targets(image,path,protect):
    """A new .shp name must not silently replace an existing sidecar."""
    destinations=[path.parent/(path.stem+extension) for extension in SHP_SUFFIXES]
    for destination in destinations:protect(image,destination)
    if not path.exists():
        existing=next((p for p in destinations[1:] if p.exists() or p.is_symlink()),None)
        if existing is not None:raise ValueError(f'同名 SHP 附属文件已存在：{existing.name}。请使用其他导出名称。')


def effective_crs(image,path,target_crs=''):
    source=image.get('assigned_crs') or image['crs']
    if not source:raise ValueError('请先指定该影像的 CRS；不会猜测投影。')
    CRS.from_user_input(source)
    return 'EPSG:4326' if Path(path).suffix.lower()=='.geojson' else CRS.from_user_input(target_crs or source).to_string()


def _publish_set(stage,target):
    """All files are prepared first; failures restore the old complete file set."""
    files=sorted(p for p in stage.iterdir() if p.is_file())
    backup=stage/'backup';backup.mkdir();saved=[];published=[]
    journal={'kind':'geoforma-vector-export-v1','target':str(target.resolve()),'new_files':[p.name for p in files]}
    (stage/'transaction.json').write_text(json.dumps(journal,indent=2))
    try:
        for suffix in SHP_SUFFIXES:
            dest=target.parent/(target.stem+suffix)
            if dest.exists():
                if not dest.is_file() or dest.is_symlink():raise ValueError('SHP 伴随文件不是普通文件，拒绝覆盖。')
                replace_file(dest,backup/dest.name);saved.append(dest.name)
        for file in files:
            replace_file(file,target.parent/file.name);published.append(file.name)
    except Exception as error:
        try:
            for name in published:(target.parent/name).unlink()
            for name in saved:replace_file(backup/name,target.parent/name)
        except Exception as recovery_error:
            raise RuntimeError(f'导出失败且回滚未完成；备份保留在 {stage}，请勿删除。') from recovery_error
        raise error


def write_vector(image,labels,path,target_crs,task,classes,protect,label_field=DEFAULT_LABEL_FIELD):
    from .export_validation import validate_export_labels
    values,geometries=validate_export_labels(image,labels,classes,task)
    path=Path(path);suffix=path.suffix.lower()
    if suffix not in FORMATS:raise ValueError('矢量格式必须为 .gpkg、.shp 或 .geojson。')
    from .export_settings import validate_label_field
    label_field=validate_label_field(label_field,suffix)
    protect(image,path)
    # A Shapefile publishes and replaces a set of siblings, not just .shp.
    # Protect every possible destination before writing or moving any file.
    if suffix=='.shp':_check_shapefile_targets(image,path,protect)
    crs=effective_crs(image,path,target_crs);source_crs=image.get('assigned_crs') or image['crs']
    reproject=CRS.from_user_input(crs)!=CRS.from_user_input(source_crs)
    path.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.geoforma-vector-',dir=path.parent));temp=stage/path.name
    retain=False;store=None;layer=None;ogr.UseExceptions()
    try:
        driver=ogr.GetDriverByName(FORMATS[suffix])
        if driver is None:raise RuntimeError('当前 GDAL 缺少所选矢量驱动。')
        store=driver.CreateDataSource(str(temp),options=['ADD_GPKG_OGR_CONTENTS=NO'] if suffix=='.gpkg' else [])
        srs=osr.SpatialReference();srs.SetFromUserInput(crs);srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        options=['ENCODING=UTF-8','2GB_LIMIT=YES'] if suffix=='.shp' else ['RFC7946=YES','COORDINATE_PRECISION=15'] if suffix=='.geojson' else []
        multipart=any(label['geometry']['type']=='MultiPolygon' for label in labels)
        layer=store.CreateLayer('labels',srs,ogr.wkbMultiPolygon if multipart else ogr.wkbPolygon,options=options)
        names={c['id']:c['name'] for c in (classes or [])}
        fields=[('label_id',ogr.OFTString),(label_field,ogr.OFTInteger),('class_name',ogr.OFTString),('status',ogr.OFTString),
                ('source',ogr.OFTString),('method',ogr.OFTString),('model',ogr.OFTString),('prompts',ogr.OFTString),
                ('edit_state',ogr.OFTString),('edit_count',ogr.OFTInteger),('edits',ogr.OFTString),('smooth_px',ogr.OFTReal)]
        if suffix=='.shp':fields=[(n,k) for n,k in fields if n not in ['source','prompts','edits']]+[('image_id',ogr.OFTString)]
        for name,kind in fields:
            field=ogr.FieldDefn(name,kind)
            if suffix=='.shp' and kind==ogr.OFTString:field.SetWidth(254)
            layer.CreateField(field)
        if suffix=='.gpkg':store.StartTransaction()
        a,b,c,d,e,f=image['transform']
        for i,label in enumerate(labels):
            task.check();pixel_geometry=geometries[i]
            geom=mapping(affine_transform(pixel_geometry,[a,b,d,e,c,f]))
            if reproject:geom=transform_geom(source_crs,crs,geom)
            attrs={'label_id':label['id'],label_field:values.get(label.get('class_id'),label.get('class_id')),'class_name':names.get(label.get('class_id'),''),
                   'status':label['status'],'source':image['path'],'method':'manual_draw' if label.get('source')=='manual_draw' else 'raster_reshape' if label.get('editing_state')=='manual' else label.get('source',''),
                   'edit_state':label.get('editing_state','model'),'edit_count':len(label.get('manual_edits',[])),
                   'edits':json.dumps(label.get('manual_edits',[]),ensure_ascii=False),
                   'model':json.dumps(label.get('model',{}),ensure_ascii=False),'smooth_px':float(label.get('smoothing_applied',0)),
                   'prompts':json.dumps({key:label.get(key) for key in ('points','box','window')},ensure_ascii=False)}
            if suffix=='.shp':
                config=label.get('model',{});attrs['model']='' if label.get('source')=='manual_draw' else config.get('backend','sam')+'/'+config.get('variant','');attrs['image_id']=image['id']
                attrs['class_name']=attrs['class_name'].encode('utf-8')[:254].decode('utf-8',errors='ignore')
            feature=ogr.Feature(layer.GetLayerDefn())
            for name,kind in fields:
                value=attrs[name]
                if value is not None:
                    if suffix=='.shp' and kind==ogr.OFTString and len(str(value).encode('utf-8'))>254:raise ValueError('SHP 标识或属性过长，请改用 GPKG/GeoJSON。')
                    feature.SetField(name,value)
            og=ogr.CreateGeometryFromJson(json.dumps(geom))
            if multipart and og.GetGeometryType()==ogr.wkbPolygon:og=ogr.ForceToMultiPolygon(og)
            feature.SetGeometry(og);layer.CreateFeature(feature);feature=None
            task.signals.progress.emit(i+1,len(labels),'导出 '+FORMATS[suffix]+'…')
        if suffix=='.gpkg':store.CommitTransaction()
        layer=None;store.Close();store=None;task.check()
        if suffix=='.shp':
            metadata={'schema':1,'geometry_coordinates':'source_raster_pixel_coordinates' if any(l.get('smoothing_applied') for l in labels) else 'source_raster_pixel_edges','source_image':image,'classes':classes or [],
                      'export_crs':crs,'label_field':label_field,'labels':labels,'dbf_note':'class_name is a UTF-8 preview of up to 254 bytes; full values and prompts are preserved here.'}
            (stage/(path.stem+'.metadata.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            _check_shapefile_targets(image,path,protect)
            try:_publish_set(stage,path)
            except RuntimeError:
                retain=bool((stage/'backup').exists() and any((stage/'backup').iterdir()));raise
        else:replace_file(temp,path)
    finally:
        layer=None
        if store is not None:store.Close()
        if not retain:shutil.rmtree(stage)
    return str(path)
