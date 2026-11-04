"""Validate stored raster metadata independently of file access and Qt."""


def validate_metadata(image):
    if not isinstance(image.get('name'),str) or not image['name']:raise ValueError('影像名称无效。')
    bands=image.get('bands')
    if type(bands) is not int or bands<1:raise ValueError('影像波段数量无效。')
    dtypes=image.get('dtypes')
    if not isinstance(dtypes,list) or len(dtypes) not in (1,bands) or not all(isinstance(v,str) and v for v in dtypes):raise ValueError('影像波段类型无效。')
    if not isinstance(image.get('crs'),str) or not isinstance(image.get('assigned_crs',''),str):raise ValueError('影像投影信息无效。')
    if not isinstance(image.get('fingerprint'),str) or not image['fingerprint']:raise ValueError('影像来源标识无效。')
    if type(image.get('source_files')) is not int or image['source_files']<1:raise ValueError('影像源文件数量无效。')
    if 'source_paths' in image and (not isinstance(image['source_paths'],list) or not all(isinstance(p,str) and p and '\x00' not in p for p in image['source_paths'])):raise ValueError('影像依赖路径无效。')
    provenance=image.get('import_list',{})
    if not isinstance(provenance,dict) or 'source' in provenance and (not isinstance(provenance['source'],str) or not provenance['source'] or '\x00' in provenance['source']):raise ValueError('影像导入来源无效。')
    if 'source_paths' in provenance and (not isinstance(provenance['source_paths'],list) or not all(isinstance(p,str) and p and '\x00' not in p for p in provenance['source_paths'])):raise ValueError('VRT 来源路径无效。')
    if 'ready' in image and type(image['ready']) is not bool:raise ValueError('影像准备状态无效。')
    for name in ('model_recipe','display_recipe'):
        recipe=image.get(name)
        if recipe is not None:
            if not isinstance(recipe,dict) or not isinstance(recipe.get('bands'),list) or len(recipe['bands'])!=3 or any(type(b) is not int or not 1<=b<=bands for b in recipe['bands']):raise ValueError('影像波段配置无效。')
            if 'ranges' in recipe:
                from .contracts import validate_recipe
                validate_recipe(recipe,bands)
