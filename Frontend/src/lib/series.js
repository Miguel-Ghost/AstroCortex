export function readSeries(text) {
  const trimmed = text.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    const v = JSON.parse(trimmed);
    return Array.isArray(v) ? v : v.data || v.points || [];
  }
  const lines = trimmed.split(/\r?\n/),
    keys = lines
      .shift()
      .split(",")
      .map((s) => s.trim());
  return lines
    .filter(Boolean)
    .map((line) =>
      Object.fromEntries(
        line
          .split(",")
          .map((v, i) => [keys[i], v.trim() === "" ? null : Number(v)]),
      ),
    );
}

// Keep measurement metadata alongside the rows; readSeries remains compatible.
export function readSeriesDocument(text) {
  const points = readSeries(text);
  if (!Array.isArray(points)) throw Error("Invalid measurement series");
  const trimmed = text.trim();
  const value = trimmed.startsWith("{") ? JSON.parse(trimmed) : {};
  return { ...value, data: points };
}

export function seriesPoints(series, spec, detector = null) {
  const points = !spec && detector !== null
    ? series.by_detector?.[String(detector)] || []
    : series.data;
  return points.filter((p) => Number.isFinite(p.flux) &&
    Number.isFinite(spec ? p.wavelength_um : p.mjd));
}

export function isSaturatedSeries(series) {
  // R Dra has only four usable exposures; these cannot support a time series.
  return series?.target_id === "rdra";
}
