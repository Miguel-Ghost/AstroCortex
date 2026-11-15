import { skyToPixel } from "./coords";
import { frameFor, positionFor } from "./manifest";
import { resource } from "./api";
import { combineFrames } from "./combine";
export async function drawFrame(ctx, c, s, cancelled) {
  const m = s.field,
    cols = s.grid ? 3 : 1,
    rows = s.grid ? 2 : 1,
    hits = [],
    dpr = devicePixelRatio || 1;
  ctx.fillStyle = "#0b0b0e";
  ctx.fillRect(0, 0, c.width, c.height);
  await Promise.all(
    Array.from({ length: s.grid ? 6 : 1 }, async (_, k) => {
      const det = s.grid ? k + 1 : s.detector,
        cw = c.width / cols,
        ch = c.height / rows,
        ox = (k % cols) * cw,
        oy = Math.floor(k / cols) * ch,
        scale = Math.max(
          1,
          Math.floor(Math.min((cw - 20 * dpr) / m.nx, (ch - 32 * dpr) / m.ny)),
        ),
        w = m.nx * scale,
        h = m.ny * scale,
        left = ox + (cw - w) / 2,
        top = oy + (ch - h) / 2;
      const f = frameFor(m, s.epochIndex, det);
      let image, flags;
      try {
        if (!f) throw Error(`No D${det} data for this date.`);
        image = ["diff", "sum"].includes(s.mode)
          ? await combineFrames(
              frameFor(m, s.pairA, det),
              frameFor(m, s.pairB, det),
              m,
              det,
              s.mode,
            )
          : await resource(f.image_url);
        if (s.layers.flags && f.flags_url) flags = await resource(f.flags_url);
        if (cancelled()) return;
        ctx.fillStyle = "#3a2a4a";
        ctx.fillRect(left, top, w, h);
        ctx.drawImage(image, left, top, w, h);
        if (flags) {
          ctx.globalAlpha = 0.55;
          ctx.drawImage(flags, left, top, w, h);
          ctx.globalAlpha = 1;
        }
        const source = s.sources?.sources?.find(
          (x) => x.source_id === s.selectedSourceId,
        );
        const point = (p) => [
          left + (p.x + 0.5) * scale,
          top + (p.y + 0.5) * scale,
        ];
        const positions = m.epochs
          .map((e) => positionFor(source, e))
          .filter((p) => Number.isFinite(p?.x) && Number.isFinite(p?.y));
        if (s.layers.track && positions.length) {
          ctx.save();
          ctx.strokeStyle = "#00e5ff99";
          ctx.lineWidth = dpr;
          ctx.setLineDash([3 * dpr, 3 * dpr]);
          ctx.beginPath();
          positions.forEach((p, i) =>
            i ? ctx.lineTo(...point(p)) : ctx.moveTo(...point(p)),
          );
          ctx.stroke();
          ctx.restore();
        }
        const pos = positionFor(source, m.epochs[s.epochIndex]);
        if (
          s.layers.reticle &&
          Number.isFinite(pos?.x) &&
          Number.isFinite(pos?.y)
        ) {
          const [px, py] = point(pos);
          for (const [color, width] of [
            ["#000", 3],
            ["#00e5ff", 1],
          ]) {
            ctx.strokeStyle = color;
            ctx.lineWidth = width * dpr;
            ctx.beginPath();
            for (const [dx, dy] of [
              [1, 0],
              [-1, 0],
              [0, 1],
              [0, -1],
            ]) {
              ctx.moveTo(px + dx * 6 * dpr, py + dy * 6 * dpr);
              ctx.lineTo(px + dx * 15 * dpr, py + dy * 15 * dpr);
            }
            ctx.stroke();
          }
        }
        if (s.layers.sources)
          for (const src of s.sources?.sources || []) {
            const p = src.positions?.[m.epochs[s.epochIndex].epoch_id];
            if (!Number.isFinite(p?.x) || !Number.isFinite(p?.y)) continue;
            const [x, y] = point(p);
            ctx.strokeStyle =
              src.source_id === s.selectedSourceId ? "#00e5ff" : "#cdd7e5";
            ctx.lineWidth = dpr;
            ctx.beginPath();
            ctx.arc(x, y, 6 * dpr, 0, Math.PI * 2);
            ctx.stroke();
            hits.push({ x, y, radius: 10 * dpr, id: src.source_id });
          }
        for (const kind of ["gaia", "wise"]) {
          if (!s.layers[kind]) continue;
          for (const item of s.catalogs?.[kind] || []) {
            if (!Number.isFinite(item.ra) || !Number.isFinite(item.dec))
              continue;
            const p = skyToPixel(item.ra, item.dec, m),
              [x, y] = point(p);
            if (p.x < 0 || p.x >= m.nx || p.y < 0 || p.y >= m.ny) continue;
            ctx.strokeStyle = kind === "gaia" ? "#f0cb76" : "#cd9ae8";
            ctx.lineWidth = dpr;
            ctx.strokeRect(x - 4 * dpr, y - 4 * dpr, 8 * dpr, 8 * dpr);
          }
        }
        ctx.fillStyle = "#ddd";
        ctx.font = `${10 * dpr}px sans-serif`;
        if (s.grid) ctx.fillText("D" + det, ox + 8 * dpr, oy + 13 * dpr);
        else {
          ctx.fillText("N ↑   E ←", left + 4 * dpr, top + 13 * dpr);
          const length = (30 / m.pixscale_arcsec) * scale;
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = dpr;
          ctx.beginPath();
          ctx.moveTo(left + 8 * dpr, top + h - 12 * dpr);
          ctx.lineTo(left + 8 * dpr + length, top + h - 12 * dpr);
          ctx.stroke();
          ctx.fillText("30″", left + 8 * dpr, top + h - 18 * dpr);
        }
      } catch (e) {
        if (cancelled()) return;
        ctx.fillStyle = "#b6b6c3";
        ctx.font = `${10 * dpr}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(e.message, ox + cw / 2, oy + ch / 2, cw - 12 * dpr);
        ctx.textAlign = "left";
      }
    }),
  );
  return hits;
}
