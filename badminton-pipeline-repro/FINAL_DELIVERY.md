# 最终交付说明

## 项目主流程

```
输入视频 (inputs/*.mp4)
  │
  ├─ Step 1: TrackNet 球检测
  │   └─ *_ball_tracknet_raw.csv  (原始检测，不做真值)
  │
  ├─ refine_ball_csv.py  (质量后处理)
  │   ├─ ROI 过滤 (场地外误检)
  │   ├─ static-lock 拒绝 (静止记分牌等)
  │   ├─ jump rejection (跳点拒绝)
  │   ├─ Kalman 平滑 (段内常速度)
  │   └─ short-gap interpolation (短缺口插值)
  │   └─ *_ball.csv + *_ball_refine_report.json
  │
  ├─ Step 2: 球员分析 overlay
  │   └─ *_overlay.mp4
  │
  ├─ Step 3: 最终渲染
  │   └─ *_final.mp4
  │
  └─ Step 4: 前端数据导出 (质量门控)
      ├─ Green → 正常导出球轨迹；球速仅在投影可靠时展示
      ├─ Yellow → 导出但标低可信
      └─ Red → 不导出球轨迹/球速，仅保留球员分析
```

## Mac MPS 最终推荐运行命令

```bash
# 对单个视频运行完整流程（含 refine-ball）
./run_all_mac.sh \
  --input-video inputs/short.mp4 \
  --work-root output/short \
  --court-points "359,347,616,345,942,533,53,536" \
  --python /opt/miniconda3/envs/pytorch_env/bin/python \
  --tracknet-device auto \
  --yolo-device mps \
  --refine-ball \
  --ball-top-pad-px 200 \
  --ball-side-pad-px 120 \
  --ball-refine-max-gap 6 \
  --ball-refine-min-motion-score 0.0

# 或直接调用 run_pipeline.py
/opt/miniconda3/envs/pytorch_env/bin/python run_pipeline.py \
  --input-video inputs/short.mp4 \
  --work-root output/short \
  --court-points "359,347,616,345,942,533,53,536" \
  --refine-ball \
  --ball-top-pad-px 200 \
  --ball-side-pad-px 120 \
  --ball-refine-max-gap 6 \
  --ball-refine-min-motion-score 0.0 \
  --tracknet-device auto \
  --pose-device auto \
  --no-frontend-export
```

## 视频质量分级表

使用 `inputs/` 目录中提供的 TrackNet 原始输出（非自行推理），经过 refine 后处理 + 质量审计后，所有视频均达到 Green 标准：

| 视频 | 质量等级 | 质量分数 | 球可见率 | 最大缺失间隔 | interp率 | 可否展示球轨迹 |
|------|---------|---------|---------|-------------|---------|-------------|
| `pro_match19_1_01_01` | **Green** | 96 | 69% | 51帧 | 5% | ✅ |
| `pro_match17_2_15_11` | **Green** | 95.2 | 80% | 30帧 | 8% | ✅ |
| `pro_match17_2_01_01` | **Green** | 95.0 | 71% | 48帧 | 9% | ✅ |
| `1_00_01` | **Green** | 94.7 | 68% | 36帧 | 6% | ✅ |
| `pro_match17_2_18_11` | **Green** | 94.0 | 70% | 35帧 | 8% | ✅ |
| `pro_match17_1_15_13` | **Green** | 93.8 | 76% | 30帧 | 10% | ✅ |
| `pro_match17_2_08_05` | **Green** | 93.5 | 65% | 50帧 | 7% | ✅ |
| `pro_match17_1_02_02` | **Green** | 93.1 | 66% | 40帧 | 12% | ✅ |
| `short` | **Green** | 89.0 | 56% | 66帧 | 23% | ✅ |

## 输出目录说明

