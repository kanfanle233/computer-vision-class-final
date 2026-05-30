# 羽毛球比赛视频智能分析系统

**简体中文**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/pytorch-2.x-ee4c2c.svg)](https://pytorch.org/)
[![GPU](https://img.shields.io/badge/GPU-CUDA%20%7C%20MPS-blue.svg)](README_PORTABLE.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/kanfanle233/computer-vision-class-final/pulls)

把一段普通的羽毛球比赛视频，转换成带**运动员轨迹、移动速度、累计跑动距离、羽毛球飞行轨迹**的可视化分析结果，并通过 **Web 前端仪表盘**提供交互式多维数据探索。当前仓库是在上游工程基础上的课程项目整理版，而不是从零开始独立重写的全新系统。

整套系统基于 **TrackNet（球检测） + YOLOv8s-pose（球员姿态） + ByteTrack（多目标跟踪） + 透视矫正**，支持 Windows NVIDIA CUDA、Apple Silicon MPS 与 CPU 自动加速。跨平台复制运行请先看 [README_PORTABLE.md](README_PORTABLE.md)。

![效果演示](docs/images/demo.gif)

---

## 项目来源与归因说明

**这不是一个从零开始独立重写的全新 pipeline。** 当前仓库是课程项目整理版，明确基于上游仓库 [ychenfen/badminton-pipeline-repro](https://github.com/ychenfen/badminton-pipeline-repro) 进行复现、整理和本地化改编。

为了避免误导，这里把边界说清楚：

- **继承自上游仓库的内容**：核心 `TrackNet -> player overlay -> FX` 处理链路、关键脚本结构，以及整体工程骨架。
- **本仓库新增或重点调整的内容**：仓库根目录重组、README/交付文档整理、macOS/MPS 本地运行适配、参数收口、前端数据导出、D3.js 仪表盘展示、质量评分与课程提交所需的工程包装。
- **不应声称的内容**：本仓库不是重新训练 TrackNet 的全新研究实现，也不是完全原创的端到端羽毛球分析框架。

更详细的上游归因和改动边界见 [UPSTREAM_ATTRIBUTION.md](UPSTREAM_ATTRIBUTION.md)。

---

## 这个项目解决了什么

市面上"开源羽毛球分析"项目通常只能做以下其中一项：
- 只检测球，没有球员分析
- 假设俯视机位（真实比赛视频几乎都是斜拍）
- 写死 Windows 路径，Mac/Linux 跑不通
- 阈值硬编码，在真实视频上静默失败（球检测率 0%）
- 没有可视化前端，分析数据只能在终端看

这个仓库包含跨平台入口 `run_pipeline.py`，一条命令跑完全流程（TrackNet → Overlay → FX → 前端数据导出），并配套 D3.js 交互式仪表盘。最终交付说明见 [FINAL_DELIVERY.md](FINAL_DELIVERY.md)，课程报告草稿见 [REPORT_DRAFT.md](REPORT_DRAFT.md)。

---

## 效果展示

### 最终质量评估结果

所有 **9 个视频**球检测质量均为 **Green**（评分 ≥ 85）：

| 视频 | 质量评分 | 可见率 | 最大缺失间隔 | 等级 |
|------|---------|--------|-------------|------|
| pro_match19_1_01_01 | 95.96 | 69% | 51 帧 | 🟢 Green |
| pro_match17_2_15_11 | 95.24 | 80% | 30 帧 | 🟢 Green |
| pro_match17_2_01_01 | 94.96 | 71% | 48 帧 | 🟢 Green |
| 1_00_01 | 94.67 | 68% | 36 帧 | 🟢 Green |
| pro_match17_2_18_11 | 94.02 | 70% | 35 帧 | 🟢 Green |
| pro_match17_1_15_13 | 93.84 | 76% | 30 帧 | 🟢 Green |
| pro_match17_2_08_05 | 93.53 | 65% | 50 帧 | 🟢 Green |
| pro_match17_1_02_02 | 93.14 | 66% | 40 帧 | 🟢 Green |
| short | 88.96 | 56% | 66 帧 | 🟢 Green |

### 前端仪表盘展示

所有视频均支持在前端仪表盘展示 **球轨迹**、**球速线** 和 **球员运动分析**：

![前端仪表盘](docs/images/frontend_dashboard.png)

前端功能：
- **Ball Trajectory ✓**：球轨迹实时显示
- **Player Analytics**：球员位置、速度、跑动距离
- **Detection Timeline**：逐帧检测状态可视化
- **Quality Stats**：质量评分与缺失段列表

### 视频输出示例

**输入**：原始比赛视频（960×544，21 fps）

![原始第一帧](docs/images/01_input_frame.jpg)

**当前流程输出**：现版本默认产出的是逐视频分析文件、前端仪表盘数据，以及可切换的 `overlay/final` 视频版本；Mini Court、质量面板、统计卡片等视图不再固定烧录进视频画面。

当前真实交付物包括：
- `*_overlay.mp4`：叠加球员分析与球轨迹的分析视频
- `*_final.mp4`：最终渲染版本
- `*_ball.csv` / `*_players.csv` / `*_motion.csv` / `*_stats.json`：结构化分析结果
- `frontend/public/data/`：前端仪表盘使用的数据导出

**说明**：Mini Court、Heatmap、Zone Occupancy、Quality Stats 等视图现在主要在 Web 前端仪表盘中交互式展示，而不是作为固定大面板直接嵌入每一帧输出视频。

---

## Web 前端仪表盘

新增基于 D3.js 的交互式可视化仪表盘，支持 **9 个预分析视频** 的多维数据探索。

![前端仪表盘截图](docs/images/frontend_dashboard.png)

### 仪表盘布局

```
┌────────────────────────────────────────────────────────────────────┐
│  Badminton Visual Analytics        [Video ▾] [Original|Overlay|Final] [Export] │
├────────────────────┬──────────────────────┬────────────────────────┤
│                    │  Court Spatial View   │  Temporal Analytics    │
│   Video Player     │  [Trajectory|Heatmap] │  [Speed|Distance|Conf] │
│   + Frame Readout  │                       │                        │
│                    │  ┌──────────────────┐  ├────────────────────────┤
│                    │  │  Mini Court      │  │  Detection Timeline    │
│                    │  │  球员/球 俯视轨迹  │  │  逐帧检测状态可视化     │
│                    │  └──────────────────┘  ├────────────────────────┤
│                    │                        │  Quality Stats         │
│                    │  Court Zone Occupancy  │  / Video Metadata      │
│                    │  区域占有率热力图        │  (Tab 切换)             │
└────────────────────┴──────────────────────┴────────────────────────┘
```

### 核心功能

| 功能 | 说明 |
|---|---|
| **视频切换** | 下拉菜单切换 9 个视频片段（short + 8 个专业比赛片段） |
| **视频源切换** | Original / Overlay / Final Result 三种版本一键切换 |
| **帧级同步** | 任意图表上点击，视频自动跳转到对应帧 |
| **Mini Court** | 球场俯视图，支持轨迹模式和热力图密度模式切换 |
| **时序分析** | 速度 / 累计距离 / 检测置信度 三种指标曲线 |
| **检测可靠性时间线** | 逐帧显示球检测状态（绿 = 正常 / 橙 = 低置信度 / 红 = 缺失） |
| **区域占有率** | 6 个球场区域（前场/中场/后场 × 近端/远端）球员停留比例 |
| **统计卡片** | 帧数、FPS、时长、分辨率、球检出率、球员跑动距离、最高速度 |
| **质量面板** | 详细的检测质量指标 + 可点击的缺失检测段列表 |
| **数据导出** | 一键复制当前视频文件路径到剪贴板 |

### 启动前端

```bash
# 方式一：直接用浏览器打开（推荐）
open frontend/index.html

# 方式二：Python 起本地服务
cd frontend && python3 -m http.server 8080
# 然后浏览器访问 http://localhost:8080
```

前端数据通过 `scripts/tools/export_frontend_data.py` 从 `output/` 目录自动生成。`run_pipeline.py` 默认会在 Step 4 自动调用导出。

---

## 整体架构

```
原始视频.mp4
    │
    ▼  Step 1: TrackNet ─────────── 球检测（专门追小目标的连续帧热力图模型）
带球轨迹的视频 + 球坐标 CSV
    │
    ▼  Step 2: Overlay ──────────── YOLOv8s-pose + ByteTrack + Homography
叠加分析的视频 + stats.json + players.csv + motion.csv
    │
    ▼  Step 3: FX ────────────────── 子弹时间冻帧 + 慢动作 + 虚拟轨道相机
最终成品视频
    │
    ▼  Step 4: Export ────────────── 前端数据导出（manifest.json + 视频转码）
前端仪表盘可直接打开
```

四段独立运行，每段可以单独迭代。改一次面板字号、调一次跳变阈值、加一个新特效，都不需要从头重跑。

---

## 快速开始（30 秒短视频跑通）

### 1. 克隆仓库（含 LFS 大文件）

```bash
git lfs install     # 没装的话先 brew install git-lfs
git clone https://github.com/kanfanle233/computer-vision-class-final.git
cd computer-vision-class-final
```

模型权重 `weights/TrackNet_best.pt`（130 MB）和样本视频通过 Git LFS 自动下载。

### 2. 装依赖

```bash
python3 -m pip install --user --index-url https://pypi.org/simple \
    numpy opencv-python pandas Pillow torch ultralytics tqdm \
    pycocotools parse lap
```

`pycocotools`、`parse`、`lap` 是 TrackNet/ByteTrack 的隐藏依赖，原 requirements 没列全，必装。

### 3. 标球场 4 角点

整个流程**唯一需要人工**的环节。运行：

```bash
python3 scripts/tools/select_court.py short.mp4
```

弹窗里**按顺序**点 4 下：左上 → 右上 → 右下 → 左下（球场长方形 4 角，不是球网）。点完按 q，终端会输出像 `--court_points "352,342,628,343,944,527,52,532"` 这样的字符串。

样本视频 `short.mp4` 的标准答案：

```
352,342,628,343,944,527,52,532
```

效果如图（黄色四边形贴合球场边线）：

![球场角点标注](docs/images/02_court_corners.jpg)

### 4. 一键跑通全流程

统一入口 `run_pipeline.py`，跨平台自动选择 CUDA / MPS / CPU：

```bash
python3 run_pipeline.py \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532"
```

这会依次执行 TrackNet → Overlay → FX → 前端数据导出，输出在 `output/short/` 目录下：

```
output/short/
├── short_ball.csv                    # 球的逐帧坐标
├── short_players.csv                 # 球员检测数据
├── short_motion.csv                  # 运动统计
├── short_overlay.mp4                 # 叠加分析视频
├── short_final.mp4                   # 最终成品视频
└── ...
```

设备设为 `auto` 时，Windows NVIDIA 环境自动使用 CUDA，Apple Silicon 环境自动使用 MPS。

旧版 Mac bash 入口仍兼容：

```bash
TRACKNET_VIS_THRESH=0.15 ./run_all_mac.sh \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532" \
  --yolo-device mps
```

### 5. 看结果

```bash
# 播放叠加分析视频
open output/short/short_overlay.mp4

# 打开前端仪表盘
open frontend/index.html
```

### 6. 可选参数

```bash
# 启用球轨迹优化（跳变剔除 + 卡尔曼平滑 + 线性插值）
python3 run_pipeline.py \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532" \
  --refine-ball

# 启用子弹时间特效
python3 run_pipeline.py \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532" \
  --cinematic-fx

# 把统计面板画在视频上（默认不画，数据全在前端仪表盘）
python3 run_pipeline.py \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532" \
  --embedded-panels
```

---

## 三段详解

### Step 1 — TrackNet（球检测）

**它解决的问题**：羽毛球只有几个像素、飞得快、容易模糊，单帧 YOLO 之类的检测器经常漏。

**它的思路**：一次吃 4 帧连拍，输出 4 张概率热力图（每个像素值 = 这里是球的概率）。利用连续帧的运动信息识别出模糊的球。类比：你看一张静态照片可能看不出蚊子在哪，但 4 张连拍就能看出"有什么东西在那一带飞过"。

**输出**：

![TrackNet 输出帧](docs/images/03_tracknet_output.jpg)

视频上小圆圈是模型识别出的球轨迹。同时生成 CSV：

```csv
Frame,Visibility,X,Y
0,1,455,202
1,1,455,202
4,1,481,122
...
```

`Visibility=1` 表示这一帧检测到球，X/Y 是球在画面里的像素坐标。

**关键参数**：

| 参数 | 含义 | 推荐 |
|---|---|---|
| `--tracknet_file` | 模型权重 | `weights/TrackNet_best.pt` |
| `--tracknet_device` | 推理设备 | `auto`（Mac MPS；NVIDIA cuda；fallback cpu） |
| `--large_video` | 流式 dataloader | 长视频必须加 |
| `--tracknet_eval_mode` | `nonoverlap` / `weight` | `nonoverlap` 快 8 倍 |
| `--tracknet-threshold` | 二值化阈值 | **0.15**（默认已设好） |

### Step 2 — Overlay（球员检测 + 数据叠加）

整个项目 90% 的工程量在这一段，干 5 件事：

1. **YOLOv8s-pose** 检测每帧球员 + 17 个人体关键点（脚踝精确定位"足点"）
2. **ByteTrack** 维持球员 ID 跨帧不串
3. **Homography** 透视矫正：把斜拍画面里的梯形球场拉成俯视长方形
4. **MotionStats** 算每个球员的瞬时速度 / 累计距离 / 最高速度
5. **数据输出**：生成 stats.json / players.csv / motion.csv 供前端仪表盘消费

**透视矫正示意**：

```
画面里的梯形                标准球场坐标系（俯视）
                              (0, 0) ─────── (6.1, 0)
   TL ──── TR                    │              │
    \      /                     │              │
     \    /     ──→ Homography ─→│              │
      \  /                       │              │
   BL ──── BR                    │              │
                              (0, 13.4)─── (6.1, 13.4)
```

OpenCV 一行调用：

```python
H, _ = cv2.findHomography(court_quad, dst_rectangle)
```

之后任何脚点像素坐标都能投影到球场米制坐标，距离/速度计算跟机位无关。

**为什么要球员脚踝不用 bbox 中心**：bbox 中心是身体中心，离地有 1 米多高；脚踝在地面上，投影更准。`estimate_foot_point()` 优先取左右脚踝平均，置信度低时退到 bbox 底中点。

### Step 3 — FX（子弹时间特效）

电影《黑客帝国》Neo 躲子弹那个慢镜头围绕镜头转的镜头。这里是单机位轻量版：

- 选定一些时间点（"子弹时刻"，可手动 / 均匀分布 / 自动峰值检测）
- 在该时刻**冻帧** 28 帧，期间用虚拟相机做小幅度旋转 + 缩放
- 冻帧后接 **40 帧慢动作**（每帧重复 6 次，可选插值）
- 然后回到正常播放

默认不启用（保持前端帧级对齐）。加 `--cinematic-fx` 开启。

### Step 4 — 前端数据导出

`run_pipeline.py` 默认在 Step 4 自动调用 `scripts/tools/export_frontend_data.py`：

- 扫描 `output/` 下所有已完成分析的视频
- 计算 Homography 将像素坐标转为球场坐标
- 生成逐视频的 `quality.json`（检测质量指标、缺失段列表）
- 生成 `manifest.json`（视频元数据索引）
- 转码视频为 H.264 浏览器兼容格式
- 输出到 `frontend/public/data/` 目录

加 `--no-frontend-export` 跳过此步。

---

## 球轨迹优化

### `--filter-ball`：保守过滤

基于球场区域 + 运动评分过滤明显的误检点：

```bash
python3 run_pipeline.py \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532" \
  --filter-ball
```

- 球场外区域（含 padding）的检出点视为误检
- 静止不动的连续检出点视为背景噪声
- ≤ 2 帧的空洞做线性插值填补
- 生成过滤报告 JSON

### `--refine-ball`：增强优化（推荐）

在 `--filter-ball` 基础上增加跳变剔除和更激进的插值：

```bash
python3 run_pipeline.py \
  --input-video short.mp4 \
  --court-points "352,342,628,343,944,527,52,532" \
  --refine-ball
```

- 逐帧跳变检测：相邻帧位移超过 `--ball-max-interp-step-px` 的视为 ID 串变
- 最大插值空洞扩展到 6 帧
- 支持 InpaintNet 校正（如果权重存在）
- 生成详细的校正报告

---

## 参数速查表

### 跑别的视频要改什么

1. `--input-video` 路径
2. 重新跑 `select_court.py` 标 `--court-points`
3. 如果机位完全不同（前场低位 / 侧场），可能要调 `--court_length_m`（全场 13.4，半场 6.7）

### 全长视频时间预估（M4 Pro）

| 阶段 | CPU | MPS（GPU） |
|---|---|---|
| TrackNet（13344 帧） | ~3 小时 | ~30 分钟 |
| Overlay | ~30 分钟 | ~10 分钟 |
| FX | ~5 分钟 | 同上 |
| 前端导出 | ~2 分钟 | 同上 |

**最大瓶颈是 TrackNet**。MPS 加速已支持（`--tracknet-device mps`）。最终工程收口和质量结果见 [FINAL_DELIVERY.md](FINAL_DELIVERY.md)。

---

## 常见问题

**Q：球完全检测不到（Visibility 全 0）**
A：先检查 `--tracknet-threshold` 是否为 0.15（默认值），再确认 `court_points.json` 或命令行里的 `--court-points` 是否和当前视频匹配。

**Q：球员速度显示 24 m/s（比博尔特还快）**
A：这通常是轨迹跳变把 ID 串变记进了 max_speed。当前版本已经改成 `8.0 × dt + 0.05` 的自适应阈值来抑制这个问题。

**Q：中文显示成方块**
A：字体回退已加了 macOS PingFang.ttc。如果还报错，确认 `/System/Library/Fonts/PingFang.ttc` 存在。

**Q：球场轮廓画歪了**
A：`select_court.py` 点的顺序错了，必须 TL → TR → BR → BL。可加 `--draw_court_polygon` 让 overlay 视频里画出绿色四边形检查。

**Q：`ModuleNotFoundError: pycocotools / parse / lap`**
A：原 requirements.txt 没列全，按本文档"装依赖"那条命令补上。

**Q：前端仪表盘打不开 / 没有数据**
A：确认 `frontend/public/data/manifest.json` 存在。运行 `run_pipeline.py` 会自动导出前端数据，或手动运行 `python3 scripts/tools/export_frontend_data.py`。

更多运行说明可参考 [README_PORTABLE.md](README_PORTABLE.md) 和 [FINAL_DELIVERY.md](FINAL_DELIVERY.md)。

---

## 项目结构

```
repository-root/
├── README.md                       # 本文件（GitHub 项目介绍）
├── FINAL_DELIVERY.md               # 最终交付说明与结果摘要
├── REPORT_DRAFT.md                 # 课程研究报告草稿
├── README_PORTABLE.md              # 跨平台运行指南
├── run_pipeline.py                 # 跨平台统一入口（TrackNet → Overlay → FX → Export）
├── run_all_mac.sh                  # macOS 一键脚本
├── run_all.ps1                     # Windows PowerShell 一键脚本
├── run_all_videos.py               # 批量处理多视频
├── requirements_repro.txt          # Python 依赖
│
├── weights/                        # 模型权重（LFS）
│   ├── TrackNet_best.pt            # 球检测（130 MB）
│   └── yolov8s-pose.pt             # 球员姿态（23 MB）
│
├── frontend/                       # Web 前端仪表盘
│   ├── index.html                  # 主页面
│   ├── favicon.svg
│   ├── styles/                     # 样式
│   │   ├── base.css                # 设计 tokens + 基础样式
│   │   ├── layout.css              # 三栏响应式布局
│   │   └── charts.css              # 图表专用样式
│   ├── src/
│   │   ├── main.js                 # 入口 + 应用状态管理
│   │   ├── dataLoader.js           # 数据加载（JSON/CSV 并行请求）
│   │   ├── videoSync.js            # 视频帧级同步
│   │   ├── charts/
│   │   │   ├── miniCourt.js        # 球场俯视图（轨迹/热力图双模式）
│   │   │   ├── speedChart.js       # 速度/距离/置信度时序曲线
│   │   │   ├── heatmapLayer.js     # Canvas 热力图层
│   │   │   ├── zoneOccupancy.js    # 区域占有率柱状图
│   │   │   ├── statCards.js        # 统计卡片 + 质量面板
│   │   │   ├── trajectoryChart.js  # 轨迹图表
│   │   │   └── visibilityTimeline.js  # 检测可靠性时间线
│   │   └── vendor/d3.min.js        # D3.js v7
│   └── public/data/                # 前端数据（pipeline 自动生成）
│       ├── manifest.json           # 视频索引
│       └── videos/                 # 逐视频分析数据
│
├── scripts/
│   ├── tracknet_runtime/           # Step 1: TrackNet
│   │   ├── predict.py              # 入口（支持 MPS 加速）
│   │   ├── model.py                # 网络结构（U-Net 风格）
│   │   ├── dataset.py              # 数据加载
│   │   └── utils/general.py        # HEIGHT=288, WIDTH=512 等常量
│   │
│   ├── overlay/
│   │   └── overlay_player_analytics.py   # Step 2: 1340+ 行核心
│   │
│   ├── fx/
│   │   └── video_fx_bullet_time.py       # Step 3: 特效
│   │
│   └── tools/                      # 工具集
│       ├── select_court.py         # 交互式标球场角点
│       ├── export_frontend_data.py # 前端数据导出
│       ├── mask_tracknet_input.py  # TrackNet 输入遮罩预处理
│       ├── smooth_ball_csv.py      # 球轨迹保守过滤
│       ├── refine_ball_csv.py      # 球轨迹增强优化
│       ├── audit_ball_quality.py   # 球检测质量审计
│       ├── check_outputs.py        # 输出文件校验
│       ├── transcode_browser_video.py  # 浏览器兼容转码
│       └── ...
│
├── output/                         # Pipeline 输出（自动生成）
│   ├── short/                      # 30 秒样本分析结果
│   ├── pro_match17_*/              # 专业比赛片段分析
│   ├── pro_match19_*/              # 专业比赛片段分析
│   ├── ball_quality_summary.csv    # 质量评分与分级汇总
│   └── ...
│
└── docs/images/                    # README 配图
```

---

## 这个项目踩过的坑（精简版）

| 问题 | 现象 | 修复位置 |
|---|---|---|
| TrackNet 球检测 0% | csv 全 0 | `predict.py:35` 阈值 0.5 → 环境变量参数化 |
| 球员速度 24 m/s | 面板数字离谱 | `overlay_player_analytics.py:602` 阈值 1.2m → `8×dt+0.05` |
| 中文方块 | macOS 字体路径 | `overlay_player_analytics.py:18-27` 字体回退表 |
| 面板信息冗余 | 每球员 7 个数字 | 砍到 4 个核心 |
| 球场 quad 错位 | 距离速度全错 | `select_court.py` 重新人工标 |
| 跳变未被过滤 | 球轨迹离群点 | `refine_ball_csv.py` 跳变剔除 + 插值 |

完整交付结果与保留主流程，见 [FINAL_DELIVERY.md](FINAL_DELIVERY.md)。

---

## 当前状态与后续方向

当前仓库已经整理为课程展示版，主流程、前端数据和质量汇总都保留在仓库根目录。后续如果继续扩展，建议围绕下列方向：

```
已完成：
  ✅ P0.1 默认值写入 sh
  ✅ P0.2 清理临时文件
  ✅ TrackNet 阈值参数化
  ✅ 跳变阈值动态化
  ✅ MPS 加速支持（TrackNet + YOLO）
  ✅ 球轨迹过滤与优化（--filter-ball / --refine-ball）
  ✅ 前端仪表盘（D3.js 交互式可视化）
  ✅ 前端数据自动导出
  ✅ 批量视频处理
  ✅ 跨平台统一入口 run_pipeline.py

可继续扩展：
  1. 击球点检测与自动回合分割
  2. 多机位适配与更鲁棒的球场标定
  3. 更丰富的前端统计图与 PDF 报告导出
  4. 更精细的球速与战术分析
```

---

## 致谢

- 当前仓库的基础工程明确来源于上游仓库 [ychenfen/badminton-pipeline-repro](https://github.com/ychenfen/badminton-pipeline-repro)。本仓库是在其基础上完成课程项目整理、本地化适配、参数收口、文档重写和前端展示集成。
- TrackNet 模型来自 [TrackNetV3](https://github.com/qaz812345/TrackNetV3)
- YOLOv8 来自 [Ultralytics](https://github.com/ultralytics/ultralytics)
- ByteTrack 跟踪算法 [ByteTrack](https://github.com/ifzhang/ByteTrack)
- 前端可视化使用 [D3.js](https://d3js.org/)
- 样本视频出自 YouTube 频道 POGBADMINTON

---

## License

本仓库包含大量基于上游仓库改编的代码。上游仓库 README 的 License 一节标注“代码部分 MIT”；当前仓库保留对上游仓库的明确署名与引用。模型权重和样本视频按各自原始来源的 license 使用，仅供学习研究。

---

## 引用

如果你的报告、论文或展示直接使用了当前课程项目整理版，建议引用**本仓库**；如果你的描述涉及继承的基础 pipeline、核心工程结构或上游脚本来源，建议**同时引用上游仓库和本仓库**。

```bibtex
@misc{badminton_pipeline_repro_upstream,
  author       = {ychenfen},
  title        = {Badminton Match Video Analytics Pipeline},
  year         = {2026},
  howpublished = {\url{https://github.com/ychenfen/badminton-pipeline-repro}}
}

@misc{computer_vision_class_final,
  author       = {kanfanle233},
  title        = {Computer Vision Class Final: Badminton Match Video Visual Analytics},
  year         = {2026},
  howpublished = {\url{https://github.com/kanfanle233/computer-vision-class-final}}
}
```

如果你基于这个课程项目做了改进或衍生版本，欢迎在当前仓库提交 PR / Issue / Discussion，并在文档中继续保留对上游仓库的清晰归因与引用。

---

## 关键词

羽毛球, 视频分析, 图像识别, 运动分析, 计算机视觉, 目标检测, 多目标跟踪, 球员追踪, 球轨迹, 透视变换, 单应性矩阵, 子弹时间, 慢动作, 体育数据分析, AI 教练, 羽毛球训练, 比赛复盘, 战术分析, OpenCV, PyTorch, YOLOv8, TrackNet, ByteTrack, Apple Silicon, M4 Pro, MPS, macOS, D3.js, 数据可视化, Web 仪表盘, badminton, sports analytics, video analytics, computer vision, object tracking, shuttle detection, player tracking, court homography, bullet time, data visualization, dashboard.
