# 上游归因说明

## 上游仓库

本仓库的主要工程基础来自：

- 上游仓库：[ychenfen/badminton-pipeline-repro](https://github.com/ychenfen/badminton-pipeline-repro)

本仓库不是从零开始独立实现的全新羽毛球分析 pipeline，而是在上游工程基础上，为课程项目提交和本地运行环境做的整理、改编与交付包装版本。

## 明确保留上游归因的原因

这样做有两个目的：

1. **技术上诚实**：核心 `TrackNet -> overlay -> FX` 管线、脚本组织方式和大量工程实现不是本仓库原创。
2. **文档上清楚**：让读者分得清“继承了什么”和“本地又新增了什么”，避免把复现工程写成从零原创系统。

## 主要继承内容

以下内容主要继承或明显改编自上游仓库：

- 核心视频处理主流程：`run_pipeline.py`
- 球检测运行时：`scripts/tracknet_runtime/`
- 球员叠加分析主脚本：`scripts/overlay/overlay_player_analytics.py`
- 特效阶段：`scripts/fx/video_fx_bullet_time.py`
- 原始工程中围绕羽毛球比赛视频分析的整体模块组织方式

## 当前仓库的主要新增与整理

当前仓库在课程项目语境下，主要做了这些工作：

- 将项目整理到仓库根目录，重建更适合提交和展示的目录结构
- 针对本地 macOS / Apple Silicon 环境整理运行方式
- 保留并整理 `output/`、`frontend/public/data/` 等课程展示需要的结果文件
- 新增并整理前端仪表盘展示链路与 README 展示素材
- 强化课程交付文档，包括 `FINAL_DELIVERY.md`、`REPORT_DRAFT.md`
- 对 README、引用、致谢、仓库说明做诚实归因与展示收口

## 不应声称的内容

为了避免误导，不建议把当前仓库描述成以下任一说法：

- “完全原创的羽毛球视频分析框架”
- “从零开始独立实现的端到端系统”
- “重新训练并提出了新的 TrackNet 模型”

更准确的说法应该是：

> 本仓库基于 `ychenfen/badminton-pipeline-repro` 完成工程复现、本地化整理与课程提交包装。

## README 中采用的归因写法参考

当前 README 的归因写法有意采用了两类常见模式：

1. **在项目前部直接说明 fork / 上游来源**
   - 类似 Sourcegraph 的 [`zoekt`](https://github.com/sourcegraph/zoekt) README 中那种在前部直接说明 “当前仓库是 fork 后的维护主线” 的写法。
2. **明确说明哪些展示资产或文档也基于上游**
   - 类似 [`react-katex`](https://github.com/MatejBransky/react-katex) README 中对 “based on” 与 “the readme and the demo are forked from ...” 的说明方式。

这两种写法的共同点是：

- 不把来源信息藏在仓库最底部；
- 不只在 License 里顺带提一句；
- 让读者一眼能分清“基础来自哪里”与“当前仓库新增了什么”。

## 许可说明

上游仓库 README 的 License 一节写明：

> 代码部分 MIT。模型权重和样本视频按各自原始来源的 license 使用，仅供学习研究。

当前仓库保留了对上游仓库的明确归因。若未来要进行更正式的公开发布或二次分发，建议进一步核对并保留上游许可证文本与相关版权说明。
