import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { useElementSize } from "../hooks/useElementSize";
import { drawFrame } from "../lib/draw";
import { readSeriesDocument, seriesPoints, isSaturatedSeries } from "../lib/series";
import { drawPlot, epochColors } from "../lib/plot";
import { FULL_VIEW, zoomView, panView, plotAnchor } from "../lib/plotView";
export function FrameCanvas() {
  const s = useStore(),
    [box, size] = useElementSize(),
    ref = useRef(),
    [loaded, setLoaded] = useState(null),
    [loadError, setLoadError] = useState(""),
    [retry, setRetry] = useState(0),
    [followDetector, setFollowDetector] = useState(false),
    [view, setView] = useState(FULL_VIEW),
    drag = useRef(null);
  const resetView = () => { drag.current = null; setView(FULL_VIEW); };
  const path = s.tab === "spectrum" ? s.field?.spectrum_url
    : s.tab === "lightcurve" ? s.field?.lightcurve_url : null;
  const series = loaded?.path === path && loaded?.field === s.field ? loaded.value : null;
  const scientific = ["spectrum", "lightcurve"].includes(s.tab);
  const points = series ? seriesPoints(series, s.tab === "spectrum",
    followDetector && s.tab === "lightcurve" ? s.detector : null) : [];
  const saturated = isSaturatedSeries(series);
  useEffect(resetView, [path, s.field, s.detector, followDetector]);
  useEffect(() => {
    const c = ref.current;
    if (!c || !scientific || !series || saturated) return;
    const wheel = event => {
      if (!c._plot) return;
      event.preventDefault();
      const anchor = plotAnchor(event.clientX, event.clientY, c.getBoundingClientRect(), c._plot);
      setView(v => zoomView(v, Math.exp(Math.max(-200, Math.min(200, event.deltaY)) * 0.004), anchor));
    };
    c.addEventListener("wheel", wheel, { passive: false });
    return () => c.removeEventListener("wheel", wheel);
  }, [scientific, series, saturated]);
  useEffect(() => {
    setLoadError("");
    setLoaded(null);
    if (!path) return;
    const a = new AbortController();
    fetch(path, { signal: a.signal })
      .then((r) => {
        if (!r.ok) throw Error("Series unavailable");
        return r.text();
      })
      .then(readSeriesDocument)
      .then(value => { if (!a.signal.aborted) setLoaded({ path, field: s.field, value }); })
      .catch(error => { if (!a.signal.aborted) setLoadError(error.message); });
    return () => a.abort();
  }, [path, s.field, retry]);
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
    c._plot = null;
    if (s.field && scientific && series && !saturated)
      c._plot = drawPlot(ctx, c, points, s.tab === "spectrum", {
        view, fluxUnit: series.flux_unit, pixelRatio: devicePixelRatio || 1,
      });
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
    followDetector,
    view,
    size.width,
    size.height,
  ]);
  return (
    <>
    {scientific && series && !saturated && (
      <div className="series-toolbar">
        {s.tab === "lightcurve" ? <>
          <span>1.0 = mean brightness</span>
          {series.by_detector && <label><input type="checkbox" checked={followDetector}
            onChange={e => setFollowDetector(e.target.checked)} /> Follow D{s.detector}</label>}
        </> : <>
          {Object.entries(epochColors(points)).map(([id, color]) =>
            <span key={id} style={{ color }}>● {id}</span>)}
          <span>Hollow points: low SNR</span>
        </>}
      </div>
    )}
    <div className="frame-area" ref={box}>
      <canvas
        id="frame"
        ref={ref}
        className={scientific ? "interactive-plot" : ""}
        tabIndex={scientific ? 0 : undefined}
        role={scientific ? "img" : undefined}
        aria-label={scientific ? `${s.tab === "spectrum" ? "Spectrum" : "Light curve"} for ${s.field?.name || "field"}. Use plus or minus to zoom, arrow keys to pan, and 0 to reset.` : undefined}
        onDoubleClick={() => { if (scientific) resetView(); }}
        onKeyDown={event => {
          if (!scientific || !series || saturated) return;
          const moves = { ArrowLeft: [-0.1, 0], ArrowRight: [0.1, 0], ArrowUp: [0, 0.1], ArrowDown: [0, -0.1] };
          if (["+", "=", "-", "0", "Home", ...Object.keys(moves)].includes(event.key)) {
            event.preventDefault(); event.stopPropagation();
            if (moves[event.key]) setView(v => panView(v, ...moves[event.key]));
            else if (["0", "Home"].includes(event.key)) resetView();
            else setView(v => zoomView(v, event.key === "-" ? 1 / 0.7 : 0.7));
          }
        }}
        onPointerDown={event => {
          if (!scientific || !ref.current?._plot || event.button !== 0 || !event.isPrimary) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, y: event.clientY, view, id: event.pointerId };
        }}
        onPointerMove={event => {
          const start = drag.current, plot = ref.current?._plot;
          if (!start || start.id !== event.pointerId || !plot) return;
          setView(panView(start.view,
            -(event.clientX - start.x) / (plot.R - plot.L),
            (event.clientY - start.y) / (plot.B - plot.T)));
        }}
        onPointerUp={() => { drag.current = null; }}
        onPointerCancel={() => { drag.current = null; }}
        onLostPointerCapture={() => { drag.current = null; }}
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
      {scientific && s.field && (!series || saturated) && (
        <div className="series-empty" role="status">
          {saturated ? <><strong>Saturated in SPHEREx</strong>
            <span>Only four usable exposures; insufficient coverage for this chart.</span></>
            : loadError ? <><span>Could not load measurements.</span>
              <button onClick={() => setRetry(n => n + 1)}>Retry</button></>
            : path ? "Loading measurements…" : "No measurements available for this field."}
        </div>
      )}
      {s.tab === "catalogs" && (
        <div id="catalogContent"><div className="empty">
          {s.catalogs ? <pre>{JSON.stringify(s.catalogs, null, 2)}</pre> : "Not available yet."}
        </div></div>
      )}
      {!s.field && (
        <div id="frameEmpty" className="empty">
          {s.error || s.progress || "Choose a target"}
        </div>
      )}
    </div>
    {scientific && series && <div className="series-details">
      {series.warning && <p className="series-warning" role="note">{series.warning}</p>}
      <details><summary>Measurement details · {points.length} points{followDetector && s.tab === "lightcurve" ? ` · D${s.detector}` : ""}</summary>
        <p>{series.name} · {series.data_release}<br />Flux unit: {series.flux_unit}</p>
        <p>{series.method}</p>
        {path && <a href={path} target="_blank" rel="noreferrer">Open measurement JSON</a>}
      </details>
    </div>}
    </>
  );
}
