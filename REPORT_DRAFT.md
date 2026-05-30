# 羽毛球运动视频分析系统——工程复现与本地化优化

## 摘要

本项目复现并整理了 ychenfen/badminton-pipeline-repro 的羽毛球视频分析系统，并针对 macOS 环境进行了本地化优化。需要明确说明的是：当前仓库不是从零开始独立实现的全新 pipeline，而是在上游工程基础上完成课程项目所需的结构整理、运行适配、结果归档与前端展示包装。系统采用 TrackNet 进行羽毛球检测，通过 refine 后处理流程提升轨迹质量，结合 YOLOv8 进行球员姿态估计和运动分析，最终通过 D3.js 前端实现可视化展示。经过工程优化，所有 9 个测试视频的球轨迹质量均达到 Green 标准（质量分数 89-96 分），可完整展示球轨迹、球速线和球员运动分析。本项目是工程复现与本地化优化，不是重新训练模型，质量分数是工程筛查指标，不等价于人工标注的准确率。

**关键词**：羽毛球检测、TrackNet、运动分析、视频处理、前端可视化

## 1. 引言

### 1.1 研究背景

羽毛球运动视频分析是计算机视觉在体育领域的重要应用。通过对比赛视频进行自动化分析，可以提取球的运动轨迹、球员的移动模式、击球速度等关键信息，为教练员和运动员提供数据支持。

### 1.2 研究目标

本项目的目标是：
1. 复现 ychenfen/badminton-pipeline-repro 的羽毛球视频分析系统
2. 针对 macOS 环境进行本地化适配（MPS 加速）
3. 建立球轨迹质量评估体系
4. 实现前端可视化展示

### 1.3 项目定位

本项目是工程复现与本地化优化，不是重新训练模型。我们使用预训练的 TrackNet 模型进行球检测，通过后处理流程提升轨迹质量，并建立质量评估体系判断可视化可信度。

### 1.4 上游来源与贡献边界

当前课程仓库明确基于上游仓库 `ychenfen/badminton-pipeline-repro`。为了保持学术和工程表达上的诚实性，本文将两类贡献分开：

1. **继承内容**：核心 `TrackNet -> overlay -> FX` 处理链路、主要脚本组织方式、以及大量基础工程实现来自上游仓库。
2. **本地新增内容**：仓库结构整理、macOS / Apple Silicon 运行适配、参数收口、结果归档、前端数据导出、D3.js 展示页面、README 与课程提交文档。

因此，本文不把该系统描述为“完全原创的端到端羽毛球分析框架”，而将其定位为**基于上游开源工程的课程复现与本地化改编项目**。

## 2. 系统总体设计

### 2.1 系统架构

系统采用模块化设计，主要包含以下组件：

```
输入视频 → TrackNet 球检测 → refine 后处理 → 质量审计 → 球员分析 overlay → FX 渲染 → 前端展示
```

### 2.2 技术栈

- **球检测**：TrackNet（heatmap 方法）
- **球员姿态估计**：YOLOv8-pose
- **轨迹后处理**：refine_ball_csv.py（ROI 过滤、static-lock 拒绝、jump rejection、Kalman 平滑、短缺口插值）
- **视频渲染**：OpenCV + FFmpeg
- **前端可视化**：D3.js + Vite

### 2.3 工作流程

1. **Step 1：TrackNet 球检测**
   - 输入原始视频，输出每帧的球坐标（*_ball_tracknet_raw.csv）
   - 使用预训练模型，不进行微调

2. **Step 2：refine 后处理**
   - ROI 过滤：拒绝场地外误检
   - static-lock 拒绝：识别并移除静止的背景元素（如记分牌）
   - jump rejection：过滤速度不合理的跳点
   - Kalman 平滑：在连续段内优化轨迹
   - 短缺口插值：填补 ≤6 帧的小缺口

3. **Step 3：质量审计**
   - 计算质量分数（0-100 分）
   - 分级：Green（≥75 分）、Yellow（≥55 分）、Red（<55 分）
   - 只有 Green 级别的视频才会展示球轨迹

