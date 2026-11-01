"""Local help and dependency metadata; never imports a model or starts a task."""
import importlib.metadata
import platform
from .distribution import VERSION,install_root,resource_root

DOCUMENTS=(('快速开始','USER_GUIDE.txt'),('目标标注','SEGMENTATION_MODES.txt'),('SAM 3','SAM3.txt'),
           ('参考影像','REFERENCE_IMAGES.txt'),('VRT 批量导入','VRT_IMPORT.txt'),
           ('保存与恢复','RECOVERY.txt'),('资源配置','RESOURCE_SETUP.txt'),('安装与卸载','DEPLOYMENT.txt'))
PACKAGES=(('PySide6','PySide6'),('PyTorch','torch'),('TorchVision','torchvision'),('NumPy','numpy'),
          ('Rasterio','rasterio'),('GDAL','GDAL'),('Shapely','shapely'),('Pillow','Pillow'),
          ('PyYAML','PyYAML'),('SAM 1','segment_anything'),('SAM 2 / 2.1','SAM-2'),
          ('Hydra','hydra-core'),('OmegaConf','omegaconf'),('certifi','certifi'),
          ('filelock','filelock'),('setuptools','setuptools'),('Requests','requests'),
          ('charset-normalizer','charset-normalizer'),('urllib3','urllib3'),('IDNA','idna'))


def document_text(filename):
    if filename not in dict(DOCUMENTS).values():raise ValueError('未知说明文档。')
    for root in (install_root(),resource_root()):
        path=root/'docs'/filename
        if path.is_file():
            if path.stat().st_size>2*1024**2:raise ValueError('说明文档过大。')
            return path.read_text(encoding='utf-8-sig')
    return '说明文档缺失。请检查安装文件完整性。'


def dependency_rows():
    # The frozen bundle carries only relevant metadata; its license inventory
    # supplies versions for runtime packages without their own metadata hook.
    from .atomic_io import read_json
    inventory={}
    path=install_root()/'licenses/packages.json'
    if path.is_file():
        try:inventory={row['name'].casefold().replace('_','-'):row['version'] for row in read_json(path)}
        except (OSError,ValueError,KeyError,TypeError):pass
    rows=[('GeoForma',VERSION),('Python',platform.python_version())]
    from PySide6.QtCore import qVersion
    rows.append(('Qt',qVersion()))
    from .native_runtime import managed_runtime,lightweight,bundled_release
    managed=None if bundled_release() else managed_runtime()
    external=managed['probe']['versions'] if managed else {}
    for label,name in PACKAGES:
        if name in ('torch','torchvision') and (managed or lightweight()):
            rows.append((label,external.get(name,'未配置')));continue
        try:version=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:version=inventory.get(name.casefold().replace('_','-'),'未附带版本记录')
        rows.append((label,version))
    return rows
