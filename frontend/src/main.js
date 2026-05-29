import { loadManifest, loadVideoDataset } from "./dataLoader.js";
import { createVideoSync } from "./videoSync.js";
import { createMiniCourt } from "./charts/miniCourt.js";
import { createSpeedChart } from "./charts/speedChart.js";
import { createVisibilityTimeline } from "./charts/visibilityTimeline.js";
import { createHeatmapLayer } from "./charts/heatmapLayer.js";
import { renderQualityPanel, renderStatCards } from "./charts/statCards.js";

const els = {
  videoSelect: document.querySelector("#videoSelect"),
  video: document.querySelector("#matchVideo"),
  showOriginal: document.querySelector("#showOriginal"),
  showOverlay: document.querySelector("#showOverlay"),
  showFinal: document.querySelector("#showFinal"),
  exportButton: document.querySelector("#exportButton"),
  batchStatus: document.querySelector("#batchStatus"),
  batchKpis: document.querySelector("#batchKpis"),
  matchRail: document.querySelector("#matchRail"),
  statCards: document.querySelector("#statCards"),
  currentFrame: document.querySelector("#currentFrame"),
  videoMeta: document.querySelector("#videoMeta"),
  videoStatus: document.querySelector("#videoStatus"),
  qualityBadge: document.querySelector("#qualityBadge"),
  qualityPanel: document.querySelector("#qualityPanel"),
  qualityWarning: document.querySelector("#qualityWarning"),
  trajectoryModes: document.querySelector("#trajectoryModes"),
  courtFrameInfo: document.querySelector("#courtFrameInfo"),
  temporalLegend: document.querySelector("#temporalLegend"),
  uploadedMeta: document.querySelector("#uploadedMeta"),
  analysisMeta: document.querySelector("#analysisMeta"),
  exportPaths: document.querySelector("#exportPaths"),
};

const state = {
  manifest: null,
  dataset: null,
  source: "overlay",
  metric: "speed",
  heatmapMode: "separated",
  trajectoryMode: "reference",
  frame: 0,
};

const charts = {
  miniCourt: createMiniCourt(document.querySelector("#miniCourt"), seekFrame),
  speed: createSpeedChart(document.querySelector("#speedChart"), seekFrame),
  timeline: createVisibilityTimeline(document.querySelector("#visibilityTimeline"), seekFrame),
  heatmap: createHeatmapLayer(document.querySelector("#heatmapLayer")),
};

const sync = createVideoSync(
  els.video,
  () => state.dataset?.analysis?.fps || 30,
  (frame) => renderFrame(frame),
);

function seekFrame(frame) {
  sync.seekFrame(Math.max(0, Math.min(frame, (state.dataset?.analysis?.frame_count || 1) - 1)));
}
window.seekFrameGlobal = seekFrame;

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatSeconds(value) {
  return `${Number(value || 0).toFixed(2)}s`;
}

function videoSourceLabel(source) {
  return { original: "原始画面", overlay: "识别叠加", final: "最终效果" }[source] || source;
}

function trajectoryModeLabel(mode) {
  return { reference: "官方参考", raw_prediction: "原始预测", filtered_prediction: "优化预测" }[mode] || "轨迹";
}

function trajectoryQuality(item, preferredMode = "filtered_prediction") {
  const modes = item.quality?.trajectory_modes || {};
  return modes[preferredMode] || modes.raw_prediction || null;
}

function metricAt10(quality) {
  return quality?.evaluation?.metrics?.f1_at_10px || null;
}

function formatPredictionF1(quality) {
  const metric = metricAt10(quality);
  return metric ? formatPct(metric.f1) : "待重跑";
}

function professionalVideos() {
  return (state.manifest?.videos || [])
    .filter((video) => video.id.startsWith("pro_match"))
    .sort((left, right) => left.id.localeCompare(right.id, undefined, { numeric: true }));
}

