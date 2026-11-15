# Migración del HTML de AstroCortex a React: frontend completo

Versión: domingo 15 nov 2026, 13:00. Para: Alessandro y la IA que use como asistente. Backend, contratos y datos: Brian.

Este documento es **la guía principal** para terminar el frontend. Parte del HTML actual (`AstroCortex_Sky.html`, un solo archivo) y lo pasa a React + Vite **conservando su diseño y la lógica que ya funciona**. Cubre las cuatro piezas: flipbook, vista del cielo, motor clasificatorio y agente.

Documentos de apoyo (solo como referencia; donde no coincidan, manda este):
- "Flipbook SPHEREx: qué pide el reto…": convenciones de píxel (4.1), coordenadas (5.3), reloj del flipbook (5.6), URL (5.11), textos (9).
- "Flipbook SPHEREx: correcciones con los datos reales": qué trae cada manifiesto real y qué debe verse en cada objetivo.
- "Dinámica del motor clasificatorio": qué significan `review_status`, `review_reasons` y `summary`.
- Guía del visor, secciones 7.3 (fuentes), 7.4 (catálogos), 7.7 (votos) y 9 (agente).

---

## 0. Reglas para la IA que aplique esta guía

1. **No crear un frontend nuevo al lado del actual.** Cada función del HTML se mueve a un componente, un hook o el store según el mapa de la sección 2. No se escribe una segunda versión del flipbook con el código de la otra guía.
2. **El diseño no cambia.** El CSS del HTML se copia completo. Las clases y los `id` se conservan.
3. **Todo número en pantalla sale del manifiesto o de la API.** Se elimina todo lo generado localmente (sección 3).
4. **Un solo estado global (Zustand).** Botones, teclado, tabla, Aladin y agente cambian el visor llamando a las mismas acciones del store.
5. Texto visible en **inglés**.
6. Prioridad: sección 12. Lo P0 primero.

---

## 1. Qué hay en el HTML actual

El HTML ya resuelve casi todo. Funciones que se conservan:

| Pieza | En el HTML | Estado |
|---|---|---|
| Intro del logo | `#intro`, `playIntro()` | Se conserva |
| Encabezado | búsqueda, accesos rápidos, Targets, FOV, Guide me, ⚙ | Se conserva; ⚙ cambia (sección 9.6) |
| Cielo | Aladin por `<script>`, malla `#mesh`, lista Objects, zoom, fondo | Se conserva |
| Flipbook | canvas `#frame`, `drawField()`, 6 paneles, blink, Difference, Sum, flags, retícula y recorrido | Se conserva con correcciones (sección 6) |
| Espectro y curva de luz | `drawPlot()` en el mismo canvas | Se conserva |
| Clasificación | tabla, filtro, Only moving, detalle, votos | Se amplía con las pestañas de revisión (sección 8) |
| Agente | orbe de partículas, chat, recorridos, voz, `validAction()`, `runAction()` | Se conserva; se quita la parte local (sección 9) |
| Paneles redimensionables | `.splitter`, `setPanelSize()` | Se conserva |
| URL | `syncURL()` | Se amplía (sección 10) |

---

## 2. Mapa del HTML a React

```
src/
  main.jsx                 monta <App/>, importa styles.css
  App.jsx                  layout (#app), intro, rutas / y /embed
  styles.css               TODO el <style> del HTML, sin cambios
  config.js                API_BASE y USE_MOCKS desde import.meta.env
  targets.js               los 5 objetivos (sección 5.1)
  store.js                 estado global (sección 4)
  lib/
    api.js                 fetchJSON, loadManifest, loadRelated, resource (sección 5)
    manifest.js            frameFor, availableEpochs, detectorInfo, positionFor
    coords.js              parseCoordinates del HTML + separationArcmin y pixelToSky (otra guía, 5.3)
    series.js              readSeries del HTML (CSV o JSON)
    draw.js                drawField del HTML partido en funciones (sección 6.2)
    combine.js             combineFrames del HTML (resta y suma)
    plot.js                drawPlot del HTML
    actions.js             validAction y runAction del HTML, conectados al store (sección 9.3)
    symbols.js             bodySymbol del HTML (íconos de clase)
    reasons.js             textos de review_reasons (sección 8.3)
  hooks/
    useFlipbookPlayer.js   reemplaza el reloj de animate() (sección 6.4)
    useUrlSync.js          sección 10
    useVoice.js            SpeechRecognition del HTML
    useElementSize.js      ResizeObserver para canvas
  components/
    Intro.jsx              #intro
    Header.jsx             header + búsqueda + accesos + FOV + Guide me + Share
    TargetDialog.jsx       #targetDialog
    SkyView.jsx            #sky: Aladin, malla, Objects, sky-tools
    MeshCanvas.jsx         drawMesh()
    FieldPanel.jsx         .field: pestañas, cabecera, tarjeta, detectores, área del frame, meta, controles
    FrameCanvas.jsx        canvas #frame (usa lib/draw.js, lib/plot.js)
    Timeline.jsx           .playback
    EpochOptions.jsx       .epoch-options
    ClassificationPanel.jsx  .classification (sección 8)
    SourceDetail.jsx       #sourceDetail
    AgentOrb.jsx           #agentOrb + drawOrb() + arrastre
    AgentChat.jsx          #chat, mensajes, recorrido, formulario, voz
    Splitters.jsx          #sideSplitter, #bottomSplitter
    Toast.jsx              #status (notify)
public/
  static/fields/<target_id>/...   carpeta static_fields que entrega Brian
  static/agent/<target_id>.json   respuestas grabadas del agente (si Brian las entrega)
vercel.json
```

Tabla de equivalencias:

