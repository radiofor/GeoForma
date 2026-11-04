GeoForma 开发环境

平台：Windows x64；Python：3.13。
PyCharm 使用已有 GeoForma Conda 环境的解释器。
项目文件及目录统一使用英文命名，以英文下划线分隔，不使用中文或空格。
说明文档使用中文。外部影像路径仍支持中文与空格。

依赖分工
  Conda：Python、Qt/PySide6、GDAL/OGR、Rasterio、NumPy、Shapely、Pillow。
  pip：CUDA 版 PyTorch/torchvision、官方 SAM、pytest、PyInstaller。
  不要通过 pip 重装 Conda 管理的 Qt 或地理库，以免造成原生 DLL 冲突。

复现文件
  conda-win-64.lock.txt：基础 Conda 环境的精确包 URL 清单。
  requirements-win-pip.txt：基础 pip 依赖，含固定 CUDA wheel 和 SAM 源码。
  installed-packages.json：基础环境安装时的版本及来源。
  security-runtime/geoforma-profile.json：源码运行层当前验证过的覆盖版本及验证记录。
  verification.json：最近一次完整环境检查结果。
  designer-verification.json：独立 Designer 启动检查结果。
  锁文件不包含后续安全运行层的全部升级，不能单凭锁文件推断当前生效版本。

复现步骤（在 Conda 终端中进入项目目录后执行）
  conda create -n GeoForma --file environment/conda-win-64.lock.txt
  conda activate GeoForma
  python -m pip install -r environment/requirements-win-pip.txt
  python environment/install_runtime.py
  python environment/check_environment.py
  python tools/check_dependencies.py
  已有同名环境时，应先备份或选择其他安装位置，不要直接重建。
  依赖检查使用与源码程序相同的运行层；发行构建也会执行该检查。
  源码启动会优先使用经过验证的 security-runtime；重新建立环境时须检查该层的
  Python、平台和版本记录，重新验证依赖及模型后再用于发布，不应直接复制验证标记。
  若未配置该层，构建会检查实际依赖的安全最低版本，不符合要求时拒绝发布。

环境隔离
  当前继承的 PATH 和 PROJ_LIB 指向另一个环境的 GDAL。
  install_runtime.py 将 _geoforma_runtime.py 和 geoforma_runtime.pth
  安装到本环境的 site-packages，仅对本环境的 Python 进程及子进程生效。
  它优先使用本环境的 DLL 和 GDAL/PROJ 数据，并排除其他同级环境的路径。
  不修改系统环境变量、注册表、其他环境或第三方模型源码。
  所有路径由 sys.prefix 推导，不绑定开发机盘符。
  如需撤销隔离，可删除 site-packages 中上述两个文件；外部 GDAL 冲突可能重新出现。

验证范围
  check_environment.py 检查 Qt Windows 控件渲染、Designer 文件、Unicode 路径、
  TIF 窗口读取、相对引用 VRT、旋转网格掩膜往返、GeoPackage 事务与回滚、
  CPU/CUDA 运算、torchvision NMS，以及 SAM ViT-B 编码、补点和自动候选接口。
  中文和空格路径只用于验证外部数据的兼容性，不是项目命名规范。
  临时测试数据放在系统临时目录，检查结束后清理，不再放入项目目录。
  源代码中的 Unicode 测试字符串使用转义序列。
  check_environment.py 使用随机权重检查接口和设备，不评估分割质量。
  test_pretrained_sam.py 已通过官方 ViT-B 预训练权重测试，详见 SAM_TEST.txt。
  发行前按当前代码和发行包重新执行验证。

GeoPackage 创建选项
  GDAL 3.13.3 在本机回滚测试中出现可选要素计数缓存不一致：
  实际两条要素仍存在，但 gpkg_ogr_contents 缓存计数为零。
  环境检查使用 ADD_GPKG_OGR_CONTENTS=NO，禁用该可选缓存，保留事务、回滚和空间索引。
  后续标签仓库应采用该选项，并保留事务回归检查。
  参考：https://gdal.org/en/stable/drivers/vector/gpkg.html

Qt Designer
  在 PyCharm 中使用 GeoForma 解释器运行 environment/open_designer.py。
  或激活环境后，从项目目录运行 python environment/open_designer.py。
  启动脚本设置本环境的 DLL 和 Qt 平台插件路径。
  直接启动深层目录中的 designer.exe 可能无法定位平台插件。
  已验证 Windows 主窗口和新建表单窗口可以启动。
  PYSIDE_DESIGNER_PLUGINS 未设置的控制台提示与 Python 自定义控件有关；
  使用标准 Qt 控件不需要配置该扩展。

SAM 2 / SAM 2.1
  正式环境使用 Meta 固定提交 2b90b9f5ceec907a1c18123530e92e794ad901a4，
  两代模型由不同配置与权重驱动。依赖已加入 requirements-win-pip.txt。
  重新建立开发环境时先安装锁定的 Torch/torchvision，再安装 SAM 2：
  PowerShell 设置 $env:SAM2_BUILD_CUDA='0'，对固定的官方源 ZIP 使用
  python -m pip install --no-deps --no-build-isolation <sam2-source.zip>。
  目标环境需先安装 setuptools、hydra-core==1.3.7、omegaconf==2.3.1、
  iopath==0.1.10、tqdm==4.70.1。无需 Visual Studio CUDA 编译链。
  不启用可选连通域扩展，不删除小目标或填补洞。