4. **Step 4：球员分析 overlay**
   - 使用 YOLOv8-pose 进行球员姿态估计
   - 计算球员位置、速度、移动距离

5. **Step 5：FX 渲染**
   - 生成最终分析视频

6. **Step 6：前端数据导出**
   - 导出标准化数据供前端使用
   - 根据质量等级决定是否导出球轨迹

## 3. 羽毛球轨迹检测与后处理

### 3.1 TrackNet 球检测

TrackNet 是一种基于 heatmap 的羽毛球检测模型，能够输出每帧中球的位置和置信度。

**模型特点**：
- 输入：连续 3 帧图像
- 输出：heatmap，表示球在每帧中的位置概率
- 阈值：默认 0.15，可通过参数调整

**局限性**：
- 模型是预训练的，没有在本项目数据集上微调
- 检测结果可能包含误检（如记分牌、场地外物体）
- 存在漏检情况（球被遮挡或模糊时）

### 3.2 refine 后处理

refine 后处理流程用于清理 TrackNet 的原始输出，提升轨迹质量：

1. **ROI 过滤**
   - 定义场地区域（通过 court-points 参数指定）
   - 拒绝场地外的检测点

2. **static-lock 拒绝**
   - 检测静止的背景元素（如记分牌）
   - 如果连续多帧的球位置几乎不变，则认为是 static-lock

3. **jump rejection**
   - 过滤速度不合理的跳点
   - 如果相邻帧的球位置变化过大，则认为是跳点

4. **Kalman 平滑**
   - 在连续段内使用 Kalman 滤波优化轨迹
   - 假设球在短时间内的运动是匀速的

5. **短缺口插值**
   - 填补 ≤6 帧的小缺口
   - 使用线性插值

### 3.3 质量评估

质量评估体系用于判断球轨迹的可信度：

**质量分数计算公式**：
```
score = 35 × score_visible + 20 × score_gap + 10 × score_interp + 15 × score_roi + 10 × score_static + 10 × score_jump
```

其中：
- score_visible = min(1.0, visible_rate / 0.55)
- score_gap = 1.0 if max_missing_gap ≤ 75 else max(0.0, 1.0 - (max_missing_gap - 75) / 120)
- score_interp = max(0.0, 1.0 - interp_rate / 0.45)
- score_roi = max(0.0, 1.0 - rejected_roi / raw_visible)
- score_static = max(0.0, 1.0 - rejected_static_lock / raw_visible)
- score_jump = max(0.0, 1.0 - rejected_jump / raw_visible)

**分级标准**：
- **Green**：score ≥ 75 且 visible_rate ≥ 0.55 且 max_missing_gap ≤ 75
- **Yellow**：score ≥ 55 且 visible_rate ≥ 0.40 且 max_missing_gap ≤ 120
- **Red**：其他

**重要说明**：质量分数是工程筛查指标，用于判断可视化可信度，不等价于人工标注的准确率。

## 4. 球员运动分析与可视化

### 4.1 球员姿态估计

使用 YOLOv8-pose 模型进行球员姿态估计：

- 输入：视频帧
- 输出：球员关键点（骨骼）
- 跟踪：使用 ByteTrack 进行多目标跟踪

### 4.2 运动分析

基于球员姿态估计结果，计算以下指标：

1. **位置**：球员在场地中的坐标（通过 homography 变换）
2. **速度**：球员的瞬时速度（米/秒）
3. **移动距离**：球员的累计移动距离（米）
4. **最大速度**：球员的最大瞬时速度（米/秒）

### 4.3 可视化展示

前端使用 D3.js 实现以下可视化：

1. **球轨迹**：显示球的运动轨迹（仅 Green 级别视频）
2. **球速线**：显示球的速度变化曲线（仅在投影可靠时展示）
3. **球员位置**：显示球员在场地中的位置
4. **球员速度**：显示球员的速度变化曲线
5. **运动统计**：显示球员的累计移动距离、最大速度等

## 5. 实验设置与本地运行环境

### 5.1 硬件环境