function videoTitle(video) {
  if (!video.id.startsWith("pro_match")) return video.title || video.id;
  const match = video.id.match(/^pro_match(\d+)_(.+)$/);
  if (!match) return video.id;
  return `比赛 ${match[1]} / ${match[2].replaceAll("_", "-")}`;
}

function detectionTier(value) {
  if (Number(value || 0) >= 0.9) return "strong";
  if (Number(value || 0) >= 0.75) return "watch";
  return "risk";
}

function activateClipCard(videoId) {
  for (const button of els.matchRail.querySelectorAll("[data-video-id]")) {
    const active = button.dataset.videoId === videoId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "true" : "false");
  }
}

function renderBatchOverview() {
  const videos = professionalVideos();
  if (!videos.length) {
    els.batchStatus.textContent = "暂未发现专业比赛分析结果。";
    els.batchKpis.innerHTML = "";
    els.matchRail.innerHTML = "";
    return;
  }
  const totalDuration = videos.reduce((sum, video) => sum + Number(video.duration_s || 0), 0);
  const scored = videos.map((video) => metricAt10(trajectoryQuality(video))).filter(Boolean);
  const averageF1 = scored.length ? scored.reduce((sum, metric) => sum + metric.f1, 0) / scored.length : null;
  const stableCount = scored.filter((metric) => metric.f1 >= 0.75).length;
  const attentionCount = scored.filter((metric) => metric.f1 < 0.4).length;
  els.batchStatus.textContent = `已导入 ${videos.length} 段结果，共 ${totalDuration.toFixed(1)} 秒；${scored.length} 段具有结构有效的预测评分，官方标注不计入模型精度。`;
  els.batchKpis.innerHTML = [
    ["处理片段", `${videos.length} / 7`],
    ["总时长", `${totalDuration.toFixed(1)} s`],
    ["有效预测均值", averageF1 === null ? "待重跑" : formatPct(averageF1)],
    ["定位良好片段", `${stableCount} 段`],
  ].map(([label, value]) => `<article><span>${label}</span><strong>${value}</strong></article>`).join("");
  els.matchRail.innerHTML = videos.map((video) => {
    const metric = metricAt10(trajectoryQuality(video));
    const score = metric?.f1;
    const attention = score === undefined ? "待重跑" : score < 0.4 ? "定位失败" : score >= 0.75 ? "定位良好" : "需复核";
    return `
      <button class="match-card ${score === undefined ? "watch" : detectionTier(score)}" type="button" data-video-id="${video.id}">
        <span class="match-name">${videoTitle(video)}</span>
        <strong>${score === undefined ? "--" : formatPct(score)}</strong>
        <span class="match-meta">${Number(video.duration_s || 0).toFixed(1)}s · ${attention}</span>
      </button>
    `;
  }).join("");
  els.matchRail.querySelectorAll("[data-video-id]").forEach((button) => {
    button.addEventListener("click", () => {
      els.videoSelect.value = button.dataset.videoId;
      loadSelectedVideo(button.dataset.videoId);
    });
  });
  if (attentionCount > 0) {
    els.batchStatus.textContent += ` ${attentionCount} 段预测 F1@10px 低于 40%，存在背景锁定或严重误定位。`;
  }
}

function setVideoSource(source) {
  state.source = source;
  els.showOriginal.classList.toggle("active", source === "original");
  els.showOverlay.classList.toggle("active", source === "overlay");
  els.showFinal.classList.toggle("active", source === "final");
  const url = state.dataset?.urls[source] || state.dataset?.urls.overlay;
  if (url) {
    const paused = els.video.paused;
    els.videoStatus.textContent = `正在加载${videoSourceLabel(source)}...`;
    els.video.src = url;
    if (!paused) {
      els.video.play().catch(() => {});
    }
  } else {
    els.videoStatus.textContent = "当前视频源不可用";
  }
}