| HTML | React |
|---|---|
| `state`, `field`, `sources`, `catalogs`, `spectrum`, `lightcurve`, `playing`, `blinking`, `trackingSource` | `useStore` (sección 4) |
| `$('id').textContent = …`, `innerHTML = …` | JSX que lee del store |
| `render()`, `renderPlayback()`, `renderSources()`, `renderSelected()`, `renderObjects()` | se eliminan: React vuelve a pintar al cambiar el store |
| `notify(text)` | `useStore.getState().notify(text)` + `<Toast/>` |
| `applyField(m)` | acción `openField` del store |
| `selectTarget(id)`, `loadField(ra, dec)` | acciones `selectTarget`, `openCoordinates` |
| `drawField()` | `FrameCanvas` + `lib/draw.js` |
| `animate()` | `useFlipbookPlayer` (flipbook), `AgentOrb` y `MeshCanvas` (sus propios `requestAnimationFrame`) |
| `askAgent()`, `runStep()`, `runAction()` | acciones `askAgent`, `runStep` del store + `lib/actions.js` |
| `initSky()`, `updateMarkers()`, `skyGoto()` | `SkyView` |
| listeners `onclick` al final del script | `onClick` en cada componente |
| `ResizeObserver` de `#app`, `#sky`, `.frame-area` | `useElementSize` en cada componente |
| `window.AstroCortexSky` | se elimina |

---

## 3. Qué se elimina

Todo lo que genera datos falsos o duplica configuración:

- `makeField`, `localFields`, `sceneRNG`, `floatURL`, `jsonURL`, `loadLocal`, `setLocalSeries`, `localAnswer`, `localTour`, `wantsNavigation`.
- Todas las ramas `if (field.local_generated)` y `m.local_sources`, `m.local_lightcurves`.
- El diálogo `#sceneData` y el botón `#sceneOrigin` ("Generated field").
- El arreglo `names` y los atajos que cargan la escena local de WISE 0855.
- El diálogo `#settings` (API y estáticos se configuran con variables de entorno) y la importación de paquetes (`#import`, `#package`, `packageData`).
- El arranque `loadLocal(133.7587, -7.2416, …)` al final del script.

Se conservan: `bodySymbol` (íconos de clase en Objects y en la tarjeta, con el `title` "Class symbol; not a resolved image of the source"), el orbe, la malla y la intro.

---

## 4. Estado global

`src/store.js`. Mantiene los nombres del HTML donde se puede, para que el código portado cambie poco.

