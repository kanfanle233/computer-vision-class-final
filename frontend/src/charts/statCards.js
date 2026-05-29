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
  const trajectory = data.activeTrajectoryQuality || {};
  const metric10 = trajectory.evaluation?.metrics?.f1_at_10px;
  const isReference = trajectory.source_type === "reference";
  const cards = [
    ["总帧数", `${meta.frames || data.analysis.frame_count || 0}`],
    ["帧率", formatNumber(meta.fps || data.analysis.fps, 1)],
    ["时长", `${formatNumber(meta.duration_s || data.analysis.duration_s, 1)} s`],
    ["分辨率", meta.resolution || "n/a"],
    ["轨迹来源", trajectory.label || "未分类"],
    ["F1@10px", isReference ? "标注" : (metric10 ? pct(metric10.f1) : "待重跑")],
    ["轨迹缺口", `${(trajectory.ball_missing_segments || data.quality.ball_missing_segments || []).length}`],
    ["近场距离", `${formatNumber(meta.near_distance_m ?? near.total_distance_m, 1)} m`],
    ["远场距离", `${formatNumber(meta.far_distance_m ?? far.total_distance_m, 1)} m`],
    ["最高速度", `${formatNumber(meta.max_speed_mps ?? Math.max(near.total_max_speed_mps || 0, far.total_max_speed_mps || 0), 1)} m/s`],
  ];

  container.innerHTML = cards
    .map(([label, value]) => `<article class="stat"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");
}

export function renderQualityPanel(container, data) {
  const quality = (data && data.quality) ? data.quality : data;
  const trajectory = data.activeTrajectoryQuality || quality;
  const coverage = quality.player_coverage || {};
  const metric10 = trajectory.evaluation?.metrics?.f1_at_10px;
  const metric20 = trajectory.evaluation?.metrics?.f1_at_20px;
  const errorMedian = metric10?.visible_pair_error_px?.median;
  const items = [
    ["轨迹来源", trajectory.label || "未分类"],
    ["F1@10px", trajectory.source_type === "reference" ? "官方参考" : (metric10 ? pct(metric10.f1) : "待重跑")],
    ["F1@20px", trajectory.source_type === "reference" ? "官方参考" : (metric20 ? pct(metric20.f1) : "待重跑")],
    ["位置中位误差", errorMedian === null || errorMedian === undefined ? "--" : `${formatNumber(errorMedian, 1)} px`],
    ["近场球员检出率", pct(coverage.near)],
    ["远场球员检出率", pct(coverage.far)],
    ["漏检区段数", `${(trajectory.ball_missing_segments || []).length}`],
  ];

  let html = `<div class="quality-list">` + items
    .map(([label, value]) => `<div class="quality-item"><span>${label}</span><strong>${value}</strong></div>`)
    .join("") + `</div>`;

  const ballData = data.ball || [];
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
        <span class="gap-range">缺口 ${idx + 1}：帧 ${seg[0]}-${seg[1]}</span>
        <span class="gap-time">${startS}s - ${endS}s (${len} 帧)</span>
      </div>
    `;
  }).join("");

  const gapContent = gapRows.length ? gapRows : `<div class="gap-empty">当前片段未发现漏检区段。</div>`;

  html += `
    <div class="quality-subsections">
      <div class="confidence-card">
        <h3>羽毛球置信度分布</h3>
        <div class="confidence-bars">
          <div class="confidence-row">
            <span class="confidence-label">高 (&gt;=0.75)</span>
            <div class="confidence-track">
              <div class="confidence-fill high" data-width="${pctHigh}"></div>
            </div>
            <span class="confidence-value">${pctHigh}%</span>
          </div>
          <div class="confidence-row">
            <span class="confidence-label">中 (0.2-0.75)</span>
            <div class="confidence-track">
              <div class="confidence-fill mid" data-width="${pctMid}"></div>
            </div>
            <span class="confidence-value">${pctMid}%</span>
          </div>
          <div class="confidence-row">
            <span class="confidence-label">低 (&lt;0.2)</span>
            <div class="confidence-track">
              <div class="confidence-fill low" data-width="${pctLow}"></div>
            </div>
            <span class="confidence-value">${pctLow}%</span>
          </div>
        </div>
      </div>

      <div class="gap-card">
        <h3>漏检区段列表</h3>
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
