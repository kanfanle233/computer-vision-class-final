import { loadManifest, loadVideoDataset } from "./dataLoader.js?v=spatial-merge-20260527";
import { createVideoSync } from "./videoSync.js";
import { createMiniCourt } from "./charts/miniCourt.js?v=spatial-merge-20260527";
import { createSpeedChart } from "./charts/speedChart.js?v=spatial-merge-20260527";
import { createVisibilityTimeline } from "./charts/visibilityTimeline.js?v=spatial-merge-20260527";
import { createZoneOccupancy } from "./charts/zoneOccupancy.js?v=spatial-merge-20260527";
import { renderQualityPanel, renderStatCards } from "./charts/statCards.js?v=spatial-merge-20260527";

const els = {
  videoSelect: document.querySelector("#videoSelect"),
  video: document.querySelector("#matchVideo"),
  showOriginal: document.querySelector("#showOriginal"),
  showOverlay: document.querySelector("#showOverlay"),
  showFinal: document.querySelector("#showFinal"),
  exportButton: document.querySelector("#exportButton"),
  statCards: document.querySelector("#statCards"),
  currentFrame: document.querySelector("#currentFrame"),
  videoMeta: document.querySelector("#videoMeta"),
  videoStatus: document.querySelector("#videoStatus"),
  qualityBadge: document.querySelector("#qualityBadge"),
  qualityPanel: document.querySelector("#qualityPanel"),
  qualityWarning: document.querySelector("#qualityWarning"),
  courtFrameInfo: document.querySelector("#courtFrameInfo"),
  zoneInsight: document.querySelector("#zoneInsight"),
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
  frame: 0,
};

const charts = {
  miniCourt: createMiniCourt(document.querySelector("#miniCourt"), seekFrame),
  speed: createSpeedChart(document.querySelector("#speedChart"), seekFrame),
  timeline: createVisibilityTimeline(document.querySelector("#visibilityTimeline"), seekFrame),
  zone: createZoneOccupancy(document.querySelector("#zoneOccupancy"), els.zoneInsight, seekFrame),
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
  return { original: "Original", overlay: "Overlay", final: "Final Result" }[source] || source;
}

function setVideoSource(source) {
  state.source = source;
  els.showOriginal.classList.toggle("active", source === "original");
  els.showOverlay.classList.toggle("active", source === "overlay");
  els.showFinal.classList.toggle("active", source === "final");
  const url = state.dataset?.urls[source] || state.dataset?.urls.overlay;
  if (url) {
    const paused = els.video.paused;
    els.videoStatus.textContent = `Loading ${videoSourceLabel(source)} preview...`;
    els.video.src = url;
    if (!paused) {
      els.video.play().catch(() => {});
    }
  } else {
    els.videoStatus.textContent = "Video source unavailable";
  }
}

function renderFrame(frame) {
  state.frame = frame;
  const fps = state.dataset?.analysis?.fps || 30;
  const total = state.dataset?.analysis?.frame_count || 0;
  const sourceLabel = videoSourceLabel(state.source);
  els.currentFrame.textContent = `Frame ${frame} / ${Math.max(total - 1, 0)} · Time ${formatSeconds(frame / Math.max(fps, 1))} · Mode ${sourceLabel}`;
  const current = charts.miniCourt.renderFrame(frame);
  charts.speed.renderFrame(frame);
  charts.timeline.renderFrame(frame);
  charts.zone.renderFrame(frame);
  if (current?.ball) {
    els.courtFrameInfo.textContent = `Frame ${frame} · Ball (${current.ball.court_x_m.toFixed(2)}m, ${current.ball.court_y_m.toFixed(2)}m) · ${Number(current.ball.speed_mps || 0).toFixed(2)} m/s`;
  } else {
    els.courtFrameInfo.textContent = `Frame ${frame} · Ball position unavailable`;
  }
}