```js
import { create } from "zustand";
import { loadManifest, loadRelated, postJSON, fetchStaticAgent } from "./lib/api";
import { availableEpochs } from "./lib/manifest";
import { runAction as execAction } from "./lib/actions";
import { TARGETS, findTargetByName } from "./targets";
import { parseCoordinates, separationArcmin } from "./lib/coords";

let fieldReq = 0;
let toastTimer = null;
let tourTimer = null;

export const useStore = create((set, get) => ({
  // Campo
  field: null, base: "", status: "idle", error: null, slowServer: false,
  sources: null, catalogs: null, spectrum: [], lightcurve: [],
  targetId: null,
  // Visor
  detector: 5, epochIndex: 0, playing: false, fps: 2,
  mode: "flip",                  // "flip" | "blink" | "diff" | "sum"
  grid: false,                   // vista de 6 paneles (se combina con cualquier modo)
  pairA: 0, pairB: 0,            // fechas de blink, resta y suma
  layers: { flags: false, gaia: false, wise: false, sources: true, track: true },
  tab: "flipbook",               // "flipbook" | "spectrum" | "lightcurve" | "catalogs"
  // Clasificación
  selectedSourceId: null, tracking: false,
  reviewTab: "needs_review", classFilter: "all", movingOnly: false,
  // Agente
  chatOpen: false, messages: [], agentBusy: false,
  tour: { steps: [], index: 0, auto: false, sourcesUsed: [], log: [] },
  // Avisos
  toast: "",

  notify: (text) => {
    set({ toast: text });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => set({ toast: "" }), 5000);
  },

  // ---- Carga de campos ----
  openField: async ({ targetId = null, ra = null, dec = null }) => {
    const id = ++fieldReq;
    set({ status: "loading", error: null, slowServer: false, playing: false, mode: "flip", grid: false,
          selectedSourceId: null, tracking: false, sources: null, catalogs: null, spectrum: [], lightcurve: [] });
    const slow = setTimeout(() => { if (id === fieldReq) set({ slowServer: true }); }, 3000);
    try {
      const { manifest, base } = await loadManifest({ targetId, ra, dec });
      if (id !== fieldReq) return;
      const dets = [...new Set(manifest.epochs.flatMap((e) => e.frames.map((f) => f.detector)))].sort((a, b) => a - b);
      const pref = TARGETS.find((t) => t.target_id === manifest.target_id)?.default_detector ?? get().detector;
      const detector = dets.includes(pref) ? pref : (dets[0] ?? 1);
      const avail = availableEpochs(manifest, detector);
      set({ field: manifest, base, status: "ready", targetId: manifest.target_id ?? null, detector,
            epochIndex: avail[0] ?? 0, pairA: avail[0] ?? 0, pairB: avail[avail.length - 1] ?? 0 });
      const related = await loadRelated(manifest, base);   // fuentes, catálogos, espectro, curva
      if (id !== fieldReq) return;
      set(related);
    } catch (e) {
      if (id === fieldReq) set({ status: "error", error: { code: e.code ?? "network", message: e.message } });
    } finally {
      clearTimeout(slow);
      if (id === fieldReq) set({ slowServer: false });
    }
  },
  selectTarget: (targetId) => get().openField({ targetId }),
  openCoordinates: (ra, dec) => get().openField({ ra, dec }),
  search: (text) => {
    const t = findTargetByName(text);
    if (t) return get().selectTarget(t.target_id);
    const c = parseCoordinates(text);
    if (!c) return get().notify("Not recognized. Enter RA Dec (e.g. 133.7587 -7.2416 or 08h55m10.8s -07d14m42s) or a test target name.");
    const near = TARGETS.find((t) => t.motion_arcsec_yr > 1 && separationArcmin({ ra: c[0], dec: c[1] }, t.approx_center) < 8);
    if (near) get().notify(`This position is near ${near.name}, which moves ${near.motion_arcsec_yr}″/yr. Opening its current position.`);
    return near ? get().selectTarget(near.target_id) : get().openCoordinates(c[0], c[1]);
  },

  // ---- Visor ----
  setDetector: (d) => set((s) => {
    if (!s.field) return { detector: d, grid: false };
    const avail = availableEpochs(s.field, d);
    return { detector: d, grid: false, epochIndex: avail.includes(s.epochIndex) ? s.epochIndex : (avail[0] ?? s.epochIndex) };
  }),
  toggleGrid: () => set((s) => ({ grid: !s.grid, tab: "flipbook" })),
  setEpoch: (i) => set({ epochIndex: i }),
  setEpochById: (eid) => set((s) => {
    const i = s.field?.epochs.findIndex((e) => e.epoch_id === eid) ?? -1;
    return i >= 0 ? { epochIndex: i } : {};
  }),
  play: () => set({ playing: true, mode: "flip" }),
  pause: () => set({ playing: false }),
  togglePlay: () => set((s) => ({ playing: !s.playing, mode: "flip" })),
  setFps: (f) => set({ fps: Math.min(8, Math.max(0.5, Number(f) || 2)) }),
  setMode: (mode) => set((s) => ({
    mode: s.mode === mode ? "flip" : mode,
    playing: false,
    tab: "flipbook",
    epochIndex: mode === "blink" ? s.pairA : s.epochIndex,
  })),
  setPair: (a, b) => set({ pairA: a, pairB: b }),
  setLayer: (k, on) => set((s) => ({ layers: { ...s.layers, [k]: on ?? !s.layers[k] } })),
  setTab: (tab) => set({ tab }),

  // ---- Clasificación ----
  selectSource: (id) => set((s) => {
    const src = s.sources?.sources?.find((x) => x.source_id === id);
    if (!src || !s.field) return {};
    const avail = availableEpochs(s.field, s.detector);
    return { selectedSourceId: id, tab: "flipbook", grid: false, playing: false, mode: "blink",
             pairA: avail[0] ?? 0, pairB: avail[avail.length - 1] ?? 0, epochIndex: avail[0] ?? 0 };
  }),
  toggleTracking: () => set((s) => ({ tracking: !s.tracking, playing: !s.tracking ? true : s.playing })),
  setReviewTab: (t) => set({ reviewTab: t }),
  setClassFilter: (v) => set({ classFilter: v }),
  setMovingOnly: (v) => set({ movingOnly: v }),
  vote: async (source, label) => {
    const s = get();
    try {
      await postJSON("/api/marks", {
        field_id: s.field.field_id, source_id: source.source_id, ra: source.ra, dec: source.dec,
        epoch_mjd: source.epoch_mjd ?? s.field.epochs[s.epochIndex]?.mjd_avg,
        user_label: label, comment: "", client_id: clientId(),
      });
      s.notify("Vote saved");
    } catch (e) { s.notify(e.message); }
  },

  // ---- Agente ----
  openChat: (open = true) => set({ chatOpen: open }),
  askAgent: async (message) => {
    const s = get();
    if (!message.trim() || s.agentBusy) return;
    s.pauseTour();
    const history = s.messages.slice(-12).map((m) => ({ role: m.role, content: m.text }));
    set({ chatOpen: true, agentBusy: true, messages: [...s.messages, { role: "user", text: message }, { role: "assistant", text: "…" }] });
    let response;
    try {
      response = await postJSON("/api/agent", { message, view_state: viewState(get()), history }, 30000);
    } catch (e) {
      response = await fetchStaticAgent(get().targetId).catch(() => null);
      if (!response) response = { reply: "The guide is not available right now. You can keep exploring with the controls.", steps: [], sources_used: [] };
    }
    if (typeof response.reply !== "string") response = { reply: "The guide returned an invalid answer.", steps: [], sources_used: [] };
    set((st) => ({
      agentBusy: false,
      messages: [...st.messages.slice(0, -1), { role: "assistant", text: response.reply }],
      tour: { steps: Array.isArray(response.steps) ? response.steps : [], index: 0, auto: false,
              sourcesUsed: response.sources_used ?? [], log: [] },
    }));
    if (get().tour.steps.length) await get().runStep(0);
  },
  runStep: async (i) => {
    const step = get().tour.steps[i];
    if (!step) return;
    set((st) => ({ tour: { ...st.tour, index: i } }));
    for (const a of step.actions ?? []) {
      const ok = await execAction(a, get());
      set((st) => ({ tour: { ...st.tour, log: [...st.tour.log, ok ? a.type : `skipped ${a?.type}`].slice(-20) } }));
    }
  },
  toggleTourAuto: () => {
    const st = get();
    if (st.tour.auto) return st.pauseTour();
    set({ tour: { ...st.tour, auto: true } });
    tourTimer = setInterval(async () => {
      const t = get().tour;
      if (t.index >= t.steps.length - 1) return get().pauseTour();
      await get().runStep(t.index + 1);
    }, 6500);
  },
  pauseTour: () => { clearInterval(tourTimer); set((st) => ({ tour: { ...st.tour, auto: false } })); },
  stopTour: () => { clearInterval(tourTimer); set((st) => ({ tour: { ...st.tour, steps: [], auto: false } })); },
}));

export function viewState(s) {
  return { ra: s.field?.center.ra ?? null, dec: s.field?.center.dec ?? null, fov_arcmin: s.field?.fov_arcmin ?? 3,
           target_id: s.targetId, detector: s.detector, epoch_id: s.field?.epochs[s.epochIndex]?.epoch_id ?? null,
           selected_source_id: s.selectedSourceId };
}

function clientId() {
  try {
    let id = localStorage.getItem("astrocortex-client");
    if (!id) { id = crypto.randomUUID(); localStorage.setItem("astrocortex-client", id); }
    return id;
  } catch { return crypto.randomUUID(); }
}
```

Regla de pausa (como `pauseTour()` del HTML): todo control manual (clic en el canvas, cielo, controles, tabla) llama a `pauseTour()` antes de su acción. El usuario siempre puede tomar el control.

---

## 5. Datos

### 5.1 `src/targets.js`

Los centros y detectores son los de la hoja de datos reales.

