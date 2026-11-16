export const EPOCH_COLORS = ["#a8cfff", "#e1b5ff", "#88dbc4", "#f3c58b", "#f3a8b8", "#cadb8e"];
export function epochColors(rows) {
  return Object.fromEntries([...new Set(rows.map(p => p.epoch_id).filter(Boolean))]
    .sort().map((id, i) => [id, EPOCH_COLORS[i % EPOCH_COLORS.length]]));
}

export function drawPlot(ctx, c, rows, spec, options = {}) {
  const scale = options.pixelRatio || 1;
  ctx.save();
  ctx.scale(scale, scale);
  const width = c.width / scale, height = c.height / scale;
  ctx.fillStyle = "#aaaaba";
  ctx.font = "11px sans-serif";
  if (!rows.length) {
    ctx.fillText("No measurements for this detector.", 16, 30);
    ctx.restore();
    return;
  }
  const X = p => spec ? p.wavelength_um : p.mjd;
  const error = p => Number.isFinite(p.flux_err) ? Math.max(0, p.flux_err) : 0;
  const xs = rows.map(X), ys = rows.flatMap(p => [p.flux - error(p), p.flux + error(p)]);
  if (!spec) ys.push(1);
  let lo = Math.min(...xs), hi = Math.max(...xs), min = Math.min(...ys), max = Math.max(...ys);
  const dx = (hi - lo || Math.max(Math.abs(lo) * 0.00001, 0.01)) * 0.05;
  const dy = (max - min || Math.max(Math.abs(min) * 0.1, 0.1)) * 0.12;
  lo -= dx; hi += dx; min -= dy; max += dy;
  if (options.view) {
    const v = options.view, xSpan = hi - lo, ySpan = max - min;
    hi = lo + xSpan * v.x1; lo += xSpan * v.x0;
    max = min + ySpan * v.y1; min += ySpan * v.y0;
  }
  const L = 64, R = Math.max(L + 1, width - 24), T = 30, B = Math.max(T + 1, height - 42);
  const px = x => L + (x - lo) / (hi - lo) * (R - L);
  const py = y => B - (y - min) / (max - min) * (B - T);
  ctx.fillText(spec ? `Flux (${options.fluxUnit || "mJy"})` : "Relative flux", L, 16);
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4, y = py(v);
    ctx.strokeStyle = "#ffffff16";
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(R, y); ctx.stroke();
    ctx.textAlign = "right"; ctx.fillStyle = "#aaaaba";
    ctx.fillText(v.toPrecision(3), L - 8, y + 4);
    // A narrow panel needs fewer x ticks so MJD labels remain readable.
    if (width >= 480 || i % 2 === 0) {
      const xv = lo + (hi - lo) * i / 4;
      ctx.textAlign = "center";
      ctx.fillText(xv.toFixed(spec ? 2 : 1), px(xv), B + 17);
    }
  }
  ctx.textAlign = "center";
  ctx.fillText(spec ? "Wavelength (µm)" : "MJD", (L + R) / 2, height - 6);
  ctx.save();
  ctx.beginPath(); ctx.rect(L, T, R - L, B - T); ctx.clip();
  if (!spec) {
    ctx.strokeStyle = "#ffffff55"; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(L, py(1)); ctx.lineTo(R, py(1)); ctx.stroke();
    ctx.setLineDash([]);
  }
  const colors = epochColors(rows);
  for (const p of rows) {
    const x = px(X(p)), y = py(p.flux), err = error(p) / (max - min) * (B - T);
    ctx.strokeStyle = ctx.fillStyle = spec ? colors[p.epoch_id] || "#e8edf4" : "#a8cfff";
    ctx.beginPath(); ctx.moveTo(x, y - err); ctx.lineTo(x, y + err);
    ctx.moveTo(x - 2, y - err); ctx.lineTo(x + 2, y - err);
    ctx.moveTo(x - 2, y + err); ctx.lineTo(x + 2, y + err); ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, spec ? 2 : 3.5, 0, 2 * Math.PI);
    // Hollow markers retain low-SNR measurements without implying detections.
    if (p.detected === false) ctx.stroke(); else ctx.fill();
  }
  ctx.restore(); ctx.restore();
  return { L, R, T, B };
}
