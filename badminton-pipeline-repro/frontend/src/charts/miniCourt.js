export function createMiniCourt(container, onSeek) {
  const root = d3.select(container);
  const svg = root.append("svg").attr("viewBox", "0 0 520 560").attr("role", "img");
  const padX = 34;
  const padY = 22;
  const courtW = 520 - padX * 2;
  const courtH = 560 - padY * 2;
  const x = d3.scaleLinear().range([padX, padX + courtW]);
  const y = d3.scaleLinear().range([padY, padY + courtH]);
  const court = svg.append("g");
  const trails = svg.append("g");
  const cursor = svg.append("g");
  
  let state = null;
  let courtMode = "trajectory";
  let currentFrameId = 0;

  const line = d3.line()
    .defined((d) => d.court_x_m !== null && d.court_y_m !== null)
    .x((d) => x(d.court_x_m))
    .y((d) => y(d.court_y_m));

  function drawCourt(analysis) {
    const width = analysis.court_size_m?.width || 6.1;
    const length = analysis.court_size_m?.length || 13.4;
    x.range([padX, padX + courtW]);
    x.domain([0, width]);
    y.domain([0, length]);
    court.selectAll("*").remove();
    court.append("rect")
      .attr("class", "court-bg")
      .attr("x", padX)
      .attr("y", padY)
      .attr("width", courtW)
      .attr("height", courtH);
      
    const singlesMargin = width * (0.46 / 6.1);
    const shortServiceFromNet = length * (1.98 / 13.4);
    const doublesServiceFromBaseline = length * (0.76 / 13.4);
    const netY = length / 2;
    const centerLineTopEndY = netY - shortServiceFromNet;
    const centerLineBottomStartY = netY + shortServiceFromNet;

    const lines = [
      // Outer Boundary (Doubles sideline and baseline)
      [[0, 0], [width, 0], [width, length], [0, length], [0, 0]],
      
      // Singles sidelines (Left and Right)
      [[singlesMargin, 0], [singlesMargin, length]],
      [[width - singlesMargin, 0], [width - singlesMargin, length]],
      
      // Net Line
      [[0, netY], [width, netY]],
      
      // Short Service Lines (Top and Bottom)
      [[0, centerLineTopEndY], [width, centerLineTopEndY]],
      [[0, centerLineBottomStartY], [width, centerLineBottomStartY]],
      
      // Doubles Long Service Lines (Top and Bottom)
      [[0, doublesServiceFromBaseline], [width, doublesServiceFromBaseline]],
      [[0, length - doublesServiceFromBaseline], [width, length - doublesServiceFromBaseline]],
      
      // Center Service Lines (Top and Bottom service courts only)
      [[width / 2, 0], [width / 2, centerLineTopEndY]],
      [[width / 2, centerLineBottomStartY], [width / 2, length]]
    ];

    for (const l of lines) {
      court
        .append("path")
        .attr("class", "court-line")
        .attr("d", d3.line().x((d) => x(d[0])).y((d) => y(d[1]))(l));
    }
  }

  function rowsFor(role) {
    if (!state) return [];
    return state.players
      .filter((d) => d.role === role && d.court_x_m !== null && d.court_y_m !== null)
      .sort((a, b) => a.frame - b.frame);
  }

  function renderDensity() {
    if (!state) return;
    trails.selectAll("*").remove();
    
    const allNear = rowsFor("near");
    const allFar = rowsFor("far");
    const allBall = state.ball.filter((d) => !d.is_missing && d.court_x_m !== null && d.court_y_m !== null);

    trails.selectAll(".density-near")
      .data(allNear)
      .join("circle")
      .attr("class", "density-near")
      .attr("r", 2.2)
      .attr("fill", "#d53f8c")
      .attr("opacity", 0.08)
      .attr("cx", (d) => x(d.court_x_m))
      .attr("cy", (d) => y(d.court_y_m));

    trails.selectAll(".density-far")
      .data(allFar)
      .join("circle")
      .attr("class", "density-far")
      .attr("r", 2.2)
      .attr("fill", "#38b2ac")
      .attr("opacity", 0.08)
      .attr("cx", (d) => x(d.court_x_m))
      .attr("cy", (d) => y(d.court_y_m));

    trails.selectAll(".density-ball")
      .data(allBall)
      .join("circle")
      .attr("class", "density-ball")
      .attr("r", 1.8)
      .attr("fill", "#ed8936")
      .attr("opacity", 0.12)
      .attr("cx", (d) => x(d.court_x_m))
      .attr("cy", (d) => y(d.court_y_m));
  }

  function renderFrame(frame) {
    if (!state) return;
    currentFrameId = frame;
    cursor.selectAll("*").remove();
    
    const current = {
      near: rowsFor("near").findLast((d) => d.frame <= frame),
      far: rowsFor("far").findLast((d) => d.frame <= frame),
      ball: state.ball.filter((d) => !d.is_missing && d.court_x_m !== null && d.court_y_m !== null).findLast((d) => d.frame <= frame),
    };

    if (courtMode === "trajectory") {
      trails.selectAll("*").remove();
      
      const nearTrail = rowsFor("near").filter((d) => d.frame <= frame);
      const farTrail = rowsFor("far").filter((d) => d.frame <= frame);
      const ballTrail = state.ball.filter((d) => !d.is_missing && d.court_x_m !== null && d.court_y_m !== null && d.frame <= frame);

      trails.append("path").datum(nearTrail).attr("class", "trajectory-near").attr("d", line);
      trails.append("path").datum(farTrail).attr("class", "trajectory-far").attr("d", line);
      trails.append("path").datum(ballTrail).attr("class", "trajectory-ball").attr("d", line);
    }

    const points = [
      ["near", current.near, "#d53f8c", 5.5],
      ["far", current.far, "#38b2ac", 5.5],
      ["ball", current.ball, "#ed8936", 4.5],
    ];
    
    cursor
      .selectAll("circle")
      .data(points.filter((d) => d[1]))
      .join("circle")
      .attr("class", "current-marker")
      .attr("r", (d) => d[3])
      .attr("fill", (d) => d[2])
      .attr("stroke", "#1a202c")
      .attr("stroke-width", 1.5)
      .attr("cx", (d) => x(d[1].court_x_m))
      .attr("cy", (d) => y(d[1].court_y_m));

    return current;
  }

  function updateData(data) {
    state = data;
    drawCourt(data.analysis);
    if (courtMode === "density") {
      renderDensity();
    } else {
      trails.selectAll("*").remove();
    }
    svg.on("click", (event) => {
      const [mx, my] = d3.pointer(event);
      const nearest = data.ball
        .filter((d) => !d.is_missing && d.court_x_m !== null && d.court_y_m !== null)
        .reduce((best, row) => {
          const dist = Math.hypot(x(row.court_x_m) - mx, y(row.court_y_m) - my);
          return !best || dist < best.dist ? { row, dist } : best;
        }, null);
      if (nearest) onSeek(nearest.row.frame);
    });
    renderFrame(currentFrameId);
  }

  function setCourtMode(nextMode) {
    courtMode = nextMode;
    if (!state) return;
    if (courtMode === "density") {
      renderDensity();
    } else {
      trails.selectAll("*").remove();
    }
    renderFrame(currentFrameId);
  }

  return { updateData, renderFrame, setCourtMode };
}
