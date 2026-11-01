"""The status badge, meter and details each carry different information."""
import pytest
from geoforma.task_status import task_detail,task_subject
from geoforma.image_list import ImportPlan


@pytest.mark.parametrize('kind,title,stage,expected',[
    ('import','导入影像…','导入影像 3/120：lake.tif','导入影像 · lake.tif'),
    ('import','导入影像…','lake.tif','导入影像 · lake.tif'),
    ('reference_import','导入参考：NDWI','读取文件引用','读取文件引用 · NDWI'),
    ('reference_import','导入 NDWI 参考影像','','导入参考 · NDWI'),
    ('preparation','准备影像 · lake.tif','准备影像 3/9','lake.tif'),
    ('preparation','准备影像 · lake.tif','','lake.tif'),
    ('preparation','准备影像：lake.tif','加载 SAM 模型…','加载模型 · lake.tif'),
    ('preparation','准备影像：lake.tif','检查完整影像缓存','检查影像缓存 · lake.tif'),
    ('model','加载模型：SAM 2.1 · Base+','加载模型权重…','读取模型权重 · SAM 2.1 · Base+'),
    ('model','加载模型：SAM 3','下载权重 · SAM 3 · 128.0 / 3290.2 MiB','下载权重 · SAM 3 · 128.0 / 3290.2 MiB'),
    ('model','加载模型：SAM 1 · L','下载权重 · SAM 1 · L · 152.0 / 1191.6 MiB','下载权重 · SAM 1 · L · 152.0 / 1191.6 MiB'),
    ('model','加载模型：SAM 1 · L','SAM 1 · L · 152.0 / 1191.6 MiB','SAM 1 · L · 152.0 / 1191.6 MiB'),
    ('model','加载模型：SAM 3','加载 SAM 模型…','加载模型 · SAM 3'),
    ('model','加载模型：SAM 3','SAM 3','加载模型 · SAM 3'),
    ('resource_install','配置 SAM 3','','配置资源 · SAM 3'),
    ('resource_install','配置 SAM 3','连接镜像 · sam3.pt','连接镜像 · sam3.pt · SAM 3'),
    ('resource_install','配置 SAM 3','下载 SAM 3 · 20 / 3000 MiB','下载 SAM 3 · 20 / 3000 MiB'),
    ('resource_install','配置 SAM 3','校验 sam3.pt','校验 sam3.pt · SAM 3'),
    ('interactive','根据提示生成轮廓…：lake.tif','','逐个分割 · lake.tif'),
    ('project_open','打开项目：lake.geoforma','读取项目文件：lake.geoforma','读取项目文件：lake.geoforma'),
    ('project_open','打开项目：lake.geoforma','缓存标签轮廓 · 256/512','缓存标签轮廓 · lake.geoforma'),
    ('export','导出标签：lake.tif','导出原始网格标签…','写入文件 · lake.tif'),
])
def test_detail_does_not_repeat_task_or_counter(kind,title,stage,expected):
    assert task_detail(title,stage,kind)==expected


@pytest.mark.parametrize('name',['导入影像.tif','准备影像_3.tif','SAM 2.1','F:/2026/10/27.tif','下载数据.tif'])
def test_filenames_versions_and_paths_are_preserved(name):
    assert task_detail('导入影像',name,'import').endswith(name)
    assert task_subject(name,'import')==name


def test_import_summary_omits_zero_counts_and_repeated_action():
    assert ImportPlan().summary(12)=='成功 12 幅'
    assert ImportPlan(duplicates=2,errors=['bad.tif']).summary(10)=='成功 10 幅 · 重复 2 项 · 失败 1 项'
