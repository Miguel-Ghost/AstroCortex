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
