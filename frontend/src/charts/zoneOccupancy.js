export function createZoneOccupancy(container, insightElement, onSeek) {
  const width = 640;
  const height = 270;
  const margin = { top: 18, right: 54, bottom: 30, left: 116 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  const x = d3.scaleLinear().range([0, innerW]);
  const y = d3.scaleBand().range([0, innerH]).paddingInner(0.2);
  const roleBand = d3.scaleBand().domain(["near", "far"]).padding(0.16);
  const roles = [
    { key: "near", label: "Near", color: "#d53f8c" },
    { key: "far", label: "Far", color: "#38b2ac" },
  ];
  const zones = [
    { id: "far-back", label: "Far backcourt" },
    { id: "far-mid", label: "Far midcourt" },
    { id: "far-front", label: "Far frontcourt" },
    { id: "near-front", label: "Near frontcourt" },
    { id: "near-mid", label: "Near midcourt" },
    { id: "near-back", label: "Near backcourt" },
  ];

  let state = null;
  let segments = [];

  function validRows(data, role) {
    return data.players.filter((row) => row.role === role && row.court_y_m !== null && row.court_x_m !== null);
  }

  function zoneIndex(value, courtLength) {
    return Math.max(0, Math.min(zones.length - 1, Math.floor((value / courtLength) * zones.length)));
  }

  function buildSegments(data) {
    const courtLength = data.analysis.court_size_m?.length || 13.4;
    return roles.flatMap((role) => {
      const rows = validRows(data, role.key);
      return zones.map((zone, index) => {
        const matching = rows.filter((row) => zoneIndex(row.court_y_m, courtLength) === index);
        const representative = matching.length ? matching[Math.floor(matching.length / 2)].frame : null;
        return {
          role: role.key,
          roleLabel: role.label,
          color: role.color,
          zoneId: zone.id,
          zoneLabel: zone.label,
          zoneIndex: index,
          count: matching.length,
          ratio: rows.length ? matching.length / rows.length : 0,
          frame: representative,
        };
      });
    });
  }

  function updateInsight() {
    if (!insightElement) return;
    const dominant = roles.map((role) => {
      const roleSegments = segments.filter((segment) => segment.role === role.key);
      const top = d3.greatest(roleSegments, (segment) => segment.ratio);
      return top ? `${role.label}: ${top.zoneLabel} ${d3.format(".1%")(top.ratio)}` : `${role.label}: unavailable`;
    });
    insightElement.textContent = `${dominant.join(" | ")}. Click a bar to seek a representative frame.`;
  }

  function updateData(data) {
    state = data;
    segments = buildSegments(data);
    g.selectAll("*").remove();

    y.domain(zones.map((zone) => zone.id));
    roleBand.range([0, y.bandwidth()]);
    const maximum = d3.max(segments, (segment) => segment.ratio) || 0;
    x.domain([0, Math.max(0.2, Math.ceil(maximum * 10) / 10)]).nice();

    g.selectAll(".zone-row-bg")
      .data(zones)
      .join("rect")
      .attr("class", "zone-row-bg")
      .attr("x", 0)
      .attr("y", (zone) => y(zone.id))
      .attr("width", innerW)
      .attr("height", y.bandwidth());

    g.append("g")
      .attr("class", "grid")
      .call(d3.axisBottom(x).ticks(4).tickSize(innerH).tickFormat(""))
      .selectAll("line")
      .attr("class", "grid-line");

    g.append("g")
      .attr("class", "axis zone-axis")
      .call(d3.axisLeft(y).tickFormat((id) => zones.find((zone) => zone.id === id)?.label || id).tickSize(0))
      .select(".domain")
      .remove();

    g.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(4).tickFormat(d3.format(".0%")));

    const bars = g.selectAll(".zone-bar")
      .data(segments)
      .join("rect")
      .attr("class", (segment) => `zone-bar ${segment.role}`)
      .attr("x", 0)
      .attr("y", (segment) => y(segment.zoneId) + roleBand(segment.role))
      .attr("height", roleBand.bandwidth())
      .attr("width", (segment) => x(segment.ratio))
      .attr("fill", (segment) => segment.color)
      .attr("opacity", 0.84)
      .style("cursor", (segment) => segment.frame === null ? "default" : "pointer")
      .on("click", (event, segment) => {
        if (segment.frame !== null) onSeek(segment.frame);
      });

    bars.append("title")
      .text((segment) => `${segment.roleLabel} | ${segment.zoneLabel}: ${d3.format(".1%")(segment.ratio)} (${segment.count} frames)`);

    g.selectAll(".zone-value")
      .data(segments.filter((segment) => segment.ratio >= 0.01))
      .join("text")
      .attr("class", "zone-value")
      .attr("x", (segment) => x(segment.ratio) + 5)
      .attr("y", (segment) => y(segment.zoneId) + roleBand(segment.role) + roleBand.bandwidth() / 2 + 3.5)
      .text((segment) => d3.format(".0%")(segment.ratio));

    g.append("text")
      .attr("class", "chart-caption zone-caption")
      .attr("x", innerW)
      .attr("y", -6)
      .attr("text-anchor", "end")
      .text("Tracked time share");

    updateInsight();
    renderFrame(0);
  }

  function renderFrame(frame) {
    if (!state) return;
    const courtLength = state.analysis.court_size_m?.length || 13.4;
    const active = new Set();
    for (const role of roles) {
      const row = validRows(state, role.key).find((item) => item.frame === frame);
      if (row) active.add(`${role.key}:${zoneIndex(row.court_y_m, courtLength)}`);
    }
    g.selectAll(".zone-bar")
      .classed("active-frame", (segment) => active.has(`${segment.role}:${segment.zoneIndex}`));
  }

  return { updateData, renderFrame };
}
