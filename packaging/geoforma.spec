from pathlib import Path
import os,sys
from PyInstaller.utils.hooks import collect_data_files,collect_submodules,copy_metadata
from PyInstaller.utils.win32.versioninfo import VSVersionInfo,FixedFileInfo,StringFileInfo,StringTable,StringStruct,VarFileInfo,VarStruct

root=Path(SPECPATH).parent
sys.path.insert(0,str(root))
from geoforma.distribution import VERSION
from main import configure_runtime
configure_runtime()
sam3_runtime=root/'environment'/'sam3-runtime'
file_version=tuple(int(part) for part in VERSION.split('.'))
if len(file_version)==3:file_version+=(0,)
if len(file_version)!=4:raise ValueError('Windows 版本必须包含四段数字。')
version_info=VSVersionInfo(ffi=FixedFileInfo(filevers=file_version,prodvers=file_version,mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),
    kids=[StringFileInfo([StringTable('040904B0',[StringStruct('FileDescription','GeoForma'),StringStruct('FileVersion',VERSION),
        StringStruct('InternalName','GeoForma'),StringStruct('OriginalFilename','GeoForma.exe'),StringStruct('ProductName','GeoForma'),StringStruct('ProductVersion',VERSION)])]),
        VarFileInfo([VarStruct('Translation',[1033,1200])])])
prefix=Path(sys.prefix)
optional=os.environ.get('GEOFORMA_OPTIONAL_RUNTIME')=='1'
datas=[(str(root/'assets'/name),'assets') for name in ('geoforma_map_pen.ico','chevron_down.svg','spin_up.svg','spin_down.svg')]
datas.append((str(root/'geoforma/model_catalog.json'),'geoforma'))
datas.append((str(root/'geoforma/native_runtime_catalog.json'),'geoforma'))
if optional:
    datas.append((str(root/'packaging/optional-runtime.json'),'geoforma'))
    from geoforma.native_runtime import catalog
    from geoforma.bundle_layout import sha256_file
    for profile in catalog()['profiles'].values():
        for wheel in profile['wheels']:
            if wheel['name']!='torchvision':continue
            path=root/'environment/resource-wheels'/wheel['filename']
            if not path.is_file() or path.stat().st_size!=wheel['bytes'] or sha256_file(path)!=wheel['sha256']:raise ValueError('请先运行 tools/prepare_resource_wheels.py 获取经校验的内封小型组件。')
            datas.append((str(path),'runtime_wheels'))
if os.environ.get('GEOFORMA_BUILD_CHANNEL')=='store':datas.append((str(root/'packaging/store-profile.json'),'geoforma'))
for folder in ['gdal','proj']:
    datas.append((str(prefix/'Library'/'share'/folder),'Library/share/'+folder))
if (prefix/'Library/lib/gdalplugins').exists():datas.append((str(prefix/'Library/lib/gdalplugins'),'Library/lib/gdalplugins'))
# Conda GIS DLLs share dependencies not always discoverable through Python imports.
binaries=[(str(path),'Library/bin') for path in (prefix/'Library/bin').glob('*.dll')]
hidden=['geoforma.backend','geoforma.sam2_backend','geoforma.sam3_backend','geoforma.sam3_runtime','geoforma.backend_factory','geoforma.exports','rasterio._features','rasterio._warp','rasterio._io','rasterio.sample','osgeo.ogr','osgeo.osr','osgeo.gdal']
hidden+=collect_submodules('geoforma.inference')
hidden+=collect_submodules('segment_anything')
hidden+=collect_submodules('sam2')+collect_submodules('hydra')+collect_submodules('omegaconf')
hidden+=collect_submodules('tqdm')
datas+=collect_data_files('sam2')
if sam3_runtime.is_dir():
    # Preserve the official package as ordinary files for its runtime imports.
    datas += [(str(path),'sam3-runtime/'+str(path.relative_to(sam3_runtime).parent))
              for path in sam3_runtime.rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc']
hidden+=collect_submodules('rasterio')+collect_submodules('osgeo')
if optional:
    hidden+=['filelock','typing_extensions','sympy','networkx','jinja2','fsspec','mpmath','packaging','PIL']
    hidden+=collect_submodules('PIL')
    import importlib.util
    from geoforma.bundle_layout import external_standard_imports
    hidden+=external_standard_imports([Path(importlib.util.find_spec(name).origin).parent for name in ('torch','torchvision')])
for package in ['torch','torchvision','segment_anything','SAM-2','hydra-core','omegaconf','rasterio','shapely','numpy','PySide6','GDAL','certifi','filelock','Pillow','setuptools','PyYAML','requests','charset-normalizer','urllib3','idna']:
    try:
        if not optional or package not in ('torch','torchvision'):datas+=copy_metadata(package)
    except Exception:pass
datas+=collect_data_files('segment_anything')
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
    hiddenimports=hidden,runtime_hooks=[str(root/'packaging/runtime_hook.py')],excludes=['tkinter','matplotlib','pandas','scipy','IPython','pytest','PyQt5','PyQt6','PySide2','tensorboard']+(['torch','torchvision'] if optional else []),noarchive=False)
from geoforma.bundle_layout import deduplicate_binaries
a.binaries=deduplicate_binaries(a.binaries)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='GeoForma',debug=False,bootloader_ignore_signals=False,
    strip=False,upx=False,console=False,icon=str(root/'assets/geoforma_map_pen.ico'),version=version_info)
# The frozen executable and file lists are complete. Release the analysis
# graph before COLLECT copies the native libraries on memory-constrained PCs.
import gc
a.graph=None
gc.collect()
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='GeoForma')