```js
export const TARGETS = [
  { target_id: "barnard",  name: "Barnard's Star", short: "Barnard",    motion_arcsec_yr: 10.4, default_detector: 2,
    aliases: ["barnard", "barnards star", "barnard's star", "gj 699"], approx_center: { ra: 269.44622, dec: 4.76881 } },
  { target_id: "epsindib", name: "Epsilon Indi B", short: "Eps Indi B", motion_arcsec_yr: 4.7,  default_detector: 5,
    aliases: ["eps indi b", "epsilon indi b", "eps ind b"], approx_center: { ra: 331.09629, dec: -56.80046 } },
  { target_id: "wise0855", name: "WISE 0855-0714", short: "WISE 0855",  motion_arcsec_yr: 8.1,  default_detector: 5,
    aliases: ["wise 0855", "wise0855", "wise 0855-0714", "wise j085510.83-071442.5"], approx_center: { ra: 133.75945, dec: -7.24286 } },
  { target_id: "rwaur",    name: "RW Aurigae",     short: "RW Aur",     motion_arcsec_yr: 0,    default_detector: 3,
    aliases: ["rw aur", "rw aurigae"], approx_center: { ra: 76.95609, dec: 30.40113 } },
  { target_id: "rdra",     name: "R Draconis",     short: "R Dra",      motion_arcsec_yr: 0,    default_detector: 3,
    aliases: ["r dra", "r draconis"], approx_center: { ra: 248.16723, dec: 66.75502 } },
];

export const findTargetByName = (text) => {
  const q = text.trim().toLowerCase().replace(/\s+/g, " ");
  return TARGETS.find((t) => t.aliases.includes(q) || t.name.toLowerCase() === q || t.target_id === q) ?? null;
};
```

### 5.2 `src/config.js` y variables de entorno

```js
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
```

- `.env.development`: `VITE_API_BASE=http://localhost:8000`
- Vercel: `VITE_API_BASE=https://<servicio-de-brian>.onrender.com`

### 5.3 `src/lib/api.js`

Reglas:
- Objetivo → manifiesto estático del propio sitio (`/static/fields/<id>/manifest.json`). No depende de Render.
- Coordenada libre → `GET /api/field`. Si no hay cobertura, el backend responde `no_coverage`.
- Fuentes y catálogos: si el manifiesto los trae en `null`, se piden a la API por `field_id` (los estáticos los traen en `null`).
- Espectro y curva de luz: solo si el manifiesto trae la URL.

```js
import { API_BASE } from "../config";
import { TARGETS } from "../targets";
import { readSeries } from "./series";

const err = (message, code) => Object.assign(new Error(message), { code });

export async function fetchJSON(url, timeoutMs = 15000, init = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...init, signal: ctrl.signal });
    const body = await r.json().catch(() => null);
    if (!r.ok || body?.error) throw err(body?.error?.message ?? `Request failed (${r.status})`, body?.error?.code ?? `http_${r.status}`);
    return body;
  } catch (e) {
    if (e.name === "AbortError") throw err("The server did not answer in time.", "timeout");
    if (e.code) throw e;
    throw err("Could not reach the server.", "network");
  } finally { clearTimeout(timer); }
}

export const postJSON = (path, data, timeoutMs = 18000) => {
  if (!API_BASE) return Promise.reject(err("The team API is not configured.", "no_api"));
  return fetchJSON(API_BASE + path, timeoutMs, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
};

export function validManifest(m) {
  const ok = m && m.field_id && m.center && Number.isFinite(m.center.ra) && Number.isFinite(m.center.dec)
    && Number.isInteger(m.nx) && Number.isInteger(m.ny) && Array.isArray(m.detectors) && Array.isArray(m.epochs);
  if (!ok) throw err("Invalid field manifest", "bad_manifest");
  return m;
}

export async function loadManifest({ targetId, ra, dec }) {
  const target = TARGETS.find((t) => t.target_id === targetId);
  if (target) {
    try {
      return { manifest: validManifest(await fetchJSON(`/static/fields/${target.target_id}/manifest.json`)), base: "" };
    } catch (e) {
      if (!API_BASE) throw e;
      ({ ra, dec } = target.approx_center);
    }
  }
  if (!API_BASE) throw err("No SPHEREx images cover this position yet.", "no_coverage");
  const q = new URLSearchParams({ ra: ra.toFixed(5), dec: dec.toFixed(5), fov_arcmin: "3" });
  return { manifest: validManifest(await fetchJSON(`${API_BASE}/api/field?${q}`, 90000)), base: API_BASE };
}

export const resolveUrl = (url, base) => (/^(https?:|data:|blob:)/.test(url) ? url : (base || "") + url);

export async function loadRelated(m, base) {
  const api = (path) => (API_BASE ? API_BASE + path : null);
  const sourcesUrl = m.sources_url ? resolveUrl(m.sources_url, base) : api(`/api/sources?field_id=${encodeURIComponent(m.field_id)}`);
  const catalogsUrl = m.catalogs_url ? resolveUrl(m.catalogs_url, base) : api(`/api/catalogs?field_id=${encodeURIComponent(m.field_id)}`);
  const [sources, catalogs, spectrum, lightcurve] = await Promise.allSettled([
    sourcesUrl ? fetchJSON(sourcesUrl, 60000) : null,
    catalogsUrl ? fetchJSON(catalogsUrl, 60000) : null,
    m.spectrum_url ? readSeries(resolveUrl(m.spectrum_url, base)) : [],
    m.lightcurve_url ? readSeries(resolveUrl(m.lightcurve_url, base)) : [],
  ]);
  const val = (r, d) => (r.status === "fulfilled" ? r.value ?? d : d);
  return { sources: val(sources, null), catalogs: val(catalogs, null), spectrum: val(spectrum, []), lightcurve: val(lightcurve, []) };
}

export const fetchStaticAgent = (targetId) =>
  targetId ? fetchJSON(`/static/agent/${targetId}.json`, 8000) : Promise.reject(err("no target", "none"));

// Caché de imágenes y datos crudos (resource() del HTML)
const cache = new Map();
export function resource(url, base, type = "image", expectedBytes = null) {
  if (!url) return Promise.resolve(null);
  const key = type + resolveUrl(url, base);
  if (!cache.has(key)) {
    const full = resolveUrl(url, base);
    const p = type === "float"
      ? fetch(full).then((r) => { if (!r.ok) throw err("Pixel data unavailable", "data"); return r.arrayBuffer(); })
          .then((b) => {
            if (expectedBytes && b.byteLength !== expectedBytes) throw err("Unexpected data size", "data");
            const dv = new DataView(b), out = new Float32Array(b.byteLength / 4);
            for (let k = 0; k < out.length; k++) out[k] = dv.getFloat32(4 * k, true);   // little-endian
            return out;
          })
      : new Promise((resolve, reject) => {
          const im = new Image();
          im.crossOrigin = "anonymous";
          im.onload = () => resolve(im);
          im.onerror = () => reject(err("Image unavailable", "image"));
          im.src = full;
        });
    p.catch(() => cache.delete(key));
    cache.set(key, p);
  }
  return cache.get(key);
}
```

