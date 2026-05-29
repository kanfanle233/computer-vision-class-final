export function createSpeedChart(container, onSeek) {
  const margin = { top: 12, right: 16, bottom: 28, left: 42 };
  const width = 720;
  const height = 240;
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  const x = d3.scaleLinear().range([0, innerW]);
  const y = d3.scaleLinear().range([innerH, 0]);
  const cursor = g.append("line").attr("class", "cursor-line").attr("y1", 0).attr("y2", innerH);
  
  let state = null;
  let metric = "speed";

  function renderFrame(frame) {
    if (!state) return;
    cursor.attr("x1", x(frame)).attr("x2", x(frame));
  }

  function getFallbackConf(d, isBall = false) {
    if (d.confidence !== null && d.confidence !== undefined && !Number.isNaN(Number(d.confidence))) {
      return Number(d.confidence);
    }
    if (isBall) {
      return d.is_missing ? 0.0 : (d.visibility === 1 ? 0.9 : 0.0);
    } else {
      return (d.court_x_m === null || d.court_y_m === null) ? 0.0 : 0.9;
    }
  }

  function rowsForMetric(data) {
    if (metric === "distance") {
      return {
        ball: [],
        near: data.motion.filter((d) => d.role === "near").map((d) => ({ frame: d.frame, value: d.cumulative_distance_m || 0 })),
        far: data.motion.filter((d) => d.role === "far").map((d) => ({ frame: d.frame, value: d.cumulative_distance_m || 0 })),
        label: "Distance (m)",
      };
    }
    if (metric === "confidence") {
      return {
        ball: data.ball.map((d) => ({ frame: d.frame, value: getFallbackConf(d, true) })),
        near: data.players.filter((d) => d.role === "near").map((d) => ({ frame: d.frame, value: getFallbackConf(d) })),
        far: data.players.filter((d) => d.role === "far").map((d) => ({ frame: d.frame, value: getFallbackConf(d) })),
        label: "Confidence",
      };
    }
    const qLevel = data.quality.ball_quality_level || "Green";
    const showBallSpeed = qLevel !== "Red" && (!data.quality.ball_filter_applied || (data.quality.ball_spatial_rate || 0) >= 0.5);
    return {
      ball: showBallSpeed ? data.ball.filter((d) => !d.is_missing).map((d) => {
        let val = d.speed_mps;
        if (val !== null && val !== undefined && val > 38.0) val = null;
        return { frame: d.frame, value: val };
      }) : [],
      near: data.motion.filter((d) => d.role === "near").map((d) => {
        let val = d.speed_mps;
        if (val !== null && val !== undefined && val > 15.0) val = null;
        return { frame: d.frame, value: val };
      }),
      far: data.motion.filter((d) => d.role === "far").map((d) => {
        let val = d.speed_mps;
        if (val !== null && val !== undefined && val > 15.0) val = null;
        return { frame: d.frame, value: val };
      }),
      label: "Speed (m/s)",
    };
  }

  function updateData(data, nextMetric = metric) {
    state = data;
    metric = nextMetric;
    g.selectAll(".axis,.series,.series-area,.grid,.chart-caption,.missing-band").remove();
    
    const series = rowsForMetric(data);
    const hasValue = (d) => d.value !== null && d.value !== undefined && !Number.isNaN(Number(d.value));
    const line = d3.line().defined(hasValue).x((d) => x(d.frame)).y((d) => y(d.value));
    const area = d3.area().defined(hasValue).x((d) => x(d.frame)).y0(innerH).y1((d) => y(d.value));
    
    x.domain([0, Math.max(data.analysis.frame_count - 1, 1)]);
    
    if (metric === "confidence") {
      y.domain([0, 1.0]);
    } else {
      y.domain([0, Math.max(1, d3.max([...series.ball, ...series.near, ...series.far], (d) => d.value || 0) || 1)]).nice();
    }

    const missingBands = [];
    let start = null;
    for (let i = 0; i < data.ball.length; i++) {
      const b = data.ball[i];
      if (b.is_missing) {
        if (start === null) start = b.frame;
      } else {
        if (start !== null) {
          missingBands.push([start, b.frame - 1]);
          start = null;
        }
      }
    }
    if (start !== null) {
      missingBands.push([start, data.ball[data.ball.length - 1].frame]);
    }

    g.selectAll(".missing-band")
      .data(missingBands)
      .join("rect")
      .attr("class", "missing-band")
      .attr("x", (d) => x(d[0]))
      .attr("width", (d) => Math.max(1, x(d[1]) - x(d[0])))
      .attr("y", 0)
      .attr("height", innerH)
      .style("pointer-events", "none");

    g.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(6));
      
    g.append("g")
      .attr("class", "axis")
      .call(d3.axisLeft(y).ticks(5));
      
    g.append("g")
      .attr("class", "grid")
      .call(d3.axisLeft(y).tickSize(-innerW).tickFormat("").ticks(5))
      .selectAll("line")
      .attr("class", "grid-line");

    if (metric === "confidence") {
      if (series.ball.length) {
        g.append("path")
          .datum(series.ball)
          .attr("class", "series-area ball-area")
          .attr("d", area)
          .attr("fill", "rgba(237, 137, 54, 0.08)")
          .style("pointer-events", "none");
      }
      g.append("path")
        .datum(series.near)
        .attr("class", "series-area near-area")
        .attr("d", area)
        .attr("fill", "rgba(213, 63, 140, 0.08)")
        .style("pointer-events", "none");
      g.append("path")
        .datum(series.far)
        .attr("class", "series-area far-area")
        .attr("d", area)
        .attr("fill", "rgba(56, 178, 172, 0.08)")
        .style("pointer-events", "none");
    }

    if (series.ball.length) {
      g.append("path")
        .datum(series.ball)
        .attr("class", "series ball-speed")
        .attr("d", line);
    }
    g.append("path")
      .datum(series.near)
      .attr("class", "series speed-near")
      .attr("d", line);
    g.append("path")
      .datum(series.far)
      .attr("class", "series speed-far")
      .attr("d", line);

    g.append("text")
      .attr("class", "chart-caption")
      .attr("x", 0)
      .attr("y", 12)
      .text(series.label);

    svg.on("click", (event) => {
      const [mx] = d3.pointer(event, g.node());
      onSeek(Math.max(0, Math.min(Math.round(x.invert(mx)), data.analysis.frame_count - 1)));
    });
    
    renderFrame(0);
  }

  function setMetric(nextMetric) {
    if (!state) return;
    updateData(state, nextMetric);
  }

  return { updateData, renderFrame, setMetric };
}
