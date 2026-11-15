export function drawPlot(ctx, c, points, spec) {
  const rows = points.filter(
    (p) =>
      Number.isFinite(p.flux) &&
      Number.isFinite(spec ? p.wavelength_um : p.mjd),
  );
  ctx.fillStyle = "#aaa";
  ctx.font = "12px sans-serif";
  if (!rows.length) {
    ctx.fillText("Not available yet.", 20, 35);
    return;
  }
  const X = (p) => (spec ? p.wavelength_um : p.mjd),
    xs = rows.map(X),
    ys = rows.flatMap((p) => [
      p.flux - (p.flux_err || 0),
      p.flux + (p.flux_err || 0),
    ]),
    lo = Math.min(...xs),
    hi = Math.max(...xs),
    min = Math.min(...ys),
    max = Math.max(...ys),
    L = 45,
    R = c.width - 20,
    T = 25,
    B = c.height - 35,
    px = (x) => L + ((x - lo) / (hi - lo || 1)) * (R - L),
    py = (y) => B - ((y - min) / (max - min || 1)) * (B - T);
  for (let i = 0; i <= 4; i++) {
    const v = min + ((max - min) * i) / 4,
      y = py(v);
    ctx.strokeStyle = "#ffffff20";
    ctx.beginPath();
    ctx.moveTo(L, y);
    ctx.lineTo(R, y);
    ctx.stroke();
    ctx.fillText(v.toPrecision(2), 2, y);
    const xv = lo + ((hi - lo) * i) / 4;
    ctx.fillText(xv.toFixed(spec ? 2 : 1), px(xv) - 10, B + 16);
  }
  ctx.fillText(spec ? "λ (µm)" : "MJD", R - 40, c.height - 5);
  for (const p of rows) {
    const x = px(X(p)),
      y = py(p.flux),
      err = ((p.flux_err || 0) / (max - min || 1)) * (B - T);
    ctx.strokeStyle = "#a7bed4";
    ctx.beginPath();
    ctx.moveTo(x, y - err);
    ctx.lineTo(x, y + err);
    ctx.stroke();
    ctx.fillStyle = "#e8edf4";
    ctx.beginPath();
    ctx.arc(x, y, 2, 0, 2 * Math.PI);
    ctx.fill();
  }
}