### 5.4 `src/lib/manifest.js`

```js
export const frameFor = (m, epochIndex, det) => m?.epochs[epochIndex]?.frames.find((f) => f.detector === det) ?? null;

export const availableEpochs = (m, det) =>
  (m?.epochs ?? []).map((e, i) => ((det == null ? e.frames.length > 0 : e.frames.some((f) => f.detector === det)) ? i : -1))
    .filter((i) => i >= 0);

export const detectorInfo = (m, det) => m?.detectors.find((d) => d.detector === det) ?? null;

// Posición de una fuente en una época: positions por época si existen; si no, su x/y única
export const positionFor = (s, e) => s?.positions?.[e?.epoch_id] ?? s ?? null;
```

---

## 6. Flipbook

### 6.1 `FieldPanel.jsx`

Es la `<section class="field">` del HTML con el mismo marcado. Cambios:

- **Cabecera** (`.field-head`): `#fieldName` = nombre del objetivo; `#fieldUnit` = `flux_unit`; `#sequenceInfo` = `date {i}/{N} · {días} days`, donde `i` y `N` cuentan las fechas disponibles del detector y `días` es la diferencia entre la primera y la última `mjd_avg` (el HTML lo mostraba en horas porque su escena duraba un día).
- **Detectores** (`#detectors`): D1–D6 llaman a `setDetector(n)`; se desactiva el botón de un detector sin cuadros en el campo; `title` con el rango λ. "6 panels" llama a `toggleGrid()`.
- **Etiqueta** (`#frameMeta`): `{date_iso} · MJD {mjd_avg} · D{n} ({λmin}–{λmax} µm) · {n_exposures} exposures · {round(flagged_frac·100)}% flagged`. En blink se agrega `· blinking A {fecha} ↔ B {fecha}`; en resta, `Difference B − A · white = brighter in B, black = brighter in A`; en suma, `Sum A + B`.
- **Estados**: cargando `Loading SPHEREx images…`; con `slowServer`, `Waking up server (free hosting can take up to a minute).`; error según `error.code` con botón `Retry`; sin campo, `Enter coordinates or pick a test target.`; `no_coverage` → `No SPHEREx images cover this position yet.` y debajo los 5 objetivos con `Try a test target:`.

### 6.2 `FrameCanvas.jsx` y `lib/draw.js`

Se porta `drawField()` casi tal cual. Lee del store en vez de variables globales. Las correcciones obligatorias son:

1. **Fondo "sin dato" morado.** Los PNG reales tienen alfa 0 en los píxeles sin dato (bordes y núcleos saturados). Antes de dibujar cada imagen se pinta su rectángulo con `#3a2a4a`; así esos píxeles se ven morados y no negros.
2. **Escala entera.** Se conserva el cálculo del HTML: `scale = Math.max(1, Math.floor(Math.min((cellW - 12) / nx, (cellH - 12) / ny)))` en píxeles del dispositivo, y `imageSmoothingEnabled = false`.
3. **Qué imagen se dibuja.** Modo `diff` o `sum` → `combineFrames(det)`. En cualquier otro modo → el PNG de `frameFor(field, epochIndex, det)`.
4. **Fecha sin el detector.** Mensaje dentro de la celda: `No D{n} data for this date.`
5. **Retícula y recorrido.** Posición: fuente seleccionada (`positionFor(source, epoch)`) o, si no hay, `epoch.expected_position`. Retícula cian `#00e5ff` con borde negro y hueco central; recorrido punteado con todas las épocas. Centro del píxel `(x, y)` en `left + (x + 0.5)·scale`, `top + (y + 0.5)·scale`.
6. **Flags** a 0.55 de opacidad sobre la imagen, solo si `layers.flags` y `frame.flags_url`.
7. **Fuentes clasificadas** como círculos por clase (código del HTML, con `colors` y `frameHits` para el clic). Solo si hay `sources` y `layers.sources`.
8. **Brújula y barra de 30″** en la vista de un solo panel: se reemplaza el texto `N ↑ E ←` del HTML por `drawCompassAndScale()` de la otra guía (5.5), o se deja el texto si no hay tiempo.

Esqueleto del componente:

```jsx
import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { useElementSize } from "../hooks/useElementSize";
import { drawFrame } from "../lib/draw";
import { drawPlot } from "../lib/plot";

export function FrameCanvas() {
  const ref = useRef(null);
  const [boxRef, size] = useElementSize();
  const s = useStore();
  useEffect(() => {
    const c = ref.current;
    if (!c || size.width <= 0) return;
    let cancelled = false;
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.floor(size.width * dpr);
    c.height = Math.floor(size.height * dpr);
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#0b0b0e";
    ctx.fillRect(0, 0, c.width, c.height);
    if (!s.field) return;
    if (s.tab === "spectrum" || s.tab === "lightcurve") { drawPlot(ctx, c.width, c.height, s); return; }
    drawFrame(ctx, c, s, () => cancelled).then((hits) => { if (!cancelled) c._hits = hits; });
    return () => { cancelled = true; };
  }, [s.field, s.base, s.detector, s.epochIndex, s.mode, s.grid, s.pairA, s.pairB, s.layers, s.sources,
      s.selectedSourceId, s.tab, size.width, size.height]);

  const onClick = (e) => {
    const st = useStore.getState();
    st.pauseTour();
    if (st.tab !== "flipbook") return;
    const c = ref.current, r = c.getBoundingClientRect();
    const x = (e.clientX - r.left) * c.width / r.width, y = (e.clientY - r.top) * c.height / r.height;
    const hit = (c._hits ?? []).map((h) => ({ ...h, d: Math.hypot(x - h.x, y - h.y) }))
      .filter((h) => h.d < h.radius).sort((a, b) => a.d - b.d)[0];
    if (hit) st.selectSource(hit.id);
  };
  return <div className="frame-area" ref={boxRef}><canvas id="frame" ref={ref} onClick={onClick} /></div>;
}
```

