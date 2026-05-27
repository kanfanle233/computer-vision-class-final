# Windows CUDA / macOS MPS 跨平台运行

项目现在以 `run_pipeline.py` 作为跨平台入口。相同目录可直接复制到 Windows 或 macOS，设备参数使用 `auto` 时自动选择：

```text
NVIDIA CUDA -> Apple MPS -> CPU
```

Windows 与 macOS 通常只会出现其中一种 GPU，因此 `auto` 可直接使用。

## 1. 准备环境

建议使用 Python 3.10-3.12 创建独立环境。

### Windows + NVIDIA CUDA

先在 [PyTorch Start Locally](https://pytorch.org/get-started/locally/) 根据显卡驱动选择 Windows / Pip / CUDA 的官方安装命令，然后安装项目依赖：

```powershell
python -m pip install --upgrade pip
# 先运行 PyTorch 官网提供的 CUDA 安装命令
python -m pip install -r requirements_repro.txt
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA unavailable')"
```

输出第一项应为 `True`。

### macOS + Apple Silicon MPS

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements_repro.txt
python -c "import torch; print(torch.backends.mps.is_available())"
```

输出应为 `True`；若为 `False`，仍可用 `--pose-device cpu --tracknet-device cpu` 运行。

## 2. 每个新视频先标定球场

不同机位必须重新选择球场四角，不能复用另一段视频的坐标。点击顺序固定为 `TL -> TR -> BR -> BL`：

```powershell
python scripts/tools/select_court.py inputs\your_video.mp4
```

macOS:

```bash
python scripts/tools/select_court.py inputs/your_video.mp4
```

记下程序输出的八个数字，例如 `416,423,864,423,944,706,227,706`。

## 3. 一键运行

### Windows PowerShell

```powershell
python run_pipeline.py `
  --input-video "inputs\your_video.mp4" `
  --court-points "416,423,864,423,944,706,227,706" `
  --tracknet-device auto `
  --pose-device auto
```

也可以使用薄包装：

```powershell
.\run_all.ps1 -InputVideo "inputs\your_video.mp4" -CourtPoints "416,423,864,423,944,706,227,706"
```

### macOS Terminal

```bash
python run_pipeline.py \
  --input-video "inputs/your_video.mp4" \
  --court-points "416,423,864,423,944,706,227,706" \
  --tracknet-device auto \
  --pose-device auto
```

默认输出位置是 `output/<video_id>/`，完成后自动更新 `frontend/public/data/manifest.json`。

## 4. 参数建议

| 场景 | 建议参数 |
| --- | --- |
| CUDA 或 MPS 正式分析 | `--tracknet-eval-mode weight --pose-imgsz 960 --detect-interval 1` |
| 快速检查效果 | `--tracknet-eval-mode nonoverlap --detect-interval 2` |
| 远端人物太小或漏检 | 保持或提高 `--pose-imgsz 960` |
| 已有可信球轨迹 CSV | `--ball-csv path/to/video_ball.csv`，跳过 TrackNet 重跑 |
| 单独成品视频需要嵌入统计面板 | `--embedded-panels` |
| 需要慢动作特效而非数据同步播放 | `--cinematic-fx` |

`TrackNet` 阈值默认使用 `0.15`，可用 `--tracknet-threshold 0.20` 调整。遇到画面中固定亮点被误认作球时，不应只相信可见率，需要抽查轨迹是否真正随羽毛球运动。

## 5. 查看 Dashboard

在项目目录运行：

```powershell
python -m http.server 8000
```

打开：

```text
http://127.0.0.1:8000/frontend/
```

如需在元数据面板中展示额外的上传参考视频：

```powershell
$env:BADMINTON_UPLOADED_VIDEO = "D:\path\to\前端可视化.mp4"
python scripts\tools\export_frontend_data.py
```

或者把该视频放到 `inputs/前端可视化.mp4`。

## 6. 编码兼容说明

流水线优先输出适合浏览器播放的 H.264 视频。如果当前 OpenCV 没有 H.264 编码器，会自动回退为 `mp4v` 以保证分析完成，并打印警告；这种情况下桌面播放器可查看结果，但浏览器预览可能需要安装 `ffmpeg` 后再转为 H.264。
