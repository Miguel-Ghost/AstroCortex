import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { useElementSize } from "../hooks/useElementSize";
import { drawFrame } from "../lib/draw";
import { readSeries } from "../lib/series";
import { drawPlot } from "../lib/plot";
export function FrameCanvas() {
  const s = useStore(),
    [box, size] = useElementSize(),
    ref = useRef(),
    [series, setSeries] = useState(null);
  useEffect(() => {
    setSeries(null);
    const path =
      s.tab === "spectrum"
        ? s.field?.spectrum_url
        : s.tab === "lightcurve"
          ? s.field?.lightcurve_url
          : null;
    if (!path) return;
    const a = new AbortController();
    fetch(path, { signal: a.signal })
      .then((r) => {
        if (!r.ok) throw Error("Series unavailable");
        return r.text();
      })
      .then(readSeries)
      .then(setSeries)
      .catch(() => {});
    return () => a.abort();
  }, [s.tab, s.field]);
  useEffect(() => {
    const c = ref.current;
    if (!c || !size.width) return;
    let cancelled = false;
    c.width = Math.floor(size.width * (devicePixelRatio || 1));
    c.height = Math.floor(size.height * (devicePixelRatio || 1));
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, c.width, c.height);
    c._hits = [];
    if (s.field && ["spectrum", "lightcurve"].includes(s.tab) && series)
      drawPlot(ctx, c, series, s.tab === "spectrum");
    if (s.field && s.tab === "flipbook")
      drawFrame(ctx, c, s, () => cancelled).then((h) => {
        if (!cancelled) c._hits = h;
      });
    return () => {
      cancelled = true;
    };
  }, [
    s.field,
    s.detector,
    s.epochIndex,
    s.mode,
    s.grid,
    s.pairA,
    s.pairB,
    s.layers,
    s.selectedSourceId,
    s.sources,
    s.tab,
    series,
    size.width,
    size.height,
  ]);
  return (
    <div className="frame-area" ref={box}>
      <canvas
        id="frame"
        ref={ref}
        onClick={(e) => {
          const c = ref.current,
            r = c.getBoundingClientRect(),
            x = ((e.clientX - r.left) * c.width) / r.width,
            y = ((e.clientY - r.top) * c.height) / r.height;
          const h = c._hits?.find(
            (h) => Math.hypot(x - h.x, y - h.y) < h.radius,
          );
          if (h) s.selectSource(h.id);
        }}
      />
      {s.tab !== "flipbook" &&
        !(series && ["spectrum", "lightcurve"].includes(s.tab)) && (
          <div id="catalogContent">
            <div className="empty">
              {s.tab === "catalogs" ? (
                s.catalogs ? (
                  <pre>{JSON.stringify(s.catalogs, null, 2)}</pre>
                ) : (
                  "Not available yet."
                )
              ) : series ? (
                <pre>{JSON.stringify(series, null, 2)}</pre>
              ) : (
                "Not available yet."
              )}
            </div>
          </div>
        )}
      {!s.field && (
        <div id="frameEmpty" className="empty">
          {s.error || s.progress || "Choose a target"}
        </div>
      )}
    </div>
  );
}
