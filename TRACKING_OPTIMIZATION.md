# 球轨迹可信化与 CUDA 参数实验

`Visibility` 比例只表示模型是否输出了坐标，不表示坐标是否命中羽毛球。此版本使用 `inputs/*_ball.csv` 中随官方样本提供的标签作为参考，并将展示数据拆分为：

- `reference`：官方参考轨迹，仅用于正确回放和评价基准。
- `raw_prediction`：TrackNet 原始预测。
- `filtered_prediction`：基于候选点的时序过滤与短缺口插值轨迹；插值点不计入检测评分。

主评分为原始分辨率上的 `F1@10px`，同时输出 `F1@20px`、定位误差、假点与漏检统计。

## 单段 CUDA 快速验证

```powershell
cd "E:\PythonProject\pythonProject\计算机视觉大作业\badminton-pipeline-repro-windows-clean"
& "E:\miniconda\envs\py310\python.exe" scripts\tools\sweep_tracknet_cuda.py `
  --video-id pro_match17_1_02_02 `
  --threshold 0.20 `
  --eval-mode nonoverlap `
  --output-root output\tracknet_sweep_smoke
```

`nonoverlap` 适合先验证链路和筛选方向。`weight` 与 `average` 更慢，但应在最终选择参数前运行。

## 七段完整参数筛选

```powershell
& "E:\miniconda\envs\py310\python.exe" scripts\tools\sweep_tracknet_cuda.py
```

默认参数网格为：

- `threshold`: `0.15`, `0.20`, `0.25`, `0.30`
- `eval_mode`: `nonoverlap`, `average`, `weight`
- `device`: `cuda`
- `batch_size`: `4`，CUDA 失败时自动以 `2` 重试

结果写入 `output\tracknet_sweep\sweep_summary.json`。程序按 `F1@10px`、位置误差、耗时依次选择候选配置。

## 将实验结果发布到网页

完整筛选结束后，发布工具会读取汇总中自动选出的最佳配置，并发布全部片段：

```powershell
& "E:\miniconda\envs\py310\python.exe" scripts\tools\promote_sweep_result.py `
  --sweep-root output\tracknet_sweep

& "E:\miniconda\envs\py310\python.exe" scripts\tools\export_frontend_data.py `
  --video-id pro_match17_1_02_02 `
  --video-id pro_match17_1_15_13 `
  --video-id pro_match17_2_01_01 `
  --video-id pro_match17_2_08_05 `
  --video-id pro_match17_2_15_11 `
  --video-id pro_match17_2_18_11 `
  --video-id pro_match19_1_01_01
```

打开页面：

```powershell
& "E:\miniconda\envs\py310\python.exe" -m http.server 8000 --bind 127.0.0.1
```

浏览器访问 `http://127.0.0.1:8000/frontend/`。页面默认显示官方参考轨迹，按钮可切换到原始预测和过滤结果。未通过最低定位质量门槛的过滤结果会标记为实验，不会宣称优化成功。
