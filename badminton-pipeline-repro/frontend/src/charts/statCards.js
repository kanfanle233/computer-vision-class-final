function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "0";
  }
  return Number(value).toFixed(digits);
}

function pct(value) {
  return `${formatNumber(Number(value || 0) * 100, 1)}%`;
}

export function renderStatCards(container, data) {
  const far = data.analysis.players?.far || {};
  const near = data.analysis.players?.near || {};
  const meta = data.analysis.analysis_meta || {};
  const qLevel = data.quality.ball_quality_level || "Green";
  const isRed = qLevel === "Red";
  const cards = [
    ["Frames", `${meta.frames || data.analysis.frame_count || 0}`],
    ["FPS", formatNumber(meta.fps || data.analysis.fps, 1)],
    ["Duration", `${formatNumber(meta.duration_s || data.analysis.duration_s, 1)} s`],
    ["Resolution", meta.resolution || "n/a"],
    ["Ball Visible", isRed ? "—" : pct(meta.ball_visible_rate ?? data.quality.ball_detection_rate)],
    ["Detection Gaps", isRed ? "质量门禁用" : `${meta.detection_gaps ?? (data.quality.ball_missing_segments || []).length}`],
    ["Near Dist", `${formatNumber(meta.near_distance_m ?? near.total_distance_m, 1)} m`],
    ["Far Dist", `${formatNumber(meta.far_distance_m ?? far.total_distance_m, 1)} m`],
    ["Max Speed", `${formatNumber(meta.max_speed_mps ?? Math.max(near.total_max_speed_mps || 0, far.total_max_speed_mps || 0), 1)} m/s`],
  ];

  container.innerHTML = cards
    .map(([label, value]) => `<article class="stat"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");
}

export function renderQualityPanel(container, data) {
  const quality = (data && data.quality) ? data.quality : data;
  const coverage = quality.player_coverage || {};
  const qLevel = quality.ball_quality_level || "Green";
  const items = [
    ["Ball Quality Level", `${qLevel}${qLevel === "Red" ? " — 球轨迹被质量门禁用" : qLevel === "Yellow" ? " — 球轨迹置信度偏低" : " — 球轨迹可信"}`],
    ["Ball Quality Score", `${(quality.ball_quality_score || 0).toFixed(0)} / 100`],
    ["Ball Visible Rate", pct(quality.ball_detection_rate)],
    ["Court-mapped Shuttle Rate", pct(quality.ball_spatial_rate)],
    ["Near Player Visible Rate", pct(coverage.near)],
    ["Far Player Visible Rate", pct(coverage.far)],
    ["Detection Gaps", `${(quality.ball_missing_segments || []).length}`],
  ];

  let html = `<div class="quality-list">` + items
    .map(([label, value]) => `<div class="quality-item"><span>${label}</span><strong>${value}</strong></div>`)
    .join("") + `</div>`;

  const ballData = data.ball || [];
  const isRed = qLevel === "Red";

  if (isRed) {
    html += `
      <div class="quality-subsections">
        <div class="confidence-card">
          <h3>球轨迹分析</h3>
          <div class="red-empty-state">球轨迹因质量门被禁用，仅展示球员分析。<br>TrackNet 在本视频中的球检测不可靠，因此不展示球速和球轨迹结论。</div>
        </div>
      </div>
    `;
    container.innerHTML = html;
    return;
  }

  const totalFrames = ballData.length || 1;
  let high = 0, mid = 0, low = 0;
  for (const d of ballData) {
    const conf = d.is_missing ? 0.0 : (d.confidence !== null && d.confidence !== undefined ? d.confidence : (d.visibility === 1 ? 0.9 : 0.0));
    if (conf >= 0.75) high++;
    else if (conf > 0.2) mid++;
    else low++;
  }
  const pctHigh = (high / totalFrames * 100).toFixed(1);
  const pctMid = (mid / totalFrames * 100).toFixed(1);
  const pctLow = (low / totalFrames * 100).toFixed(1);

  const missingSegments = [];
  let start = null;
  for (let i = 0; i < ballData.length; i++) {
    const b = ballData[i];
    if (b.is_missing) {
      if (start === null) start = b.frame;
    } else {
      if (start !== null) {
        missingSegments.push([start, b.frame - 1]);
        start = null;
      }
    }
  }
  if (start !== null) {
    missingSegments.push([start, ballData[ballData.length - 1].frame]);
  }

  const gapRows = missingSegments.map((seg, idx) => {
    const startS = (seg[0] / (data.analysis.fps || 30)).toFixed(2);
    const endS = (seg[1] / (data.analysis.fps || 30)).toFixed(2);
    const len = seg[1] - seg[0] + 1;
    return `
      <div class="gap-item" data-frame="${seg[0]}">
        <span class="gap-range">Gap ${idx + 1}: Fr ${seg[0]}-${seg[1]}</span>
        <span class="gap-time">${startS}s - ${endS}s (${len} frames)</span>
      </div>
    `;
  }).join("");

  const gapContent = gapRows.length ? gapRows : `<div class="gap-empty">No missing detections found in this video.</div>`;

  html += `
    <div class="quality-subsections">
      <div class="confidence-card">
        <h3>Shuttle Confidence Distribution</h3>
        <div class="confidence-bars">
          <div class="confidence-row">
            <span class="confidence-label">High (&gt;=0.75)</span>
            <div class="confidence-track">
              <div class="confidence-fill high" data-width="${pctHigh}"></div>
            </div>
            <span class="confidence-value">${pctHigh}%</span>
          </div>
          <div class="confidence-row">
            <span class="confidence-label">Medium (0.2-0.75)</span>
            <div class="confidence-track">
              <div class="confidence-fill mid" data-width="${pctMid}"></div>
            </div>
            <span class="confidence-value">${pctMid}%</span>
          </div>
          <div class="confidence-row">
            <span class="confidence-label">Low (&lt;0.2)</span>
            <div class="confidence-track">
              <div class="confidence-fill low" data-width="${pctLow}"></div>
            </div>
            <span class="confidence-value">${pctLow}%</span>
          </div>
        </div>
      </div>

      <div class="gap-card">
        <h3>Detection Gap Segments List</h3>
        <div class="gap-list-box">${gapContent}</div>
      </div>
    </div>
  `;

  container.innerHTML = html;

  container.querySelectorAll(".confidence-fill").forEach((bar) => {
    bar.style.width = `${bar.dataset.width}%`;
  });

  container.querySelectorAll(".gap-item").forEach((item) => {
    item.addEventListener("click", () => {
      const frame = parseInt(item.dataset.frame);
      if (window.seekFrameGlobal) {
        window.seekFrameGlobal(frame);
      }
    });
  });
}
