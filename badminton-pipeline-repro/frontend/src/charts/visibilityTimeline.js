export function createVisibilityTimeline(container, onSeek) {
  const width = 520;
  const height = 120;
  const margin = { top: 14, right: 12, bottom: 28, left: 12 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  const x = d3.scaleLinear().range([0, innerW]);
  const cursor = g.append("line").attr("class", "cursor-line").attr("y1", 0).attr("y2", innerH);
  
  let state = null;
  const tooltip = d3.select("#timelineTooltip");

  function renderFrame(frame) {
    if (!state) return;
    cursor.attr("x1", x(frame)).attr("x2", x(frame));
  }

  function updateData(data) {
    state = data;
    g.selectAll(".axis,.tick-rect,.timeline-empty-msg").remove();

    const qLevel = data.quality?.ball_quality_level || "Green";
    if (qLevel === "Red" || !data.ball || data.ball.length === 0) {
      // Show empty state message for Red quality videos
      x.domain([0, Math.max(data.analysis.frame_count, 1)]);
      g.append("text")
        .attr("class", "timeline-empty-msg")
        .attr("x", innerW / 2)
        .attr("y", innerH / 2 + 10)
        .attr("text-anchor", "middle")
        .attr("fill", "#888")
        .attr("font-size", "11px")
        .text(qLevel === "Red" ? "球轨迹因质量门被禁用 — 仅展示球员分析" : "No ball data available");
      g.append("g")
        .attr("class", "axis")
        .attr("transform", `translate(0,${innerH})`)
        .call(d3.axisBottom(x).ticks(5));
      return;
    }
    x.domain([0, Math.max(data.analysis.frame_count, 1)]);
    const barW = Math.max(1.2, innerW / Math.max(data.analysis.frame_count, 1));
    
    g.selectAll(".tick-rect")
      .data(data.ball)
      .join("rect")
      .attr("class", (d) => `tick-rect ${
        d.is_missing ? "timeline-missing" : (d.confidence !== null && d.confidence < 0.5 ? "timeline-low" : "timeline-visible")
      }`)
      .attr("x", (d) => x(d.frame))
      .attr("y", 18)
      .attr("width", barW)
      .attr("height", 34)
      .style("cursor", "pointer")
      .on("mouseover", (event, d) => {
        const frame = d.frame;
        const timeS = d.time_s !== null && d.time_s !== undefined ? d.time_s : frame / (data.analysis.fps || 30);
        
        const ballStatus = d.is_missing ? `<span class="status-missing">Missing</span>` :
                           (d.confidence < 0.5 ? `<span class="status-low">Low Conf</span>` :
                            `<span class="status-valid">Valid</span>`);
        
        const nearRow = data.players.find((p) => p.role === "near" && p.frame === frame);
        const farRow = data.players.find((p) => p.role === "far" && p.frame === frame);

        const getPlayerStatus = (row) => {
          if (!row || row.court_x_m === null || row.court_y_m === null) {
            return `<span class="status-missing">Missing</span>`;
          }
          const conf = row.confidence ?? 0.9;
          if (conf < 0.5) {
            return `<span class="status-low">Low Conf</span>`;
          }
          return `<span class="status-valid">Valid</span>`;
        };

        const nearStatus = getPlayerStatus(nearRow);
        const farStatus = getPlayerStatus(farRow);

        const htmlContent = `
          <div class="tooltip-title">Frame Detail</div>
          <strong>Index:</strong> ${frame}<br/>
          <strong>Time:</strong> ${timeS.toFixed(3)} s<br/>
          <strong>Shuttle:</strong> ${ballStatus}<br/>
          <strong>Near Player:</strong> ${nearStatus}<br/>
          <strong>Far Player:</strong> ${farStatus}
        `;
        
        tooltip.html(htmlContent)
          .style("display", "block")
          .style("left", `${event.pageX + 16}px`)
          .style("top", `${event.pageY - 16}px`);
      })
      .on("mousemove", (event) => {
        tooltip
          .style("left", `${event.pageX + 16}px`)
          .style("top", `${event.pageY - 16}px`);
      })
      .on("mouseout", () => {
        tooltip.style("display", "none");
      })
      .on("click", (event, d) => {
        onSeek(d.frame);
      });

    g.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(5));

    svg.on("click", (event) => {
      // 允许点击坐标轴外部区域快速 seek
      if (event.target.tagName !== "rect") {
        const [mx] = d3.pointer(event, g.node());
        onSeek(Math.max(0, Math.min(Math.round(x.invert(mx)), data.analysis.frame_count - 1)));
      }
    });

    renderFrame(0);
  }

  return { updateData, renderFrame };
}