`lib/draw.js` → `drawFrame(ctx, canvas, state, isCancelled)` contiene el cuerpo de `drawField()` del HTML con las correcciones 1–8, y devuelve `frameHits`. Las imágenes se piden con `resource(url, state.base)`.

### 6.3 `lib/combine.js` (resta y suma)

Se porta `combineFrames()` del HTML. Cambios:
- Usa `resource(frame.data_url, base, "float", nx * ny * 4)`.
- A y B son `pairA` y `pairB`.
- Color de NaN: `[58, 42, 74]`.
- Si falta `data_url` en alguna de las dos fechas: error `Difference needs raw data (data_url) for both dates.`
- La resta usa la escala de la otra guía (5.4, `differenceToRGBA`: percentil 99 de |B − A|). La escala de la suma se mantiene como en el HTML.

### 6.4 `hooks/useFlipbookPlayer.js` (reemplaza el reloj de `animate()`)

- **Flipbook:** un cuadro cada `1/fps` s, solo por las fechas disponibles del detector (o con algún cuadro en la vista de 6). El último cuadro dura el doble.
- **Blink:** alterna `pairA` y `pairB` cada 500 ms.
- **Seguimiento (Track):** si `tracking` está activo, en cada cambio de época se centra Aladin en la posición de la fuente seleccionada (lo hace `SkyView` al suscribirse a `epochIndex`).

El código es el de la otra guía, sección 5.6, con `mode === "flip"` (y `grid` permitido) para el flipbook y `mode === "blink"` para el blink. Antes de animar se precargan todos los cuadros que se van a mostrar (misma sección); mientras tanto, Play queda desactivado y se muestra `Loading frames {done}/{total}…`.

### 6.5 `Timeline.jsx` y `EpochOptions.jsx`

- ‹ ▶ › y el deslizador recorren **las fechas disponibles del detector**, no todos los índices (fragmento de la otra guía, 5.7). Se desactivan en blink, resta y suma, y con menos de 2 fechas.
- Velocidad: opciones ordenadas `0.5, 1, 2, 4, 8` fps; 2 por defecto. El HTML tenía 12 fps y el orden mezclado.
- A y B: selects con `{n} · {date_iso}`; cambian `setPair`.
- Blink, Difference y Sum: `setMode("blink" | "diff" | "sum")`. Se desactivan con menos de 2 fechas.
- Casillas Flags, Gaia y WISE: `setLayer`.
- Con una sola fecha: `Only one date is available here, so motion can't be shown. Try the 6-detector view or another field.`

### 6.6 FOV

Solo hay datos de 3.2′: el select muestra una única opción `3′` y queda desactivado.

---

## 7. Vista del cielo (`SkyView.jsx`)

Se porta `initSky()` en un `useEffect(() => {...}, [])` que crea Aladin **una sola vez** (en desarrollo, StrictMode ejecuta los efectos dos veces: hay que guardar la instancia en un `useRef` y no crearla si ya existe). Se conserva la carga por `<script>` de la URL del HTML, que ya funciona.

- **Centrar:** al cambiar `field`, `animateToRaDec(field.center)` y `setFov(fieldViewFov())` (la función del HTML).
- **Marcadores:** `updateMarkers()` del HTML en un `useEffect` que depende de `field`, `sources`, `catalogs`, `layers` y `epochIndex`. Se borra la rama `local_generated`: los marcadores de clase usan siempre `shapes[label]` y `colors[label]`.
- **Clic en un marcador:** `objectClicked` → `selectSource(source_id)` o `selectTarget(target_id)`.
- **Objects:** la lista del HTML (`renderObjects`) pasa a JSX con los íconos de `bodySymbol`.
- **Fondo:** el select de AllWISE / 2MASS / SPHEREx D1 se conserva.
- **Si Aladin no carga:** se muestra el mensaje en `#skyNotice` y se agrega la clase `field-panel-only` al `body`, como hace el HTML.
- La malla (`MeshCanvas`) y los botones de zoom se conservan tal cual.

---

## 8. Motor clasificatorio (`ClassificationPanel.jsx`, `SourceDetail.jsx`)

El frontend no sabe si el motor es una red neuronal o la regla del índice de metano: solo lee el contrato. Las fuentes llegan de `GET /api/sources?field_id=…` (sección 5.3) con el formato de la guía del visor 7.3 más los campos de la "Dinámica del motor clasificatorio" (sección 5): `catalog`, `agreement`, `review_status`, `review_reasons` y `summary`.

### 8.1 Encabezado

Se conserva `.classification-head` y se agrega:
- **Resumen** desde `sources.summary`: `{n_sources} sources · {needs_review} need review · {classified} classified · {known} known`.
- **Pestañas de revisión:** `Needs review (n)`, `Classified (n)`, `Known (n)`; abierta por defecto `Needs review`. Si las fuentes no traen `review_status`, se ocultan las pestañas y se muestra la lista completa ordenada como en el HTML (`rankedSources`).
- Se conservan el filtro de clase y `Only moving`.

### 8.2 Tabla

Columnas del HTML: Source, Class, Confidence/Priority, Moves (px), Methane idx, Gaia, CatWISE, JPL, Flags %. Se agregan:
- En **Needs review**: columna `Why` con los chips de `review_reasons` (sección 8.3).
- En **Known**: columnas `Catalog` (`catalog.known_label`, `catalog.known_source`) y `Match` (`agrees` ✓, `disagrees` ✗ con la fila resaltada, `no_reference` —).