```
output/
├── ball_quality_summary.csv     # 全视频质量分级汇总
├── ball_quality_summary.json    # 同上（JSON 格式，含 best variant 选择）
├── short/                       # Green — 可展示球轨迹
│   ├── short_ball.csv           # 精炼后球轨迹（含 Source/Confidence）
│   ├── short_ball_tracknet_raw.csv  # TrackNet 原始输出
│   ├── short_ball_refine_report.json # 质量报告
│   ├── short_players.csv        # 球员检测数据
│   ├── short_motion.csv         # 运动统计
│   ├── short_overlay.mp4        # 分析叠加视频
│   └── short_final.mp4          # 最终渲染视频
├── pro_match17_*/               # Green — 可展示球轨迹和球员分析
│   └── ...                      # 同上结构
├── pro_match19_1_01_01/         # Green — 可展示球轨迹和球员分析
│   └── ...
└── ...
```

## 前端启动方式

```bash
cd frontend
npx vite          # 开发服务器，默认 http://localhost:5173
# 或直接打开 frontend/index.html（需本地 HTTP 服务器）
```

前端默认加载 `short` 视频（Green）。通过下拉菜单可切换其他视频。所有 9 个视频均为 Green 级别，可展示球轨迹、球速线和球员运动分析。由于球点投影到地面坐标存在误差，物理球速仅在投影可靠时展示；球员速度和运动统计正常展示。

## 答辩讲解要点

### 全部 9 个视频都达到了 Green 标准

使用 `inputs/` 目录中提供的 TrackNet 原始检测数据，配合 refine 后处理（ROI 过滤、static-lock 拒绝、jump rejection、Kalman 平滑、短缺口插值），所有视频的球可见率都在 56%-80% 之间，质量分数 89-96 分。

### 为什么 refine 后处理是必要的？

1. **原始 TrackNet 输出包含噪声**：即使 TrackNet 能正确检测球，输出中仍包含场地外误检、静止锁定（如记分牌）、跳点等问题。
2. **refine 后处理层负责清理**：ROI 过滤器拒绝场地外检测，static-lock 检测器识别并移除静止的背景元素，jump rejection 过滤速度不合理的跳点，Kalman 平滑在连续段内优化轨迹，短缺口插值填补 ≤6 帧的小缺口。
3. **质量门确保可信度**：每个视频都有 0-100 的质量评分，基于可见率、最大缺失间隔、插值率、各阶段拒绝率综合计算。只有达到 Green 标准（score≥75、vis≥55%、gap≤75）的视频才会展示球轨迹。

### 系统架构

```
TrackNet 原始检测 → refine 后处理 → 质量审计 → overlay 球员分析 → FX 渲染 → 前端展示
```

- TrackNet 负责球检测（heatmap 方法）
- refine 负责质量控制（不替代 TrackNet，只做后处理）
- 质量门决定哪些数据可以用于前端展示
- 前端区分 Green/Yellow/Red 展示，Green 正常展示球轨迹，Yellow 标低可信，Red 隐藏球轨迹只展示球员分析
- 当前所有 9 个视频均为 Green 级别，可完整展示球轨迹和球员分析

### 为什么停止继续调参

当所有 9 个视频都达到 Green 标准后，停止继续优化 TrackNet/refine 参数，原因如下：

1. **收益递减**：当前质量分数已经很高（89-96 分），继续调参带来的提升有限。
2. **过拟合风险**：过度调参可能导致参数过拟合于质量评分器，而非真正提升检测质量。
3. **稳定性考虑**：当前结果已经稳定，继续调参可能破坏已验证的 Green 结果。
4. **工程目标达成**：项目目标是工程复现和本地化优化，不是追求极致的检测准确率。

### 局限性说明

1. **没有重新训练模型**：使用的是预训练的 TrackNet 模型，没有在本项目数据集上微调。
2. **没有人工标注真值**：质量分数是工程指标，基于模型检测结果计算，不等价于人工标注的准确率。
3. **质量分数是工程筛查工具**：用于判断可视化可信度，不是学术评估指标。
