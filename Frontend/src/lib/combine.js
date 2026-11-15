import { resource } from "./api.js";
export function combineValues(a, b, mode) {
  if (a.length !== b.length) throw Error("Frame dimensions differ.");
  return Float32Array.from(a, (v, i) =>
    Number.isFinite(v) && Number.isFinite(b[i])
      ? mode === "diff"
        ? b[i] - v
        : b[i] + v
      : NaN,
  );
}
export function valuesToRGBA(values, mode, stretch) {
  const finite = Array.from(values)
      .filter(Number.isFinite)
      .map(Math.abs)
      .sort((a, b) => a - b),
    p99 = Math.max(finite[Math.floor(0.99 * (finite.length - 1))] || 0, 1e-6);
  const rgba = new Uint8ClampedArray(values.length * 4);
  values.forEach((v, i) => {
    let color = [58, 42, 74];
    if (Number.isFinite(v)) {
      if (mode === "diff") {
        const t = Math.max(-1, Math.min(1, v / p99));
        const g = Math.round(127.5 + 127.5 * t);
        color = [g, g, g];
      } else {
        const lo = 2 * (stretch?.vmin || 0),
          hi = 2 * (stretch?.vmax || 1);
        const g = Math.round(
          255 * Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1))),
        );
        color = [g, g, g];
      }
    }
    rgba.set([...color, 255], i * 4);
  });
  return rgba;
}
export async function combineFrames(a, b, m, det, mode) {
  if (!a?.data_url || !b?.data_url)
    throw Error("Difference needs raw data (data_url) for both dates.");
  const [av, bv] = await Promise.all([
    resource(a.data_url, "float", m.nx * m.ny * 4),
    resource(b.data_url, "float", m.nx * m.ny * 4),
  ]);
  const values = combineValues(av, bv, mode);
  const c = document.createElement("canvas");
  c.width = m.nx;
  c.height = m.ny;
  c.getContext("2d").putImageData(
    new ImageData(
      valuesToRGBA(
        values,
        mode,
        m.detectors.find((d) => d.detector === det)?.stretch,
      ),
      m.nx,
      m.ny,
    ),
    0,
    0,
  );
  return c;
}