Reglas:
- **Confidence:** si `sources.calibrated` es `true`, `class_probs[label]` en porcentaje. Si no, `Rank {n}` (como en el HTML).
- **`unknown`** se muestra como `Needs review`, nunca como descubrimiento.
- **Clases candidatas** (`cold_brown_dwarf`, `asteroid_comet`) llevan el prefijo `Candidate · `.
- Clic en una fila → `selectSource(id)`: se selecciona en tabla, cielo y flipbook, y arranca el blink primera/última fecha.
- Sin fuentes: `Classification is not available for this field yet.`

### 8.3 `lib/reasons.js`

```js
const REASONS = {
  moves_without_catalog_motion: "Moves, no catalog motion",
  methane_index_high_not_known: "High methane index, not a known dwarf",
  no_gaia_counterpart: "No Gaia counterpart",
  only_one_epoch: "Only in one epoch",
  low_confidence: "Low confidence",
  disagrees_with_catalog: "Disagrees with catalog",
};
export const reasonText = (code) => REASONS[code] ?? String(code).replace(/_/g, " ");
```

La lista definitiva de códigos la confirma Brian. Un código nuevo se muestra igual, con los guiones bajos reemplazados por espacios.

### 8.4 Detalle de la fuente (`SourceDetail.jsx`)

Se conserva `renderSourceDetail()` del HTML:
- Chips de evidencia: `Moves {motion_px} px`, `Methane index {methane_index}`, `In Gaia` / `Not in Gaia`, `In CatWISE` / `Not in CatWISE`, `JPL: {jpl_match.name}` y los de `review_reasons`.
- Barras por clase (`<meter>`) solo si `calibrated`.
- Línea del catálogo: `Catalog: {known_label} ({known_source})` o `No catalog type`.
- Votos `Real / Artifact / Not sure` → `vote(source, label)`. Se muestran en `needs_review` y `classified`.
- Botón `Ask Cortex` → `askAgent("Explain the selected source")`.

### 8.5 Pie

`.provenance`: `{Rule-based | Model} · {model_version} · {data_release} · {pipeline_commit}`, desde `sources.method`, `sources.model_version`, etc.

### 8.6 Tarjeta de selección (`#selectedCard`)

Se conserva: ícono de clase, `source_id`, nombre, clase (`Candidate · ` si corresponde) y el botón `Track`, que llama a `toggleTracking()`.

---

## 9. Agente (Cortex)

### 9.1 Qué se conserva

El orbe de partículas (`AgentOrb.jsx`: `drawOrb`, arrastre, clase `working`), el chat (`AgentChat.jsx`: mensajes, formulario, voz) y los controles del recorrido (Back, Next, Auto, Stop, "Sources & actions").

### 9.2 Flujo

1. El usuario escribe, habla o pulsa `Guide me` → `askAgent(message)`.
2. `POST /api/agent` con `{message, view_state, history}` (guía del visor, sección 9.2).
3. La respuesta trae `reply`, `steps` y `sources_used`. Se muestra `reply`; si hay `steps`, aparece el recorrido y se ejecuta el paso 0.
4. Si la API falla o tarda más de 30 s → `/static/agent/<target_id>.json`. Si tampoco existe: `The guide is not available right now. You can keep exploring with the controls.`
5. El orbe muestra `Working…` mientras `agentBusy` es `true`.

Se elimina la lógica local (`localTour`, `localAnswer`, `wantsNavigation`): el backend decide si una pregunta lleva recorrido.

### 9.3 `lib/actions.js`

Se copia `validAction()` del HTML sin cambios. `runAction()` pasa a llamar al store:

```js
import { useStore } from "../store";

export async function runAction(a, s) {
  if (!validAction(a)) return false;
  const st = useStore.getState();
  const idx = (eid) => st.field?.epochs.findIndex((e) => e.epoch_id === eid) ?? -1;
  switch (a.type) {
    case "goto":               await st.openCoordinates(a.ra, a.dec); break;
    case "select_target":      if (st.targetId !== a.target_id) await st.selectTarget(a.target_id); break;
    case "set_fov":            break;                      // solo hay 3.2′
    case "set_detector":       st.setDetector(a.detector); break;
    case "show_detector_grid": if (!st.grid) st.toggleGrid(); break;
    case "set_epoch":          st.setEpochById(a.epoch_id); break;
    case "play_flipbook":      if (a.fps) st.setFps(a.fps); st.play(); break;
    case "pause":              st.pause(); break;
    case "blink":
    case "show_difference": {
      const i = idx(a.epoch_a), j = idx(a.epoch_b);
      if (i < 0 || j < 0) return false;
      st.setPair(i, j);
      useStore.setState({ mode: a.type === "blink" ? "blink" : "diff", playing: false, tab: "flipbook", epochIndex: i });
      break;
    }
    case "toggle_layer":       st.setLayer(a.layer, a.on); break;
    case "highlight":          window.dispatchEvent(new CustomEvent("astro-highlight", { detail: a })); break;  // SkyView lo escucha
    case "select_source":
    case "ask_vote":           st.selectSource(a.source_id); break;
    case "open_tab":
      if (a.tab === "classification") document.getElementById("classification")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      else st.setTab(a.tab);
      break;
    default: return false;
  }
  return true;
}

export function validAction(a) { /* copiar validAction() del HTML tal cual */ }
```

`SkyView` escucha `astro-highlight` y dibuja la cruz temporal de 8 s (código del caso `highlight` del HTML).

### 9.4 Voz

`useVoice` contiene el código de `SpeechRecognition` del HTML. Al terminar de hablar llama a `askAgent(texto)`. Sin soporte: `Voice input is not available in this browser. Use Chrome or type your question.`

### 9.5 Respuestas del agente

- `reply` se muestra como texto plano (`white-space: pre-wrap`), nunca como HTML.
- Acción inválida → se ignora y queda en el registro como `skipped …`.
- El agente solo afirma lo que dicen los endpoints. El frontend no agrega datos a sus respuestas.

### 9.6 Encabezado sin ⚙

El botón ⚙ (Settings) se reemplaza por `Share`: copia la URL actual (`navigator.clipboard.writeText(location.href)`) y avisa `View link copied`.

---

