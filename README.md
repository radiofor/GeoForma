# GeoForma

GeoForma 是一款面向地理影像的 Windows 桌面标注工具，支持交互式分割、标签编辑和导出。

## 界面预览

主窗口：导入影像、进行标注、管理标签和导出结果。

![GeoForma 主窗口](docs/images/main-window.png)

资源配置：按需配置运行库和模型权重，并选择资源存放位置。图中目录仅为示例。

![资源配置窗口](docs/images/resource-settings.png)

## 下载与安装

1. 前往 [Releases](https://github.com/radiofor/GeoForma/releases/latest)，下载 `GeoForma-1.0.4-win64-setup.exe`。
2. 在 Windows 11 64 位系统中运行安装程序，按提示完成安装。
3. 已安装过 GeoForma 的用户请先保存工作并退出程序。对符合校验条件的旧版，安装向导会先卸载旧版再安装新版，并保留已有资源。

## 首次配置

1. 启动软件，打开右上角“设置”中的“资源配置”。
2. 如需将资源放到其他磁盘，先点击“选择目录”。例如选择 F 盘后，软件会使用 `F:\GeoForma-Resources`；切换目录时会迁移已有受管资源。
3. 在“PyTorch 运行库”中选择 CPU 或 NVIDIA GPU 版本，点击“自动下载并配置”，也可以手动导入对应文件。
4. 切换到“模型权重”，选择需要的模型并下载或导入权重。运行库和权重按需配置，安装包不包含这些大文件。

GPU 加速需要兼容的 NVIDIA 显卡和驱动；没有兼容 GPU 时可选择 CPU 运行库。无需单独安装 Python 或 CUDA Toolkit。

## 基本使用

1. 点击“导入影像”，选择 TIF、TIFF 或 VRT 文件；需要参考底图时，可点击“导入参考”。
2. 根据影像检查坐标系和模型波段，等待所需影像准备完成。
3. 选择标签类别，在工具栏使用正点、负点或框选提示目标；检查生成的轮廓，必要时调整。
4. 点击“保存标签”，并保存项目。完成后点击“导出标签”，选择 GPKG、SHP 或 GeoJSON 等格式。

更多操作可在软件左下角“操作说明”中查看。项目文件和原始影像保存在用户选择的位置，请妥善保管。

## 隐私政策与反馈

查看 [隐私政策](PRIVACY.md)。如需反馈问题，请使用 [Issues](https://github.com/radiofor/GeoForma/issues)，不要在公开反馈中提交个人信息、密码或未经脱敏的数据。
