import { API_BASE } from "../config.js";
const cache = new Map();
export async function fetchJSON(path, { signal, method = "GET", body } = {}) {
  if (!path) return null;
  const r = await fetch(path, {
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let e;
    try {
      e = (await r.json()).error;
    } catch {}
    throw Object.assign(Error(e?.message || `Request failed (${r.status})`), {
      code: e?.code || "network",
    });
  }
  const data = await r.json();
  if (data.error)
    throw Object.assign(Error(data.error.message), { code: data.error.code });
  return data;
}
export function apiPath(path) {
  if (!API_BASE) throw Error("The team API is not configured.");
  return API_BASE + path;
}
export function resource(path, type = "image", expectedBytes) {
  if (!path) return Promise.reject(Error("Resource not available."));
  const u = new URL(path, location.origin);
  if (!["http:", "https:"].includes(u.protocol))
    return Promise.reject(Error("Unsupported resource URL"));
  const key = type + ":" + u.href;
  if (!cache.has(key)) {
    const p = (async () => {
      if (type === "image") {
        const r = await fetch(u, { signal: AbortSignal.timeout(15000) });
        if (!r.ok) throw Error(`Image unavailable (${r.status})`);
        return createImageBitmap(await r.blob());
      }
      const r = await fetch(u, { signal: AbortSignal.timeout(15000) });
      if (!r.ok) throw Error("Raw data unavailable.");
      const b = await r.arrayBuffer();
      if (expectedBytes && b.byteLength !== expectedBytes)
        throw Error(
          `Invalid BIN length: ${b.byteLength}; expected ${expectedBytes}.`,
        );
      const view = new DataView(b);
      return Float32Array.from({ length: b.byteLength / 4 }, (_, i) =>
        view.getFloat32(i * 4, true),
      );
    })();
    cache.set(key, p);
    p.catch(() => cache.delete(key));
  }
  return cache.get(key);
}
export async function preload(m, progress) {
  const urls = m.epochs.flatMap((e) =>
    e.frames.flatMap((f) => [f.image_url, f.flags_url].filter(Boolean)),
  );
  let done = 0;
  await Promise.all(
    urls.map(async (u) => {
      await resource(u);
      progress?.(++done, urls.length);
    }),
  );
}
