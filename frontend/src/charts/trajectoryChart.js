export function createTrajectoryChart(container, onSeek) {
  const margin = { top: 12, right: 18, bottom: 28, left: 42 };
  const width = 520;
  const height = 220;
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  const x = d3.scaleLinear().range([0, innerW]);
  const y = d3.scaleLinear().range([innerH, 0]);
  const line = d3.line().defined((d) => !d.is_missing).x((d) => x(d.frame)).y((d) => y(d.speed_mps || 0));
  const cursor = g.append("line").attr("class", "cursor-line").attr("y1", 0).attr("y2", innerH);
  let state = null;

  function renderFrame(frame) {
    if (!state) return;
    cursor.attr("x1", x(frame)).attr("x2", x(frame));
  }

  function updateData(data) {
    state = data;
    g.selectAll(".axis,.series,.grid").remove();
    x.domain([0, Math.max(data.analysis.frame_count - 1, 1)]);
    y.domain([0, Math.max(1, d3.max(data.ball, (d) => d.speed_mps || 0) || 1)]).nice();
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${innerH})`).call(d3.axisBottom(x).ticks(5));
    g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(5));
    g.append("path").datum(data.ball).attr("class", "series ball-speed").attr("d", line);
    g.append("text").attr("class", "chart-caption").attr("x", 0).attr("y", 12).text("speed m/s");
    svg.on("click", (event) => {
      const [mx] = d3.pointer(event, g.node());
      onSeek(Math.round(x.invert(mx)));
    });
    renderFrame(0);
  }

  return { updateData, renderFrame };
}
