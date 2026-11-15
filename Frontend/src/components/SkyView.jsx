import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { MeshCanvas } from "./MeshCanvas";
import { positionFor } from "../lib/manifest";
import {
  loadSky,
  initialSurvey,
  selectSurvey,
  ALLWISE_URL,
  TWOMASS_URL,
} from "../lib/sky";
export function SkyView({ ready }) {
  const s = useStore(),
    instance = useRef(),
    api = useRef(),
    host = useRef(),
    [notice, setNotice] = useState("Loading sky…"),
    [objects, setObjects] = useState(true),
    [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!ready) return;
    let gone = false;
    loadSky()
      .then(({ A, renderer }) => {
        if (gone || instance.current) return;
        api.current = A;
        const v = A.aladin(host.current, {
          survey: initialSurvey(A, renderer),
          projection: "SIN",
          cooFrame: "ICRSd",
          fov: 360,
          allowFullZoomout: true,
          showReticle: false,
          reticleColor:"#bdd5e8",
          showCooGrid: false,
          showZoomControl: false,
          showLayersControl: false,
          showGotoControl: false,
          showFullscreenControl: false,
          showProjectionControl: false,
          showFrame: false,
        });
        if (!v.setFov) v.setFov = v.setFoV.bind(v);
        instance.current = v;
        host.current.dataset.renderer = renderer;
        v.on("objectClicked", (o) => {
          if (o?.data?.source_id)
            useStore.getState().selectSource(o.data.source_id);
          else if (o?.data?.target_id)
            useStore.getState().selectTarget(o.data.target_id);
        });
        if (!document.querySelector("#aladin canvas")) {
          setNotice(
            "Sky images are not available in this session. The local flipbook is ready.",
          );
        } else {
          setNotice("");
        }
        setLoaded(true);
      })
      .catch((e) => {
        if (!gone) {
          setNotice(e?.message || String(e));
        }
      });
    return () => {
      gone = true;
      if (instance.current) {
        instance.current.destroy?.();
        host.current?.replaceChildren();
        instance.current = null;
      }
    };
  }, [ready]);
  useEffect(() => {
    const a = instance.current;
    if (a && s.field) a.gotoRaDec(s.field.center.ra, s.field.center.dec);
  }, [s.field, loaded]);
  useEffect(() => {
    const a = instance.current;
    if (!a || !s.field || !s.tracking) return;
    const source = s.sources?.sources?.find(
        (x) => x.source_id === s.selectedSourceId,
      ),
      p = positionFor(source, s.field.epochs[s.epochIndex]);
    if (p) a.gotoRaDec(p.ra, p.dec);
  }, [s.field, s.tracking, s.epochIndex, s.selectedSourceId, loaded]);
  useEffect(() => {
    const a = instance.current,
      A = api.current;
    if (!a || !s.field || !loaded) return;
    const layer = A.catalog({
      name: "Sources",
      color: "#b9d4ed",
      sourceSize: 9,
    });
    a.addCatalog(layer);
    layer.addSources(
      (s.sources?.sources || [])
        .filter((p) => Number.isFinite(p.ra) && Number.isFinite(p.dec))
        .map((p) =>
          A.source(p.ra, p.dec, {
            source_id: p.source_id,
            name: p.display_name || p.source_id,
          }),
        ),
    );
    return () => {
      layer.removeAll();
      a.removeCatalog?.(layer);
    };
  }, [s.field, s.sources, loaded]);
  useEffect(() => {
    const a = instance.current,
      A = api.current;
    if (!a || !A || !loaded) return;
    const targets = Object.entries(s.targetStats).filter(([, t]) => t);
    const layer = A.catalog({
      name: "Observation targets",
      color: "#8fd8f0",
      sourceSize: 10,
      shape: "circle",
      displayLabel: true,
      labelColumn: "name",
    });
    a.addCatalog(layer);
    layer.addSources(
      targets.map(([id, t]) =>
        A.source(t.center.ra, t.center.dec, { target_id: id, name: t.name }),
      ),
    );
    return () => {
      layer.removeAll();
      a.removeCatalog?.(layer);
    };
  }, [loaded, s.targetStats]);
  return (
    <section
      className="sky"
      id="sky"
    >
      <div id="aladin" ref={host} style={{ width: "100%", height: "100%" }} />
      <MeshCanvas />
      <div id="skyNotice">{notice}</div>
      <div id="objectBrowser">
        <button
          id="objectsBtn"
          aria-expanded={objects}
          onClick={() => setObjects(!objects)}
        >
          Objects ·{" "}
          {Object.values(s.targetStats).filter(Boolean).length +
            (s.sources?.sources?.length || 0)}
        </button>
        {objects && (
          <div id="objectList">
            {Object.entries(s.targetStats)
              .filter(([, t]) => t)
              .map(([id, t]) => (
                <button
                  key={id}
                  className={id === s.targetId ? "active" : ""}
                  onClick={() => s.selectTarget(id)}
                >
                  <span>
                    <strong>{t.name}</strong>
                    <small>Observation target · {t.frames} frames</small>
                  </span>
                </button>
              ))}
            {s.sources?.sources?.length ? (
              s.sources.sources.map((src) => (
                <button
                  key={src.source_id}
                  onClick={() => s.selectSource(src.source_id)}
                >
                  {src.display_name || src.source_id} ·{" "}
                  {src.label || "Needs review"}
                </button>
              ))
            ) : (
              <div className="empty">No source catalog available yet.</div>
            )}
          </div>
        )}
      </div>
      <div className="sky-tools">
        <button
          aria-label="Sky overview"
          title="Sky overview"
          onClick={() => instance.current?.setFov(360)}
        >
          ◯
        </button>
        <button
          aria-label="Zoom in"
          onClick={() => {
            const a = instance.current;
            if (a) a.setFov(a.getFov()[0] / 1.5);
          }}
        >
          +
        </button>
        <button
          aria-label="Zoom out"
          onClick={() => {
            const a = instance.current;
            if (a) a.setFov(a.getFov()[0] * 1.5);
          }}
        >
          −
        </button>
        <button
          aria-label="Center field"
          onClick={() => {
            const a = instance.current;
            if (a && s.field) {
              a.gotoRaDec(s.field.center.ra, s.field.center.dec);
              a.setFov((s.field.fov_arcmin / 60) * 2);
            }
          }}
        >
          ⊙
        </button>
        <button
          id="expandField"
          aria-label="Expand field"
          onClick={() => s.patch({ expanded: !s.expanded })}
        >
          ▣
        </button>
        <select
          id="background"
          aria-label="Sky background"
          onChange={async (e) => {
            const a = instance.current,
              A = api.current;
            if (!a) return;
            try {
              a.setImageSurvey(
                await selectSurvey(
                  A,
                  host.current.dataset.renderer,
                  e.target.value,
                  e.target.selectedOptions[0].textContent,
                ),
              );
            } catch (error) {
              s.notify(error.message);
              e.target.value = ALLWISE_URL;
            }
          }}
        >
          <option value={ALLWISE_URL}>AllWISE</option>
          <option value={TWOMASS_URL}>2MASS</option>
          <option value="CDS/P/SPHEREx/QR2/D1">SPHEREx D1</option>
        </select>
      </div>
    </section>
  );
}