- **设备**：macOS（Apple Silicon）
- **加速**：MPS（Metal Performance Shaders）

### 5.2 软件环境

- **Python**：3.10（/opt/miniconda3/envs/pytorch_env/bin/python）
- **PyTorch**：支持 MPS 加速
- **OpenCV**：用于视频处理
- **Ultralytics**：YOLOv8-pose
- **D3.js**：前端可视化

### 5.3 数据集

使用 `inputs/` 目录中的 9 个羽毛球比赛视频：

1. short（短视频，用于快速测试）
2. 1_00_01
3. pro_match17_1_02_02
4. pro_match17_1_15_13
5. pro_match17_2_01_01
6. pro_match17_2_08_05
7. pro_match17_2_15_11
8. pro_match17_2_18_11
9. pro_match19_1_01_01

### 5.4 运行命令

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

## 6. 实验结果与质量评估

### 6.1 球轨迹质量

所有 9 个视频的球轨迹质量均达到 Green 标准：

| 视频 | 质量等级 | 质量分数 | 球可见率 | 最大缺失间隔 | interp率 |
|------|---------|---------|---------|-------------|---------|
| `pro_match19_1_01_01` | **Green** | 96.0 | 69% | 51帧 | 5% |
| `pro_match17_2_15_11` | **Green** | 95.2 | 80% | 30帧 | 8% |
| `pro_match17_2_01_01` | **Green** | 95.0 | 71% | 48帧 | 9% |
| `1_00_01` | **Green** | 94.7 | 68% | 36帧 | 6% |
| `pro_match17_2_18_11` | **Green** | 94.0 | 70% | 35帧 | 8% |
| `pro_match17_1_15_13` | **Green** | 93.8 | 76% | 30帧 | 10% |
| `pro_match17_2_08_05` | **Green** | 93.5 | 65% | 50帧 | 7% |
| `pro_match17_1_02_02` | **Green** | 93.1 | 66% | 40帧 | 12% |
| `short` | **Green** | 89.0 | 56% | 66帧 | 23% |

### 6.2 球员运动分析

所有视频的球员运动分析均可正常展示：

- 球员位置：通过 homography 变换将像素坐标转换为场地坐标
- 球员速度：计算瞬时速度（米/秒）
- 移动距离：计算累计移动距离（米）
- 最大速度：记录最大瞬时速度（米/秒）

### 6.3 前端展示状态

所有 9 个视频均为 Green 级别，前端可完整展示：
- 球轨迹 ✓
- 球速线 ✓（仅在投影可靠时展示）
- 球员位置 ✓
- 球员速度 ✓
- 运动统计 ✓

## 7. 前端可视化展示

### 7.1 技术实现

前端使用 D3.js 实现可视化，主要功能：

1. **视频播放器**：播放原始视频、overlay 视频、final 视频
2. **球轨迹图**：显示球的运动轨迹（时间-位置图）
3. **球速图**：显示球的速度变化曲线
4. **球员位置图**：显示球员在场地中的位置（俯视图）
5. **球员速度图**：显示球员的速度变化曲线
6. **运动统计面板**：显示累计移动距离、最大速度等

### 7.2 质量门控

前端根据质量等级决定展示内容：

- **Green**：正常展示球轨迹、球速线、球员分析
- **Yellow**：展示球轨迹但标低可信，球员分析正常
- **Red**：隐藏球轨迹和球速线，仅展示球员分析

### 7.3 数据导出

使用 `export_frontend_data.py` 脚本导出标准化数据：

```bash
/opt/miniconda3/envs/pytorch_env/bin/python scripts/tools/export_frontend_data.py
```