function renderMetadata(data) {
  const uploaded = data.analysis.uploaded_video_meta || state.manifest.uploaded_video_meta || {};
  const analysis = data.analysis.analysis_meta || {};
  const uploadedRows = [
    ["File", uploaded.file_name || "Unavailable"],
    ["Duration", uploaded.duration_s ? `${Number(uploaded.duration_s).toFixed(2)}s` : "n/a"],
    ["Frames / FPS", uploaded.frame_count ? `${uploaded.frame_count} / ${Number(uploaded.fps || 0).toFixed(1)}` : "n/a"],
    ["Resolution", uploaded.resolution || "n/a"],
    ["Video Codec", uploaded.codec || "n/a"],
    ["Audio", uploaded.audio_codec ? `${uploaded.audio_codec} · ${uploaded.audio_channels || ""} · ${uploaded.audio_sample_rate_hz || ""}Hz` : "n/a"],
  ];
  const analysisRows = [
    ["Clip", analysis.video_id || data.analysis.video_id],
    ["Duration", `${Number(analysis.duration_s || 0).toFixed(2)}s`],
    ["Frames / FPS", `${analysis.frames || data.analysis.frame_count} / ${Number(analysis.fps || data.analysis.fps || 0).toFixed(1)}`],
    ["Resolution", analysis.resolution || "n/a"],
    ["Ball Visible", formatPct(analysis.ball_visible_rate ?? data.quality.ball_detection_rate)],
    ["Ball Quality", `${data.quality.ball_quality_level || "Green"} (score: ${(data.quality.ball_quality_score || 0).toFixed(0)})`],
    ["Court-mapped Shuttle", formatPct(analysis.ball_spatial_rate ?? data.quality.ball_spatial_rate)],
    ["Near / Far Visible", `${formatPct(analysis.near_visible_rate ?? data.quality.player_coverage?.near)} / ${formatPct(analysis.far_visible_rate ?? data.quality.player_coverage?.far)}`],
  ];
  const toDl = (rows) => rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  els.uploadedMeta.innerHTML = toDl(uploadedRows);
  els.analysisMeta.innerHTML = toDl(analysisRows);
  els.exportPaths.textContent = JSON.stringify(data.entry.files, null, 2);
}

function renderQualityWarning(data) {
  const qLevel = data.quality.ball_quality_level || "Green";
  const coverage = data.quality.player_coverage || {};
  const warnings = [];
  if ((coverage.near || 0) < 0.5) warnings.push("Near-player trajectory is incomplete.");
  if ((coverage.far || 0) < 0.5) warnings.push("Far-player trajectory is incomplete.");

  if (qLevel === "Red") {
    warnings.push("球轨迹质量为 Red：TrackNet 检测不可靠，球轨迹/球速不作为结论展示。仅保留球员运动分析。");
  } else if (qLevel === "Yellow") {
    warnings.push("球轨迹质量为 Yellow：置信度偏低，仅供参考。");
    if ((data.quality.ball_detection_rate || 0) < 0.75) warnings.push("Ball detection has long missing periods.");
  } else {
    if ((data.quality.ball_detection_rate || 0) < 0.75) warnings.push("Ball detection has long missing periods.");
    if (data.quality.ball_filter_applied && (data.quality.ball_spatial_rate || 0) < 0.5) {
      warnings.push("Ambiguous or airborne shuttle points are omitted from the court map.");
    }
    if ((data.quality.ball_filtered_frames || 0) > 0) warnings.push("Shuttle path is heuristic-filtered; verify it against video before reporting.");
  }
  if (warnings.length) {
    els.qualityWarning.hidden = false;
    els.qualityWarning.textContent = warnings.join(" ");
    els.qualityWarning.className = "quality-warning" + (qLevel === "Red" ? " warning-red" : qLevel === "Green" ? " warning-green" : "");
  } else {
    els.qualityWarning.hidden = true;
    els.qualityWarning.textContent = "";
  }
}

function updateTemporalLegend() {
  const qLevel = state.dataset?.quality?.ball_quality_level || "Green";
  const isRed = qLevel === "Red";
  const hideBallSpeed = isRed || (state.dataset?.quality?.ball_filter_applied && (state.dataset.quality.ball_spatial_rate || 0) < 0.5);
  const ballLabel = isRed ? "Orange: Shuttle speed unavailable (quality=Red)" : (hideBallSpeed ? "Orange: Shuttle speed hidden (insufficient projection)" : "Orange: Filtered projected shuttle speed");
  const labels = {
    speed: [
      ballLabel,
      "Pink: Near-player speed",
      "Cyan: Far-player speed",
    ],
    distance: ["Pink: Near-player distance", "Cyan: Far-player distance"],
    confidence: ["Pink: Near-player confidence", "Cyan: Far-player confidence"],
  };
  els.temporalLegend.innerHTML = labels[state.metric]
    .map((text) => {
      const colorClass = text.includes("Orange") ? "ball" : (text.includes("Pink") ? "near" : "far");
      return `<span><i class="dot ${colorClass}"></i>${text}</span>`;
    })
    .join("");
}

