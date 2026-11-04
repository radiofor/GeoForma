GeoForma 1.0.5 商店材料
======================

本文件夹集中保存商店填写文案、当前界面截图、应用图标及隐私政策文件。

桌面截图
--------
上传位置：Store 一览 → 中文（中国）→ 屏幕截图 → 桌面。
文件夹：screenshots/。
四张截图由当前软件界面生成，使用合成影像示例；PNG 尺寸以 asset-manifest.json 为准。
编号为建议展示顺序，可在商店上传后调整。

01-main-window.png：软件主界面。
02-image-import.png：导入影像。
03-label-export.png：标签列表与导出。
04-reshape.png：轮廓重塑。

商店图标
--------
上传位置：Store 一览 → 中文（中国）→ Microsoft Store 徽标 → Microsoft Store 显示图像。
文件夹：store-icons/。

app-tile-300x300.png：对应 1:1 应用磁贴图标 300 × 300。
app-tile-150x150.png：对应 1:1 图像 150 × 150。
app-tile-71x71.png：对应 1:1 图像 71 × 71。

均沿用当前应用的地图与笔尖 Logo，保留透明背景和原始比例。
150 像素文件与当前 MSIX 使用的图标相同；其他尺寸从同一原稿导出。

原始 Logo
---------
文件夹：../assets/。
geoforma_logo_map_pen.png：透明背景原稿，用于其他规格导出。
geoforma_map_pen.ico：当前 Windows 应用的多尺寸图标文件。
以上原稿与 ICO 不需要上传到“桌面截图”或 PNG 商店图标栏。

填写文案与隐私政策
------------------
store-listing-zh-CN.txt：中文商店介绍、功能、简短描述、关键字等字段。
geoforma-privacy/：README.md、PRIVACY.md 和 index.html。
隐私政策网页地址：https://radiofor.github.io/geoforma-privacy/。
填写 URL 前请确认 GitHub Pages 已发布，且网页能够公开访问。

宣传素材
--------
文件夹：promotional/。
01-poster-720x1080.png：对应“Microsoft Store 徽标 → 招贴画”。
02-box-art-1080x1080.png：对应“Microsoft Store 徽标 → 1:1 酷图”。
03-super-hero-1920x1080.png：对应“Windows 和 Xbox 图像 → 16:9 超级英雄画面”。
三张图为统一品牌风格的 2D 地理示意插画；横版不含文字、Logo 或软件界面。
实际操作截图仍使用 screenshots/，应用磁贴图标仍使用 store-icons/。
预告片及 Xbox 专项宣传图片仍可留空。
具体上传说明见 promotional/UPLOAD_GUIDE.txt，生成提示词见 promotional/generation-prompts.json。

校验
----
asset-manifest.json：截图与图标的尺寸、文件大小及 SHA256 记录。
当前发布包的位置见 release/latest-1.0.5.json。

微软参考：
https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images
