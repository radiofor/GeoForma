"""Chinese report built from measured evidence; filenames remain ASCII."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'

def main():
    rows=json.loads((OUT/'summary.json').read_text());lines=[
        'GeoForma 官方 SAM 模型评估报告',
        '测试日期：2026-10-13；测试对象：本机 RTX 4060 Ti 16GB。',
        '范围：SAM 1 B/L/H，SAM 2 与 SAM 2.1 各 Tiny/Small/Base+/Large，共 11 个公开检查点。SAM 3/3.1 按用户要求暂缓，未运行推理，不能评定效果。',
        '正式 GeoForma 后端仍为 SAM 1；新增模型目前仅在独立测试环境验证，尚未加入正式模型选择界面。',
        '',
        '测试环境',
        'Windows：独立 environment/sam_eval，继承现有 GeoForma PyTorch；Python 3.13.16、torch 2.9.1+cu128。',
        '共同基准使用 FP32；另对 SAM 2.1 Small/Large 补测 BF16。不采用 torch.compile，不训练或更新权重。SAM 2 关闭可选 CUDA 扩展构建，不要求用户手工编译；apply_postprocessing=False，关闭洞填充和小连通区域删除。',
        '代码固定提交与权重 URL、SHA256 见 manifest.json；SHA256 为本地计算，不等于独立发布的官方校验值。',
        '',
        '数据和公平对照',
        '低分辨率：Sentinel-2-RGB-2025/X189/BX1517_BY0858.tif，1958×1957，EPSG:3857。',
        '高分辨率：Bing-RGB/X189/BX1517_BY0858.tif，16384×16384，EPSG:3857。',
        '54 个既有湖泊/疑似湖泊观察位置：高低分辨率各 27；每个使用原始像元 1024 窗口。另有 4 个小湖细节窗口和 1 个非方形窗口，共 59 个固定样本/模型。',
        '正负点包含模拟上下文点；框选范围从之前的 AI 试验掩膜推导，未经人工确认。高低分辨率影像并非严格同日期同成像条件，不能据此量化分辨率导致的精度变化。',
        '没有人工真值：未计算或声称湖泊 IoU、召回率、精度排名；预测质量分数不能跨模型当作实测精度。提示点命中、面积、边缘接触仅用于工程诊断。',
        '',
        '实测性能（GPU 编码和提示预测为 59 样本中位数；CPU 为同一高分辨率小湖窗口单次编码；显存为 PyTorch 峰值 allocated，不包含驱动、桌面及其他程序）',
        '模型 | GPU 编码 ms | 缓存后补点 ms | CPU 编码 ms | GPU 峰值 MiB | 权重 MiB | GPU/CPU/跨进程缓存',
    ]
    for r in rows:lines.append(f"{r['model']} | {r['encode_ms']} | {r['refine_ms']} | {r.get('cpu_encode_ms')} | {r['gpu_mib']} | {r['weights_mib']} | {'通过' if r.get('cpu_ok') and r.get('fresh_process_restore') else '待完成'}")
    comparisons=[]
    for name in ['sam2.1_small','sam2.1_large']:
        file=OUT/'windows'/name/'cuda_bf16/results.json'
        if not file.exists():continue
        q=json.loads(file.read_text())
        if not q.get('ok'):continue
        import numpy as np
        ious=[]
        for t in q['trials']:
            with np.load(OUT/'windows'/name/'cuda'/(t['key']+'.npz')) as a,np.load(file.parent/(t['key']+'.npz')) as b:
                union=int((a['refine']|b['refine']).sum());iou=int((a['refine']&b['refine']).sum())/union if union else 1.
            ious.append({'fixture':t['key'],'fp32_bf16_mask_iou':iou})
        entry={'model':name,'encode_ms':statistics.median(t['encode_seconds'] for t in q['trials'])*1000,'cache_mib':q['trials'][0]['cache_bytes']/1048576,'mean_agreement_iou':statistics.mean(t['fp32_bf16_mask_iou'] for t in ious),'worst_cases':sorted(ious,key=lambda t:t['fp32_bf16_mask_iou'])[:5]};comparisons.append(entry)
    if comparisons:
        lines+=['','BF16 补测（与 FP32 的一致性，不是湖泊准确率）']
        for r in comparisons:lines.append(f"{r['model']}: 编码 {r['encode_ms']:.2f}ms，缓存 {r['cache_mib']:.2f}MiB，掩膜平均一致性 IoU {r['mean_agreement_iou']:.4f}；差异最大的样本 {r['worst_cases']}")
        (OUT/'bf16_comparison.json').write_text(json.dumps(comparisons,indent=2),encoding='utf-8')
    lines+=['','全幅自动候选测试','统一使用 768 核心区域＋128 像元重叠，读取 1024 窗口；边界采用有效像元遮罩。每个模型独立执行，未拼接相邻编码特征。','AMG 参数：points_per_side=8，points_per_batch=16，pred_iou_thresh=.88，stability_score_thresh=.95，crop_n_layers=0，min_mask_region_area=0。8×8 是吞吐与流程对照，不是充分覆盖小湖的最终生产参数。','候选计数为原始类别无关输出，包含嵌套、重复、岩石、阴影、背景等；没有进行跨块去重或人工湖泊确认，不能当作湖泊数量。','模型 | 低分辨率全图块数/候选数/秒 | 高分辨率全图块数/候选数/秒']
    for r in rows:
        def detail(prefix):return f"{r.get(prefix+'_full_tiles','-')}/{r.get(prefix+'_full_candidates','-')}/{round(r[prefix+'_full_seconds'],2) if r.get(prefix+'_full_seconds') is not None else '待完成'}"
        lines.append(r['model']+' | '+detail('low')+' | '+detail('high'))
    lines+=['','小湖采样密度敏感性（不是精度评分）','每个模型对高分辨率 L28/L29 细节窗口使用 32×32 提示；SAM 2 系列另外测试默认 .8 IoU 阈值。点落在某个候选中仍可能是背景/包含地形的候选。']
    for r in rows:
        file=OUT/'windows'/r['model']/'dense_small/results.json'
        if file.exists():
            trials=json.loads(file.read_text())['trials']
            lines.append(r['model']+'：'+ '; '.join(f"{t['fixture']} threshold={t['pred_iou_thresh']} candidates={t['candidates']} center_hits={t['center_hits']} areas={t['center_hit_areas']} time={t['seconds']:.2f}s" for t in trials))
    lines+=['','跨块大目标扩展窗口（重新编码）','每模型对大湖读取 4096×4096、对小湖读取 2048×2048 原始像元窗口；不是把原块特征拼接。']
    for r in rows:
        file=OUT/'windows'/r['model']/'expanded/results.json'
        if file.exists():
            trials=json.loads(file.read_text())['trials'];lines.append(r['model']+'：'+ '; '.join(f"{t['key']} point={t['point']['pixels']} refine={t['refine']['pixels']} box={t['box']['pixels']} edge={t['refine']['touches_window']} encode={t['encode_seconds']:.3f}s" for t in trials))
    lines+=['','自动候选的多点修正（两个小冰碛湖）','对每个版本选择点命中的最小候选，分别测试原中心点、多水面正点＋额外边缘负点、清除候选先验以及框＋点组合；额外位置经过 RGB 目视选择，但没有人工真值。']
    for r in rows:
        file=OUT/'windows'/r['model']/'multilake/results.json'
        if file.exists():
            for t in json.loads(file.read_text())['trials']:lines.append(f"{r['model']} {t['fixture']} seed={t['seed_pixels']} multi_seed={t['multi_seed']['pixels']} fresh={t['multi_fresh']['pixels']} box_points={t['multi_box']['pixels']}; positive_hits={t['multi_seed']['positive_hits']}; undo_reapply_exact={t['undo_reapply_exact']}")
    lines+=['','关键结论与接入建议','1. 优先接入 SAM 2.1 Small：当前小湖目视样例较稳定，编码明显快于 SAM 1 B，权重/显存成本低。该建议是工程和样例观察，不是统计精度冠军。','2. SAM 2.1 Tiny 作为轻量、CPU/低显存选项；部分小湖样例选择了湖泊的一部分，不能单凭速度作为唯一默认。','3. SAM 2.1 Large 作为可选复核模型；多数小湖样例有效，但非方形窗口和弱水体也会失败，稠密 AMG 对 L29 仍没有点命中候选，不能自动视为最优。','4. 保留 SAM 1 B 兼容原项目；SAM 1 L/H 可保留高级选项，但不建议默认。SAM 1 H 的高分辨率 L29 细节中，补点最高分掩膜含大量周围地形，框选结果更集中。','5. SAM 2 原版四种规模均可运行，可作为回归/研究选项；日常界面优先展示 2.1，避免同时铺开所有历史版本。','6. 所有已测试模型都是类别无关分割：选择“湖泊”标签不会让 SAM 1/2/2.1 自动识别湖泊。全图仍需人工筛选与漏检补点。低分辨率 L29 的水体证据弱，模型规模增加也不能保证可靠标注。','7. 不默认平滑或删除小区域；失败时可选另一候选、改用框与点组合、补点或清除不可靠先验重新预测。软件应提供显式“不使用候选先验重新分割”，防止候选局部范围持续限制结果。','8. FP32 保持默认。BF16 在本机能运行，Large 编码显著提速、特征缓存约 10MiB，但少数样本的最高分候选发生明显跳变；平均一致性高不能掩盖个别失败。低精度应独立缓存并作为高级选项验证。','',
        '缓存、坐标和软件接入',
        'SAM 1 恢复单个 image embedding；SAM 2/2.1 必须同时恢复 image_embed、high_res_feats 和原始 H/W，缓存约为 SAM 1 的四倍。官方没有通用的磁盘特征恢复接口；本次使用固定版本私有状态封装，正式接入须独立适配器和缓存 schema。',
        '官方已有能力：加载完整预训练模型、图像编码复用、点/框/低分辨率掩膜提示、类别无关自动掩膜生成。',
        '工程封装能力：原始栅格分块和 NoData 裁剪、提示坐标恢复、磁盘缓存、GeoPackage/GeoTIFF、版本/精度切换与任务恢复。',
        '仍需算法研究/人工真值验证：自动识别纯湖泊、全图小湖漏检补全、跨块目标身份和接缝、冰雪/阴影/浅水边界判断、模型精度排名。此次没有把这些当作已解决。',
        '点击复用特征，没有重复调用编码器；官方 AMG.generate 仍会调用 set_image 和编码器，已有交互特征缓存不能自动消除这部分计算。',
        '非方形窗口及磁盘恢复逐像元一致；像元中心坐标做仿射往返校验。空间验证另将 11 模型 × 高低分辨率小湖掩膜转几何、导出 EPSG:4326 GPKG 和原网格 TIFF，共 22 组；掩膜→多边形→栅格像元一致、原图尺寸/仿射/CRS 一致。',
        '大目标触及窗口边缘应提示重新读取更大原始栅格窗口并编码；扩展窗口测试见 expanded 目录。扩展会下采样至模型固定输入，小目标细节可能下降，不能把特征拼接当作跨块分割。',
        '尚需正式工程接入：后端能力注册、模型选择/自动下载、版本化缓存校验、UI/任务进程切换和真实窗口回归。',
        '',
        '文件索引',
        'summary.csv / summary.json：实测汇总。review.html / comparison_*.png：固定提示视觉对照。',
        'windows/<model>/cuda/results.json：点框、特征、坐标、显存详细记录。cpu/results.json：CPU 回退记录。',
        'windows/<model>/full_low_grid8、full_high_grid8：完整 TIF 每块结果与压缩掩膜。dense_small：稠密提示敏感性；expanded：大窗口重新编码。',
        'exports：仅供空间导出验证的测试标签，不是人工确认的训练数据。',
        'initial_status.json 保留最初测试校验 DLL 异常；extended_status.json / additional_status.json 记录修复后及额外测试结果。',
        '本轮未修改用户影像、项目、标签、正式 Python 依赖或正在运行的软件。新增源码和依赖放在项目独立测试目录，权重放入用户 GeoForma 模型目录。独立 venv 的 Conda 原生库初始化问题已修复并复测；没有归因为模型失败。',
    ]
    (OUT/'REPORT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('REPORT.txt updated',flush=True)

if __name__=='__main__':main()