function renderDataset(data) {
  state.dataset = data;
  renderStatCards(els.statCards, data);
  renderQualityPanel(els.qualityPanel, data);
  renderQualityWarning(data);
  renderMetadata(data);
  els.videoMeta.textContent = `${Number(data.analysis.fps || 0).toFixed(1)} fps · ${data.analysis.frame_count || 0} frames · ${formatSeconds(data.analysis.duration_s)}`;
  const qLevel = data.quality.ball_quality_level || "Green";
  if (qLevel === "Green") {
    els.qualityBadge.textContent = `Ball Trajectory ✓ (${formatPct(data.quality.ball_detection_rate)})`;
    els.qualityBadge.className = "quality-badge quality-green";
  } else if (qLevel === "Yellow") {
    els.qualityBadge.textContent = `Ball Trajectory ~ (${formatPct(data.quality.ball_detection_rate)})`;
    els.qualityBadge.className = "quality-badge quality-yellow";
  } else {
    els.qualityBadge.textContent = `Ball Trajectory ✗ — 仅展示球员分析`;
    els.qualityBadge.className = "quality-badge quality-red";
  }
  els.showOriginal.disabled = !data.urls.original;
  els.showFinal.disabled = !data.urls.final;
  charts.miniCourt.updateData(data);
  charts.speed.updateData(data, state.metric);
  charts.timeline.updateData(data);
  charts.zone.updateData(data);
  updateTemporalLegend();
  const nextSource = data.urls[state.source] ? state.source : "overlay";
  setVideoSource(nextSource);
  renderFrame(0);
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

  const qualityRank = { Green: 0, Yellow: 1, Red: 2 };
  const videosForSelect = [...state.manifest.videos].sort((a, b) => {
    const qa = a.quality?.ball_quality_level || "Green";
    const qb = b.quality?.ball_quality_level || "Green";
    return (qualityRank[qa] ?? 3) - (qualityRank[qb] ?? 3) || (a.title || a.id).localeCompare(b.title || b.id);
  });
  els.videoSelect.innerHTML = videosForSelect
    .map((video) => {
      const qLevel = video.quality?.ball_quality_level || "Green";
      const mode = qLevel === "Green" ? "Ball trajectory" : qLevel === "Yellow" ? "Low-confidence ball" : "Players only";
      return `<option value="${video.id}">${video.title || video.id} [${qLevel} · ${mode}]</option>`;
    })
    .join("");
  els.videoSelect.value = state.manifest.default_video;
  els.videoSelect.addEventListener("change", () => loadSelectedVideo(els.videoSelect.value));
  els.showOriginal.addEventListener("click", () => setVideoSource("original"));
  els.showOverlay.addEventListener("click", () => setVideoSource("overlay"));
  els.showFinal.addEventListener("click", () => setVideoSource("final"));
  els.exportButton.addEventListener("click", async () => {
    const payload = JSON.stringify(state.dataset.entry.files, null, 2);
    await navigator.clipboard?.writeText(payload).catch(() => {});
    els.exportButton.textContent = "Copied";
    setTimeout(() => {
      els.exportButton.textContent = "Export";
    }, 1200);
  });
  for (const button of document.querySelectorAll("[data-metric]")) {
    button.addEventListener("click", () => {
      state.metric = button.dataset.metric;
      document.querySelectorAll("[data-metric]").forEach((item) => item.classList.toggle("active", item === button));
      charts.speed.setMetric(state.metric);
      updateTemporalLegend();
      renderFrame(state.frame);
    });
  }
  els.video.addEventListener("loadeddata", () => {
    els.videoStatus.textContent = `${videoSourceLabel(state.source)} preview loaded`;
  });
  els.video.addEventListener("canplay", () => {
    if (els.video.readyState >= 3) {
      els.videoStatus.textContent = `${videoSourceLabel(state.source)} ready to play`;
    }
  });
  els.video.addEventListener("error", () => {
    els.videoStatus.textContent = "Preview unavailable · check codec";
  });
}

async function boot() {
  state.manifest = await loadManifest();
  setupControls();
  await loadSelectedVideo(state.manifest.default_video);
}

boot().catch((error) => {
  document.body.innerHTML = `<main class="app-shell"><p class="empty-note">${error.message}</p></main>`;
});
