const DATA_ROOT = "public/data";

const numberFields = new Set([
  "frame",
  "time_s",
  "visibility",
  "x_px",
  "y_px",
  "court_x_m",
  "court_y_m",
  "speed_mps",
  "is_missing",
  "is_interpolated",
  "is_spatial_valid",
  "speed_valid",
  "bbox_x1",
  "bbox_y1",
  "bbox_x2",
  "bbox_y2",
  "confidence",
  "cumulative_distance_m",
  "rally_distance_m",
  "max_speed_so_far_mps",
]);

function coerceRow(row) {
  const out = {};
  for (const [key, value] of Object.entries(row)) {
    if (numberFields.has(key)) {
      out[key] = value === "" ? null : Number(value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

export async function loadManifest() {
  const manifest = await d3.json(`${DATA_ROOT}/manifest.json`);
  if (!manifest || !Array.isArray(manifest.videos)) {
    throw new Error("Invalid frontend data manifest.");
  }
  return manifest;
}

export async function loadVideoDataset(videoEntry) {
  const files = videoEntry.files;
  const base = `${DATA_ROOT}/`;
  const [analysis, quality, ball, players, motion] = await Promise.all([
    d3.json(`${base}${files.analysis}`),
    d3.json(`${base}${files.quality}`),
    d3.csv(`${base}${files.ball}`, coerceRow),
    d3.csv(`${base}${files.players}`, coerceRow),
    d3.csv(`${base}${files.motion}`, coerceRow),
  ]);
  return {
    entry: videoEntry,
    analysis,
    quality,
    ball,
    players,
    motion,
    urls: {
      original: files.original_video ? `${base}${files.original_video}` : null,
      overlay: files.overlay_video ? `${base}${files.overlay_video}` : null,
      final: files.final_video ? `${base}${files.final_video}` : null,
    },
  };
}
