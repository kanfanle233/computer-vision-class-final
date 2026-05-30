export function createHeatmapLayer(canvas) {
  const ctx = canvas.getContext("2d");
  let state = null;
  let mode = "separated";

  function drawCourt(offsetX, w, h, titleText) {
    ctx.fillStyle = "#4a5568";
    ctx.font = "600 11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(titleText, offsetX + w / 2, 14);

    ctx.strokeStyle = "#cbd5e0";
    ctx.lineWidth = 1;

    const cw = w - 36;
    const ch = h - 36;
    const courtW = state?.analysis?.court_size_m?.width || 6.1;
    const courtH = state?.analysis?.court_size_m?.length || 13.4;

    const sx = (cx) => offsetX + 18 + (cx / courtW) * cw;
    const sy = (cy) => 20 + (cy / courtH) * ch;

    const singlesMargin = courtW * (0.46 / 6.1);
    const shortServiceFromNet = courtH * (1.98 / 13.4);
    const doublesServiceFromBaseline = courtH * (0.76 / 13.4);
    const netY = courtH / 2;
    const centerLineTopEndY = netY - shortServiceFromNet;
    const centerLineBottomStartY = netY + shortServiceFromNet;

    const lines = [
      // Outer Boundary (Doubles sideline and baseline)
      [[0, 0], [courtW, 0], [courtW, courtH], [0, courtH], [0, 0]],
      
      // Singles sidelines (Left and Right)
      [[singlesMargin, 0], [singlesMargin, courtH]],
      [[courtW - singlesMargin, 0], [courtW - singlesMargin, courtH]],
      
      // Net Line
      [[0, netY], [courtW, netY]],
      
      // Short Service Lines (Top and Bottom)
      [[0, centerLineTopEndY], [courtW, centerLineTopEndY]],
      [[0, centerLineBottomStartY], [courtW, centerLineBottomStartY]],
      
      // Doubles Long Service Lines (Top and Bottom)
      [[0, doublesServiceFromBaseline], [courtW, doublesServiceFromBaseline]],
      [[0, courtH - doublesServiceFromBaseline], [courtW, courtH - doublesServiceFromBaseline]],
      
      // Center Service Lines (Top and Bottom service courts only)
      [[courtW / 2, 0], [courtW / 2, centerLineTopEndY]],
      [[courtW / 2, centerLineBottomStartY], [courtW / 2, courtH]]
    ];

    for (const line of lines) {
      ctx.beginPath();
      ctx.moveTo(sx(line[0][0]), sy(line[0][1]));
      for (let i = 1; i < line.length; i++) {
        ctx.lineTo(sx(line[i][0]), sy(line[i][1]));
      }
      ctx.stroke();
    }
  }

  function drawPoint(x, y, color, radius) {
    const grd = ctx.createRadialGradient(x, y, 0, x, y, radius);
    grd.addColorStop(0, color);
    grd.addColorStop(1, "rgba(255, 255, 255, 0)");
    ctx.fillStyle = grd;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  function updateData(data, nextMode = mode) {
    state = data;
    mode = nextMode;
    const width = canvas.width;
    const height = canvas.height;
    const courtW = data.analysis.court_size_m?.width || 6.1;
    const courtH = data.analysis.court_size_m?.length || 13.4;
    const radius = Math.max(12, Math.min(22, width / 54));

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#fbfdff";
    ctx.fillRect(0, 0, width, height);

    if (mode === "separated") {
      const subW = width / 3;
      const splitRadius = Math.max(8, Math.min(15, subW / 22));
      
      drawCourt(0, subW, height, "Shuttle Density");
      const scaleX_A = (v) => 18 + (v / courtW) * (subW - 36);
      const scaleY_A = (v) => 20 + (v / courtH) * (height - 36);
      for (const r of data.ball.filter((d) => !d.is_missing && d.court_x_m !== null && d.court_y_m !== null)) {
        drawPoint(scaleX_A(r.court_x_m), scaleY_A(r.court_y_m), "rgba(237, 137, 54, 0.22)", splitRadius);
      }

      drawCourt(subW, subW, height, "Near Density");
      const scaleX_B = (v) => subW + 18 + (v / courtW) * (subW - 36);
      const scaleY_B = (v) => 20 + (v / courtH) * (height - 36);
      const nearRows = data.players.filter((d) => d.role === "near" && d.court_x_m !== null && d.court_y_m !== null);
      for (const r of nearRows) {
        drawPoint(scaleX_B(r.court_x_m), scaleY_B(r.court_y_m), "rgba(213, 63, 140, 0.2)", splitRadius);
      }

      drawCourt(2 * subW, subW, height, "Far Density");
      const scaleX_C = (v) => 2 * subW + 18 + (v / courtW) * (subW - 36);
      const scaleY_C = (v) => 20 + (v / courtH) * (height - 36);
      const farRows = data.players.filter((d) => d.role === "far" && d.court_x_m !== null && d.court_y_m !== null);
      for (const r of farRows) {
        drawPoint(scaleX_C(r.court_x_m), scaleY_C(r.court_y_m), "rgba(56, 178, 172, 0.2)", splitRadius);
      }
    } 
    else {
      let title = "Match Spatial Density";
      if (mode === "ball") title = "Shuttle Density";
      if (mode === "near") title = "Near-Player Density";
      if (mode === "far") title = "Far-Player Density";
      
      drawCourt(0, width, height, title);

      const scaleX = (v) => 18 + (v / courtW) * (width - 36);
      const scaleY = (v) => 20 + (v / courtH) * (height - 36);

      if (mode === "all" || mode === "ball") {
        for (const row of data.ball.filter((d) => !d.is_missing && d.court_x_m !== null && d.court_y_m !== null)) {
          drawPoint(scaleX(row.court_x_m), scaleY(row.court_y_m), "rgba(237, 137, 54, 0.18)", radius);
        }
      }
      if (mode === "all" || mode === "near" || mode === "far") {
        const rows = data.players.filter((d) => d.court_x_m !== null && d.court_y_m !== null && (mode === "all" || d.role === mode));
        for (const row of rows) {
          drawPoint(scaleX(row.court_x_m), scaleY(row.court_y_m), row.role === "near" ? "rgba(213, 63, 140, 0.16)" : "rgba(56, 178, 172, 0.16)", radius);
        }
      }
    }
  }

  function renderFrame() {
    if (!state) return;
  }

  function setMode(nextMode) {
    if (!state) return;
    updateData(state, nextMode);
  }

  return { updateData, renderFrame, setMode };
}