function renderFrame(frame) {
  state.frame = frame;
  const fps = state.dataset?.analysis?.fps || 30;
  const total = state.dataset?.analysis?.frame_count || 0;
  const sourceLabel = videoSourceLabel(state.source);
  els.currentFrame.textContent = `第 ${frame} / ${Math.max(total - 1, 0)} 帧 · ${formatSeconds(frame / Math.max(fps, 1))} · ${sourceLabel} / ${trajectoryModeLabel(state.trajectoryMode)}`;
  const current = charts.miniCourt.renderFrame(frame);
  charts.speed.renderFrame(frame);
  charts.timeline.renderFrame(frame);
  charts.heatmap.renderFrame(frame);
  if (current?.ball) {
    els.courtFrameInfo.textContent = `第 ${frame} 帧 · 球位置 (${current.ball.court_x_m.toFixed(2)}m, ${current.ball.court_y_m.toFixed(2)}m) · ${Number(current.ball.speed_mps || 0).toFixed(2)} m/s`;
  } else {
    els.courtFrameInfo.textContent = `第 ${frame} 帧 · 暂无球位置`;
  }
}

function renderMetadata(data) {
  const uploaded = data.analysis.uploaded_video_meta || state.manifest.uploaded_video_meta || {};
  const analysis = data.analysis.analysis_meta || {};
  const tracking = data.quality.trajectory_metadata?.configuration || data.quality.trajectory_metadata?.tracknet || {};
  const uploadedRows = [
    ["文件", uploaded.file_name || "不可用"],
    ["时长", uploaded.duration_s ? `${Number(uploaded.duration_s).toFixed(2)}s` : "n/a"],
    ["帧数 / FPS", uploaded.frame_count ? `${uploaded.frame_count} / ${Number(uploaded.fps || 0).toFixed(1)}` : "n/a"],
    ["分辨率", uploaded.resolution || "n/a"],
    ["视频编码", uploaded.codec || "n/a"],
    ["音频", uploaded.audio_codec ? `${uploaded.audio_codec} · ${uploaded.audio_channels || ""} · ${uploaded.audio_sample_rate_hz || ""}Hz` : "n/a"],
  ];
  const analysisRows = [
    ["片段", videoTitle(data.entry)],
    ["时长", `${Number(analysis.duration_s || 0).toFixed(2)}s`],
    ["帧数 / FPS", `${analysis.frames || data.analysis.frame_count} / ${Number(analysis.fps || data.analysis.fps || 0).toFixed(1)}`],
    ["分辨率", analysis.resolution || "n/a"],
    ["轨迹来源", trajectoryModeLabel(state.trajectoryMode)],
    ["预测 F1@10px", state.trajectoryMode === "reference" ? "官方标注" : formatPredictionF1(data.activeTrajectoryQuality)],
    ["推理设置", state.trajectoryMode === "reference" ? "不适用" : `${tracking.eval_mode || "未知"} / th=${tracking.threshold ?? "?"} / ${tracking.device || "?"}`],
    ["近场 / 远场", `${formatPct(analysis.near_visible_rate ?? data.quality.player_coverage?.near)} / ${formatPct(analysis.far_visible_rate ?? data.quality.player_coverage?.far)}`],
  ];
  const toDl = (rows) => rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  els.uploadedMeta.innerHTML = toDl(uploadedRows);
  els.analysisMeta.innerHTML = toDl(analysisRows);
  els.exportPaths.textContent = JSON.stringify(data.entry.files, null, 2);
}

function renderQualityWarning(data) {
  const coverage = data.quality.player_coverage || {};
  const warnings = [];
  if ((coverage.near || 0) < 0.5) warnings.push("近场球员轨迹不完整。");
  if ((coverage.far || 0) < 0.5) warnings.push("远场球员轨迹不完整。");
  if (state.trajectoryMode === "reference") warnings.push("当前显示官方参考轨迹，不代表模型精度。");
  const metric = metricAt10(data.activeTrajectoryQuality);
  if (metric && metric.f1 < 0.4) warnings.push("模型定位精度低，存在背景锁定或严重误检。");
  if (state.trajectoryMode !== "reference" && !metric) warnings.push("当前预测尚无有效定位评分，请重新运行推理。");
  if (warnings.length) {
    els.qualityWarning.hidden = false;
    els.qualityWarning.textContent = `需复核：${warnings.join(" ")}`;
  } else {
    els.qualityWarning.hidden = true;
    els.qualityWarning.textContent = "";
  }
}

