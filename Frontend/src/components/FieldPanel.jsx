import { bodySymbol } from "../lib/symbols";
import { useStore } from "../store";
import { FrameCanvas } from "./FrameCanvas";
import { availableEpochs, frameFor } from "../lib/manifest";
import { TARGETS } from "../targets";
export function FieldPanel() {
  const s = useStore(),
    m = s.field,
    e = m?.epochs[s.epochIndex],
    f = frameFor(m, s.epochIndex, s.detector),
    d = m?.detectors.find((d) => d.detector === s.detector),
    avail = availableEpochs(m, s.detector, s.grid),
    pairDisabled = !s.preloaded || avail.length < 2;
  const selected = s.sources?.sources?.find(
    (x) => x.source_id === s.selectedSourceId,
  );
  return (
    <section className="field">
      <nav className="tabs">
        {[
          ["flipbook", "Flipbook"],
          ["spectrum", "Spectrum"],
          ["lightcurve", "Light curve"],
          ["catalogs", "Catalogs"],
        ].map(([tab, label]) => (
          <button
            key={tab}
            data-tab={tab}
            className={s.tab === tab ? "active" : ""}
            onClick={() => s.patch({ tab, playing: false, mode: "flip" })}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="field-head">
        <strong id="fieldName">{m?.name || "Field"}</strong>
        <span id="fieldUnit">{s.tab === "flipbook" ? m?.flux_unit : s.tab === "spectrum" ? "mJy" : s.tab === "lightcurve" ? "Relative flux" : ""}</span>
        <span id="sequenceInfo">
          {s.tab === "flipbook" && e && `${s.epochIndex + 1} / ${m.epochs.length}`}
        </span>
      </div>
      {selected && (
        <div id="selectedCard">
          <img
            id="selectedPortrait"
            src={bodySymbol(selected.label).toDataURL()}
            alt="Source class symbol"
            title="Class symbol; not a resolved image of the source"
          />
          <div className="selection-text">
            <span id="selectedId">{selected.source_id}</span>
            <strong id="selectedName">
              {selected.display_name || selected.source_id}
            </strong>
            <span id="selectedClass">
              Candidate · {selected.label || "Needs review"}
            </span>
          </div>
          <button
            id="trackSource"
            className={s.tracking ? "active" : ""}
            onClick={() => s.patch({ tracking: !s.tracking })}
          >
            Track
          </button>
        </div>
      )}
      <div className="detectors" id="detectors">
        {[1, 2, 3, 4, 5, 6].map((det) => (
          <button
            key={det}
            className={s.detector === det && !s.grid ? "active" : ""}
            onClick={() => s.setDetector(det)}
          >
            D{det}
          </button>
        ))}
        <button
          id="gridBtn"
          className={s.grid ? "active" : ""}
          onClick={() =>
            s.patch({ grid: !s.grid, tab: "flipbook", playing: false })
          }
        >
          6 panels
        </button>
      </div>
      <FrameCanvas />
      {s.error && (
        <div className="empty">
          Try a test target:{" "}
          {TARGETS.map((t) => (
            <button
              key={t.target_id}
              onClick={() => s.selectTarget(t.target_id)}
            >
              {t.short}
            </button>
          ))}
        </div>
      )}
      {s.tab === "flipbook" && <>
      <div id="frameMeta">
        {s.progress ||
          (e && (
            <>
              {e.date_iso} · MJD {e.mjd_avg.toFixed(4)} · D{s.detector} ·{" "}
              {(
                f?.lambda_range_um || [d?.lambda_min_um, d?.lambda_max_um]
              ).join("–")}{" "}
              µm
              <br />
              {f
                ? `${f.n_exposures} exposures · coadd · flags ${(f.flagged_frac * 100).toFixed(1)}%`
                : `No D${s.detector} data for this date.`}
              {["diff", "sum"].includes(s.mode) &&
                ` · ${s.mode === "diff" ? "B − A" : "A + B"}`}
            </>
          ))}
      </div>
      <div className="playback">
        <button
          id="prev"
          aria-label="Previous epoch"
          disabled={!m || s.mode !== "flip"}
          onClick={() => s.step(-1)}
        >
          ‹
        </button>
        <button
          id="play"
          aria-label={s.playing ? "Pause flipbook" : "Play flipbook"}
          disabled={!s.preloaded}
          onClick={s.togglePlay}
        >
          {s.playing ? "Ⅱ" : "▶"}
        </button>
        <button
          id="next"
          aria-label="Next epoch"
          disabled={!m || s.mode !== "flip"}
          onClick={() => s.step(1)}
        >
          ›
        </button>
        <input
          id="epoch"
          type="range"
          aria-label="Epoch"
          min="0"
          max={Math.max(0, avail.length - 1)}
          value={Math.max(0, avail.indexOf(s.epochIndex))}
          disabled={!m || s.mode !== "flip"}
          onChange={(e) => s.setEpoch(avail[+e.target.value])}
        />
        <select
          id="fps"
          aria-label="Playback speed"
          value={s.fps}
          onChange={(e) => s.patch({ fps: +e.target.value })}
        >
          {[0.5, 1, 2, 4, 8].map((n) => (
            <option key={n} value={n}>
              {n} fps
            </option>
          ))}
        </select>
      </div>
      <div className="epoch-options">
        {[
          ["epochA", "pairA", "Epoch A"],
          ["epochB", "pairB", "Epoch B"],
        ].map(([id, key, label]) => (
          <select
            key={id}
            id={id}
            aria-label={label}
            value={s[key]}
            onChange={(e) =>
              s.patch({ [key]: +e.target.value, playing: false })
            }
          >
            {m?.epochs.map((e, i) => (
              <option key={e.epoch_id} value={i}>
                {i + 1} · {e.date_iso}
              </option>
            ))}
          </select>
        ))}
        {[
          ["blink", "Blink"],
          ["diff", "Difference"],
          ["sum", "Sum"],
        ].map(([mode, label]) => (
          <button
            key={mode}
            id={mode}
            disabled={pairDisabled}
            className={s.mode === mode ? "active" : ""}
            onClick={() => s.setMode(mode)}
          >
            {label}
          </button>
        ))}
        {["flags", "reticle", "track", "gaia", "wise"].map((key) => (
          <label key={key}>
            <input
              id={key}
              type="checkbox"
              disabled={
                ["gaia", "wise"].includes(key) && !s.catalogs?.[key]?.length
              }
              checked={s.layers[key]}
              onChange={() => s.setLayer(key)}
            />
            {key === "track" ? "Path" : key[0].toUpperCase() + key.slice(1)}
          </label>
        ))}
      </div>
      </>}
      <details className="data-provenance">
        <summary>
          {m?.epochs.reduce((n, e) => n + e.frames.length, 0) || 0} frames ·
          Processing details · {m?.fov_arcmin || 3.2}′ FOV
        </summary>
        <p>
          {m?.data_release} · {m?.pipeline_commit}
          <br />
          {m?.image_is}
          <br />
          {m?.nx} × {m?.ny} px · {m?.pixscale_arcsec}″/px · {m?.flux_unit}
        </p>
      </details>
    </section>
  );
}