## 10. URL y `/embed`

Se reemplaza `syncURL()` por `useUrlSync` (otra guía, 5.11), con estos parámetros:

| Parámetro | Ejemplo | Significado |
|---|---|---|
| `target` | `wise0855` | Objetivo (tiene prioridad sobre `ra`/`dec`) |
| `ra`, `dec` | `133.75945`, `-7.24286` | Centro, 5 decimales |
| `det` | `5` | Detector |
| `t` | `e2` | Fecha actual |
| `mode` | `flip`, `blink`, `diff`, `sum` | Vista |
| `grid` | `1` | Vista de 6 paneles |
| `a`, `b` | `e1`, `e3` | Fechas de blink, resta y suma |
| `fps` | `2` | Velocidad |
| `src` | `s_0012` | Fuente seleccionada (se aplica cuando llegan las fuentes) |

Al abrir sin parámetros se carga WISE 0855 (estático), no una escena generada.

**`/embed`:** si `location.pathname` empieza con `/embed`, `App` muestra solo `FieldPanel` y un enlace `Open in the full tool` a `"/" + location.search`. Hace falta este `vercel.json`:

```json
{ "rewrites": [{ "source": "/((?!static/|assets/).*)", "destination": "/index.html" }] }
```

---

## 11. Pasos de la migración

1. **Proyecto:**
   ```
   npm create vite@latest astrocortex-web -- --template react
   cd astrocortex-web
   npm install
   npm install zustand
   ```
   Borrar el contenido de ejemplo de `src/App.jsx`, `src/App.css` y `src/index.css`.
2. **Estilos:** copiar todo el `<style>` del HTML a `src/styles.css`, sin tocarlo, e importarlo en `main.jsx`.
3. **Logo:** el `<svg>` de `<defs>` (gradientes y `#wordmark`) va al inicio de `App.jsx`, tal cual (con `stop-color` → `stopColor`, `stop-opacity` → `stopOpacity`, `font-family` → `fontFamily`, `stroke-width` → `strokeWidth`, `font-weight` → `fontWeight`, `font-size` → `fontSize`, `letter-spacing` → `letterSpacing`).
4. **Marcado:** copiar `<header>`, `<main id="app">`, el orbe, el chat y los diálogos a sus componentes (sección 2), convirtiendo a JSX (`class` → `className`, `for` → `htmlFor`, `<input>` → `<input />`, `aria-*` igual). Borrar lo de la sección 3.
5. **Datos:** `config.js`, `targets.js`, `lib/api.js`, `lib/manifest.js`. Copiar la carpeta `static_fields/` que entrega Brian como `public/static/fields/`.
6. **Store** (sección 4) y conectar el encabezado: los accesos rápidos y Targets llaman a `selectTarget`, y la búsqueda a `search`.
7. **Flipbook** (sección 6). Probar los 5 objetivos con el backend apagado.
8. **Cielo** (sección 7).
9. **Clasificación** (sección 8) contra la API de Brian.
10. **Agente** (sección 9).
11. **URL, `/embed` y atajos de teclado** (otra guía, 5.12).
12. **Vercel:** importar el repo con el preset Vite (build `npm run build`, salida `dist`), agregar la variable `VITE_API_BASE` y subir `vercel.json`.

---

## 12. Prioridades

| Prioridad | Qué |
|---|---|
| P0 | Pasos 1–7: flipbook con datos reales de los 5 objetivos, búsqueda, detectores, 6 paneles, blink, resta, flags, retícula, URL. Desplegado en Vercel |
| P0 | Tabla de clasificación leyendo `/api/sources` (aunque sea con `method: "rule"`) |
| P1 | Pestañas de revisión y votos; agente con recorridos; cielo con marcadores |
| P2 | Voz, suma, `/embed`, atajos de teclado |

Envío: domingo 15 antes de las 23:59 (meta del equipo: 22:00).

---

## 13. Pruebas finales

Flipbook (datos reales, con el backend apagado):

| Objetivo | Detector | Debe verse |
|---|---|---|
| WISE 0855 | D5 | Punto débil en la retícula que se corre ~1.3 px a la derecha entre e1 y e3 |
| Barnard's Star | D2 | Sube ~1.6 px (norte) entre e1 y e3; núcleo morado por saturación |
| Epsilon Indi B | D5 | ~1 px con blink; en e4, D1 y D4 muestran `No D1 data for this date.` |
| RW Aurigae | D3 | Quieto; cambia de brillo |
| R Draconis | D3 | Quieto; núcleo morado por saturación |

Además:
- La URL copiada en otra pestaña reproduce la vista.
- Una coordenada lejos de los 5 objetivos muestra `No SPHEREx images cover this position yet.` y los accesos a los objetivos.
- Con la API encendida: la tabla muestra fuentes, `Needs review` abre por defecto, el voto responde `Vote saved` y el pie dice `Rule-based` o `Model`.
- `Guide me` en WISE 0855 genera un recorrido cuyas acciones mueven el visor. Al tocar un control, el recorrido se pausa.
- Ningún texto dice "discovery" ni muestra números que no vengan del manifiesto o de la API.
- No queda rastro de la escena generada (buscar `local_generated` y `makeField` en el código: cero resultados).

---

## 14. Lo que el backend expone (Brian)

| Endpoint | Uso en el frontend |
|---|---|
| `/static/fields/<target_id>/…` | También en el propio sitio (`public/`); el backend los sirve para las coordenadas que resuelve `/api/field` |
| `GET /api/field?ra&dec&fov_arcmin` | Manifiesto del objetivo más cercano (<1′) o `404 no_coverage` |
| `GET /api/sources?field_id=f_<target_id>` | Tabla de clasificación (7.3 + campos de revisión) |
| `GET /api/catalogs?field_id=f_<target_id>` | Capas Gaia y WISE |
| `POST /api/agent` | Agente |
| `POST /api/marks`, `GET /api/marks?field_id=` | Votos |
| `/static/agent/<target_id>.json` | Respaldo del agente (si se generan) |

Todos los errores llegan con el formato `{"error": {"code": "...", "message": "..."}}`. CORS: dominio de Vercel y `http://localhost:5173`.