function updateTemporalLegend() {
  const labels = {
    speed: ["橙色：球速", "粉色：近场球员速度", "青色：远场球员速度"],
    distance: ["粉色：近场球员距离", "青色：远场球员距离"],
    confidence: ["粉色：近场球员置信度", "青色：远场球员置信度"],
  };
  els.temporalLegend.innerHTML = labels[state.metric]
    .map((text) => {
      const colorClass = text.includes("橙色") ? "ball" : (text.includes("粉色") ? "near" : "far");
      return `<span><i class="dot ${colorClass}"></i>${text}</span>`;
    })
    .join("");
}

function renderDataset(data) {
  state.dataset = data;
  state.trajectoryMode = data.ballModes.reference ? "reference" : data.trajectoryMode;
  data.ball = data.ballModes[state.trajectoryMode] || data.ball;
  data.activeTrajectoryQuality = data.qualityModes[state.trajectoryMode] || {};
  for (const button of els.trajectoryModes.querySelectorAll("[data-trajectory-mode]")) {
    button.classList.toggle("active", button.dataset.trajectoryMode === state.trajectoryMode);
    button.disabled = !data.ballModes[button.dataset.trajectoryMode];
    const availableLabel = data.qualityModes[button.dataset.trajectoryMode]?.label;
    if (availableLabel) button.textContent = availableLabel;
  }
  renderStatCards(els.statCards, data);
  renderQualityPanel(els.qualityPanel, data);
  renderQualityWarning(data);
  renderMetadata(data);
  els.videoMeta.textContent = `${Number(data.analysis.fps || 0).toFixed(1)} fps · ${data.analysis.frame_count || 0} 帧 · ${formatSeconds(data.analysis.duration_s)}`;
  els.qualityBadge.textContent = state.trajectoryMode === "reference"
    ? "官方标注"
    : `F1@10px ${formatPredictionF1(data.activeTrajectoryQuality)}`;
  els.showOriginal.disabled = !data.urls.original;
  els.showFinal.disabled = !data.urls.final;
  charts.miniCourt.updateData(data);
  charts.speed.updateData(data, state.metric);
  charts.timeline.updateData(data);
  charts.heatmap.updateData(data, state.heatmapMode);
  updateTemporalLegend();
  const nextSource = data.urls[state.source] ? state.source : "overlay";
  setVideoSource(nextSource);
  activateClipCard(data.entry.id);
  renderFrame(0);
}

function setTrajectoryMode(mode) {
  if (!state.dataset?.ballModes?.[mode]) return;
  state.trajectoryMode = mode;
  state.dataset.ball = state.dataset.ballModes[mode];
  state.dataset.activeTrajectoryQuality = state.dataset.qualityModes[mode] || {};
  for (const button of els.trajectoryModes.querySelectorAll("[data-trajectory-mode]")) {
    button.classList.toggle("active", button.dataset.trajectoryMode === mode);
    button.disabled = !state.dataset.ballModes[button.dataset.trajectoryMode];
  }
  renderStatCards(els.statCards, state.dataset);
  renderQualityPanel(els.qualityPanel, state.dataset);
  renderQualityWarning(state.dataset);
  renderMetadata(state.dataset);
  charts.miniCourt.updateData(state.dataset);
  charts.speed.updateData(state.dataset, state.metric);
  charts.timeline.updateData(state.dataset);
  charts.heatmap.updateData(state.dataset, state.heatmapMode);
  els.qualityBadge.textContent = mode === "reference"
    ? "官方标注"
    : `F1@10px ${formatPredictionF1(state.dataset.activeTrajectoryQuality)}`;
  renderFrame(state.frame);
}