导出内容：
- manifest.json：视频列表、默认视频、质量信息
- videos/<video_id>/ball.csv：球轨迹数据
- videos/<video_id>/players.csv：球员位置数据
- videos/<video_id>/motion.csv：运动统计数据
- videos/<video_id>/analysis.json：分析元数据
- videos/<video_id>/quality.json：质量评估数据
- videos/<video_id>/*.mp4：视频文件

## 8. 局限性与未来工作

### 8.1 当前局限性

1. **没有重新训练模型**：使用的是预训练的 TrackNet 模型，没有在本项目数据集上微调。
2. **没有人工标注真值**：质量分数是工程指标，基于模型检测结果计算，不等价于人工标注的准确率。
3. **质量分数是工程筛查工具**：用于判断可视化可信度，不是学术评估指标。
4. **球速投影存在误差**：由于 homography 变换的误差，球速仅在投影可靠时展示。
5. **部分视频球可见率较低**：如 short 视频的球可见率仅为 56%。

### 8.2 未来工作

1. **模型微调**：在本项目数据集上微调 TrackNet 模型，提升检测准确率。
2. **人工标注**：建立人工标注的真值数据集，用于评估检测准确率。
3. **实时分析**：优化系统性能，实现实时视频分析。
4. **多角度分析**：支持多角度视频的同步分析。
5. **击球识别**：识别击球事件，分析击球类型和力量。

## 9. 总结

本项目成功复现并整理了 ychenfen/badminton-pipeline-repro 的羽毛球视频分析系统，并针对 macOS 环境进行了本地化优化。需要再次强调的是：当前成果建立在上游开源工程基础之上，本仓库的主要贡献是课程项目场景下的结构整理、运行适配、结果收口和展示包装，而不是从零提出一套全新的端到端羽毛球分析框架。通过建立球轨迹质量评估体系，所有 9 个测试视频的球轨迹质量均达到 Green 标准，可完整展示球轨迹、球速线和球员运动分析。

本项目是工程复现与本地化优化，不是重新训练模型。质量分数是工程筛查指标，用于判断可视化可信度，不等价于人工标注的准确率。系统已经可以用于教学演示和初步的运动分析，但如果需要更精确的检测结果，建议进行模型微调和人工标注。

## 参考文献

1. TrackNet: A Deep Learning Network for Tracking High-speed and Small Objects in Sports Applications
2. YOLOv8: Ultralytics YOLOv8
3. D3.js: Data-Driven Documents
4. ychenfen/badminton-pipeline-repro, GitHub repository
5. kanfanle233/computer-vision-class-final, GitHub repository

## 附录

### A. 项目结构

```
badminton-pipeline-repro/
├── inputs/                    # 输入视频
├── output/                    # 输出结果
│   ├── ball_quality_summary.csv
│   ├── ball_quality_summary.json
│   └── <video_id>/            # 各视频的输出
├── scripts/
│   ├── tracknet_runtime/      # TrackNet 推理
│   ├── overlay/               # 球员分析 overlay
│   ├── fx/                    # 视频特效
│   └── tools/                 # 工具脚本
├── frontend/                  # 前端可视化
│   ├── index.html
│   ├── src/
│   ├── styles/
│   └── public/data/           # 导出的数据
├── weights/                   # 模型权重
├── run_pipeline.py            # 单视频处理
├── run_all_mac.sh             # Mac 兼容包装
├── run_all_videos.py          # 批量处理
└── FINAL_DELIVERY.md          # 最终交付说明
```

### B. 关键脚本

1. `run_pipeline.py`：单视频完整处理流程
2. `run_all_mac.sh`：Mac 兼容包装脚本
3. `run_all_videos.py`：批量处理脚本
4. `scripts/tools/export_frontend_data.py`：前端数据导出
5. `scripts/tools/audit_ball_quality.py`：质量审计
6. `scripts/tools/refine_ball_csv.py`：轨迹后处理

### C. 质量评估公式

```
score = 35 × min(1.0, visible_rate / 0.55)
      + 20 × (1.0 if max_missing_gap ≤ 75 else max(0.0, 1.0 - (max_missing_gap - 75) / 120))
      + 10 × max(0.0, 1.0 - interp_rate / 0.45)
      + 15 × max(0.0, 1.0 - rejected_roi / raw_visible)
      + 10 × max(0.0, 1.0 - rejected_static_lock / raw_visible)
      + 10 × max(0.0, 1.0 - rejected_jump / raw_visible)
```

### D. 最终推荐运行命令

```bash
# Mac 环境
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
```