async function loadSelectedVideo(videoId) {
  const entry = state.manifest.videos.find((item) => item.id === videoId);
  if (!entry) return;
  const dataset = await loadVideoDataset(entry);
  renderDataset(dataset);
}

function setupControls() {
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.dataset.tab;
      tabButtons.forEach((b) => b.classList.remove("active"));
      tabContents.forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      const targetEl = document.getElementById(targetTab);
      if (targetEl) targetEl.classList.add("active");
    });
  });

  const courtModeTrajectory = document.querySelector("#courtModeTrajectory");
  const courtModeDensity = document.querySelector("#courtModeDensity");
  if (courtModeTrajectory && courtModeDensity) {
    courtModeTrajectory.addEventListener("click", () => {
      courtModeTrajectory.classList.add("active");
      courtModeDensity.classList.remove("active");
      charts.miniCourt.setCourtMode("trajectory");
    });
    courtModeDensity.addEventListener("click", () => {
      courtModeDensity.classList.add("active");
      courtModeTrajectory.classList.remove("active");
      charts.miniCourt.setCourtMode("density");
    });
  }

  els.videoSelect.innerHTML = state.manifest.videos
    .map((video) => `<option value="${video.id}">${videoTitle(video)}</option>`)
    .join("");
  els.videoSelect.value = state.manifest.default_video;
  els.videoSelect.addEventListener("change", () => loadSelectedVideo(els.videoSelect.value));
  els.showOriginal.addEventListener("click", () => setVideoSource("original"));
  els.showOverlay.addEventListener("click", () => setVideoSource("overlay"));
  els.showFinal.addEventListener("click", () => setVideoSource("final"));
  els.exportButton.addEventListener("click", async () => {
    const payload = JSON.stringify(state.dataset.entry.files, null, 2);
    await navigator.clipboard?.writeText(payload).catch(() => {});
    els.exportButton.textContent = "已复制";
    setTimeout(() => {
      els.exportButton.textContent = "复制路径";
    }, 1200);
  });
  for (const button of els.trajectoryModes.querySelectorAll("[data-trajectory-mode]")) {
    button.addEventListener("click", () => setTrajectoryMode(button.dataset.trajectoryMode));
  }
  for (const button of document.querySelectorAll("[data-metric]")) {
    button.addEventListener("click", () => {
      state.metric = button.dataset.metric;
      document.querySelectorAll("[data-metric]").forEach((item) => item.classList.toggle("active", item === button));
      charts.speed.setMetric(state.metric);
      updateTemporalLegend();
      renderFrame(state.frame);
    });
  }
  for (const button of document.querySelectorAll("[data-heatmap]")) {
    button.addEventListener("click", () => {
      state.heatmapMode = button.dataset.heatmap;
      document.querySelectorAll("[data-heatmap]").forEach((item) => item.classList.toggle("active", item === button));
      charts.heatmap.setMode(state.heatmapMode);
    });
  }

  els.video.addEventListener("loadeddata", () => {
    els.videoStatus.textContent = `${videoSourceLabel(state.source)}已加载`;
  });
  els.video.addEventListener("canplay", () => {
    if (els.video.readyState >= 3) {
      els.videoStatus.textContent = `${videoSourceLabel(state.source)}可播放`;
    }
  });
  els.video.addEventListener("error", () => {
    els.videoStatus.textContent = "视频无法预览 · 请检查编码";
  });
}

async function boot() {
  state.manifest = await loadManifest();
  renderBatchOverview();
  setupControls();
  await loadSelectedVideo(state.manifest.default_video);
}

boot().catch((error) => {
  document.body.innerHTML = `<main class="app-shell"><p class="empty-note">${error.message}</p></main>`;
});
