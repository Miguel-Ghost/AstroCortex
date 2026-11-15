# Flipbook SPHEREx: qué pide el reto y qué cambiar en el frontend actual

Versión: domingo 15 nov 2026. Para: Alessandro (frontend) y la IA que use como asistente. Backend y contratos: Brian.

Este documento no reemplaza el frontend que ya existe. Dice qué stack se acordó, cómo pasar a ese stack lo que ya está hecho y qué agregar o cambiar para que el flipbook haga lo que pide el reto. Los contratos de datos completos están en la guía del visor (sección 7). Si algo choca, manda lo que confirme Brian, y por encima de todo, el enunciado del reto.

---

## 0. Stack acordado

| Pieza | Qué se usa | Para qué |
|---|---|---|
| Base | **React con Vite** (JavaScript; TypeScript es opcional) | Componentes, estado compartido, build para Vercel |
| Despliegue | **Vercel** | Sitio público; variables `VITE_API_BASE` y `VITE_USE_MOCKS` |
| Estado global | **Zustand** (o Context de React) | Un solo estado para flipbook, tabla de clasificación, agente y URL |
| Gráficos | **Recharts** o **Plotly** | Espectro y curva de luz (no el flipbook) |
| Vista del cielo | **aladin-lite** (paquete npm, v3) | Esfera del cielo con marcadores (P1) |
| Flipbook | `<canvas>` propio, sin librerías | Píxeles nítidos y escala de brillo bajo control |
| Backend | FastAPI en Render (Brian) | Manifiestos, imágenes, clasificación, agente |

Por qué no alcanza con HTML suelto: el agente mueve el visor llamando a las mismas acciones que los botones (`set_detector`, `blink`, `play_flipbook`…), la tabla de clasificación marca fuentes sobre el mismo canvas, y la URL refleja todo el estado. Eso exige un estado único compartido por componentes, que es lo que dan React y Zustand. Las funciones de las secciones 5.3 a 5.6 (coordenadas, escala de brillo, dibujo en canvas) son JavaScript puro y no dependen de React.

### 0.1 Pasar el HTML actual a Vite + React sin rehacer el diseño

El objetivo de esta etapa es que la página se vea **igual** que el HTML actual, pero dentro del proyecto Vite. El diseño no cambia.

1. Crear el proyecto e instalar Zustand:
   ```
   npm create vite@latest astrocortex-web -- --template react
   cd astrocortex-web
   npm install
   npm install zustand
   ```
2. Borrar el contenido de ejemplo de `src/App.jsx`, `src/App.css` y `src/index.css`.
3. Copiar la hoja de estilos actual a `src/styles.css` e importarla en `src/main.jsx`: `import "./styles.css";`.
4. Copiar imágenes, íconos y fuentes a `public/`. En el código se referencian con ruta absoluta: `/img/logo.png`.
5. Copiar el contenido del `<body>` actual dentro del `return (...)` de `App.jsx` y aplicar estas conversiones:

   | HTML | JSX |
   |---|---|
   | `class="x"` | `className="x"` |
   | `for="id"` | `htmlFor="id"` |
   | `style="width: 10px; color: red"` | `style={{ width: "10px", color: "red" }}` |
   | `<img ...>`, `<input ...>`, `<br>` | `<img ... />`, `<input ... />`, `<br />` |
   | `<!-- comentario -->` | `{/* comentario */}` |
   | `onclick="play()"` | `onClick={play}` |
   | `<select onchange="...">` | `<select value={...} onChange={(e) => ...}>` |

6. Los `<script>` del HTML no se copian tal cual:
   - lo que responde a clics pasa a funciones dentro del componente (`onClick`);
   - lo que modifica el DOM a mano (`innerHTML`, `getElementById`) pasa a estado de React y se pinta en el JSX;
   - lo que corre al cargar la página pasa a un `useEffect(() => { ... }, [])`;
   - las librerías cargadas por `<script src="https://...">` pasan a paquetes npm (`npm install aladin-lite`) e `import`.
7. `npm run dev` y comparar lado a lado con el HTML. Recién cuando se vean igual, partir `App.jsx` en los componentes de la guía del visor (sección 5): `TopBar`, `SearchBox`, `FieldPanel`, `FrameCanvas`, `TimelineControls`, `DetectorGrid`, `ClassificationTable`, `AgentPanel`.
8. Archivo `vercel.json` en la raíz del proyecto. Sin esto, abrir `/embed` directamente da 404 en Vercel:
   ```json
   { "rewrites": [{ "source": "/((?!static/|assets/).*)", "destination": "/index.html" }] }
   ```
9. Variables de entorno:
   - `.env.development`: `VITE_USE_MOCKS=1` y `VITE_API_BASE=http://localhost:8000`
   - En Vercel (Settings → Environment Variables): `VITE_USE_MOCKS=0` y `VITE_API_BASE=https://<servicio-de-brian>.onrender.com`
10. En Vercel: importar el repo, preset **Vite**, build `npm run build`, salida `dist`. Si el frontend vive en una subcarpeta del repo, indicarla en *Root Directory*.

---

## 1. Qué pide el reto

Texto oficial (sección Objectives):

> "Users will enter the coordinates of a patch of sky (Right Ascension and declination). Your tool will display a series of images of that patch like a little video, making it easy to spot moving objects."

En requisitos concretos:

1. El usuario escribe coordenadas RA y Dec.
2. La herramienta muestra **la serie de imágenes SPHEREx de esa zona, una tras otra, como un video corto**: el **flipbook**.
3. El objetivo es que se vea **qué se mueve** y qué cambia de brillo.
4. Se prueba con Barnard's Star, Epsilon Indi B, WISE 0855 (RA 08h55m10.831s, Dec −7°14′42.53″), RW Aurigae y R Draconis.

"Like a little video" significa una **animación en el navegador**: cuadros que se reemplazan en un canvas, con play y pausa. No es un MP4 ni un GIF hecho en el servidor, y no es el video de ≤30 s de la entrega.

Consideraciones opcionales del enunciado que toca el flipbook:

| Consideración | Dónde se resuelve |
|---|---|
| Coadd por cada uno de los 6 detectores | El backend entrega un cuadro por época y detector; el frontend elige detector y muestra los 6 a la vez (5.8) |
| Sumar o restar fechas | Resta B − A (5.9); suma en P1 |
| Campo de visión elegible | Selector de FOV (5.13) |
| Coordenadas en la URL, embebible | 5.11 |
| Metadatos y flags | Etiqueta del cuadro y capa de flags (5.5, 5.7) |

---

## 2. Resultado esperado

### 2.1 Lo que ve el usuario (WISE 0855)

1. Pulsa **WISE 0855** en la barra superior (o escribe "WISE 0855", o sus coordenadas).
2. Aparece un recorte de ~3′ × 3′ con píxeles grandes y nítidos (cada píxel SPHEREx es un cuadrado de ~6.2″). Norte arriba, este a la izquierda, brújula N/E y barra de 30″.
3. Una **retícula cian con hueco central** marca dónde debería estar WISE 0855 en esa fecha. Una línea fina con puntos muestra su recorrido en todas las fechas.
4. Debajo: `2025-05-25 · MJD 60820.5 · D6 (4.42–5.00 µm) · date 1/3 · 3 exposures · 1% flagged`.
5. **Play**: los cuadros pasan uno tras otro (2 por segundo por defecto). El punto avanza ~2 píxeles hacia la derecha (oeste) entre la primera y la última fecha. Las estrellas fijas no se mueven.
6. **Blink**: alterna primera y última fecha dos veces por segundo. El salto es evidente.
7. **Difference**: resta B − A en gris. Donde estaba el objeto queda un punto negro; donde está ahora, uno blanco. Las estrellas fijas desaparecen.
8. **All 6**: los 6 detectores de la misma fecha lado a lado. WISE 0855 casi no se ve en D1–D3 y se ve claro en D5–D6. Play anima los 6 juntos.
9. La URL cambia sola: `/?target=wise0855&ra=133.75870&dec=-7.24160&fov=3&det=6&t=e1&mode=flip&a=e1&b=e3&fps=2`. Abierta en otra pestaña, muestra lo mismo.
10. `/embed?…` con los mismos parámetros muestra solo el flipbook.

### 2.2 Definición de terminado

- [ ] RA/Dec en grados (`133.7587 -7.2416`) o sexagesimal (`08h55m10.8s -07d14m42s`, `08:55:10.8 -07:14:42`).
- [ ] Los 5 objetivos cargan con un clic desde archivos estáticos, aunque el backend esté caído.
- [ ] Play/pausa, anterior/siguiente, deslizador de fecha y velocidad.
- [ ] Cada cuadro muestra fecha ISO, MJD, detector, rango λ, exposiciones y % con flags.
- [ ] Todas las fechas de un detector usan la **misma escala de brillo**.
- [ ] Píxeles nítidos, también con el zoom de Windows al 125 %.
- [ ] Selector D1–D6 y vista de 6 detectores.
- [ ] Blink entre dos fechas elegibles (por defecto, primera y última).
- [ ] Retícula y recorrido de la posición esperada.
- [ ] Capa de flags activable.
- [ ] Una fecha sin el detector elegido muestra un aviso y no rompe la vista.
- [ ] Un campo con una sola fecha desactiva blink y resta y lo explica.
- [ ] Estado completo en la URL y ruta `/embed`.
- [ ] Mensajes de carga y de error claros.

---

## 3. Lo mínimo de SPHEREx para el flipbook

| Hecho | Consecuencia en el frontend |
|---|---|
| Un píxel mide ~6.2″ (`pixscale_arcsec`) | Las fuentes son puntos de 1–2 píxeles. Hay que agrandar cada píxel (×8 a ×16) sin suavizar |
| 6 detectores, cada uno con su rango de λ (D1 0.75–1.09 µm … D6 4.42–5.00 µm) | Nunca se mezclan detectores en una animación: un objeto frío aparece en D6 y desaparece en D1, y eso parecería movimiento o cambio de brillo |
| Cada zona se observa cada ~6 meses; cada pasada es una **época** | Un cuadro por época. Puede haber solo 2–4 cuadros; por eso existen blink y resta |
| El backend suma las exposiciones de una época por detector | Cada cuadro ya trae mejor señal que una exposición suelta |
| Movimientos esperados de 1 a 3 píxeles en ~1.5 años | Un suavizado o un corrimiento de 1 píxel arruina la visualización |
| Las variables cambian de brillo, no de posición | Si cada cuadro se autoescala, una variable parece constante. La escala la fija el backend por detector |
| La coordenada de WISE 0855 del enunciado es de 2010; en 2025–2026 el objeto está ~2.1′ al oeste | El centro lo decide el backend. Si alguien escribe la coordenada del enunciado, se avisa (5.10) |
| Hay píxeles sin dato en los bordes | Se pintan de morado oscuro, no de negro |
| Cada píxel puede tener flags | Capa semitransparente activable. No se ocultan fuentes por tener flags |

---

## 4. Datos que recibe el flipbook

Un solo documento por campo, el **manifiesto**: `GET /api/field?ra=…&dec=…&fov_arcmin=…`. Los 5 objetivos tienen el mismo manifiesto como archivo estático en `/static/fields/<target_id>/manifest.json` (va en `public/static/fields/` del proyecto).

| Campo | Uso |
|---|---|
| `center.ra`, `center.dec` | Centro del recorte. Es el que se muestra y el que va a la URL, no el que escribió el usuario |
| `fov_arcmin`, `nx`, `ny`, `pixscale_arcsec` | Tamaño del recorte |
| `detectors[]` | Rango λ de cada detector y su `stretch` (`type`, `vmin`, `vmax`): escala fija de brillo |
| `epochs[]` | Una entrada por fecha, en orden cronológico: `epoch_id`, `date_iso`, `mjd_avg` |
| `epochs[].frames[]` | Un cuadro por detector disponible. **Puede faltar algún detector** |
| `frames[].image_url` | PNG ya estirado por el backend |
| `frames[].data_url` | Datos crudos float32: permiten resta, valor del píxel y escala en el navegador |
| `frames[].flags_url` | PNG con flags coloreados, transparente donde no hay flag |
| `frames[].n_exposures`, `flagged_frac` | Etiqueta del cuadro |
| `epochs[].expected_position` | Posición esperada del objetivo en esa fecha (`x`, `y` en píxeles del recorte). `null` en coordenadas libres |
| `data_release`, `pipeline_commit` | Pie del panel |

### 4.1 Convenciones fijas (Brian las cumple en el backend)

1. **Píxeles:** `x` = columna, `y` = fila, desde 0, con los **enteros en el centro del píxel**. Fila 0 = norte (arriba), columna 0 = este (izquierda). En el canvas, el centro del píxel `(x, y)` está en `((x + 0.5)·s, (y + 0.5)·s)`, con `s` = píxeles de pantalla por píxel SPHEREx.
2. **`data_url`:** binario float32 little-endian de `ny × nx` valores, por filas, fila 0 = norte, NaN donde no hay dato. Tamaño exacto `nx·ny·4` bytes.
3. **`image_url`:** PNG con alfa 0 en los píxeles sin dato.
4. **`flags_url`:** PNG RGBA, alfa 0 donde no hay flag.
5. **URLs:** absolutas o empezando con `/`. Las que empiezan con `/` se resuelven contra el origen del manifiesto (la API o el propio sitio).
6. **Errores:** `{"error": {"code": "...", "message": "..."}}`; códigos con mensaje propio: `no_coverage`, `fov_too_large`, `upstream_unavailable`.
7. **`target_id`:** `barnard`, `epsindib`, `wise0855`, `rwaur`, `rdra`.

---

## 5. Cambios paso a paso

Cada paso dice qué agregar o cambiar en el frontend y cómo comprobarlo. Los fragmentos de código son las partes donde es fácil equivocarse; el resto se adapta a los componentes que ya existen.

### 5.1 Estado global

Si el frontend guarda la fecha o el detector actual dentro de un componente, se mueven a un estado global. Todo el visor (y después la tabla y el agente) lee y cambia el estado solo con estas acciones.

`src/store.js`:

```js
import { create } from "zustand";
import { loadField } from "./lib/api";
import { availableEpochs } from "./lib/manifest";
import { TARGETS } from "./targets";

let requestId = 0;

export const useStore = create((set, get) => ({
  // Campo
  ra: null, dec: null, fov: 3, targetId: null,
  manifest: null, base: "", status: "idle", error: null, slowServer: false,
  // Flipbook
  detector: 6, epochIndex: 0, playing: false, fps: 2,
  mode: "flip",                 // "flip" | "blink" | "diff" | "grid"
  pairA: 0, pairB: 0,           // fechas del blink y de la resta (índices de manifest.epochs)
  layers: { flags: false, track: true, sources: true },
  selectedSourceId: null,

  openField: async ({ ra, dec, fov = get().fov, targetId = null }) => {
    const id = ++requestId;
    set({ status: "loading", error: null, slowServer: false, playing: false, ra, dec, fov, targetId });
    const slow = setTimeout(() => { if (id === requestId) set({ slowServer: true }); }, 3000);
    try {
      const { manifest, base } = await loadField({ ra, dec, fov, targetId });
      if (id !== requestId) return;              // respuesta vieja: el usuario ya pidió otro campo
      const dets = [...new Set(manifest.epochs.flatMap((e) => e.frames.map((f) => f.detector)))];
      const preferred = TARGETS.find((t) => t.target_id === targetId)?.default_detector ?? get().detector;
      const detector = dets.includes(preferred) ? preferred : (dets.length ? Math.min(...dets) : 1);
      const avail = availableEpochs(manifest, detector);
      set({
        manifest, base, status: "ready", detector,
        ra: manifest.center.ra, dec: manifest.center.dec,   // el centro manda el manifiesto
        epochIndex: avail[0] ?? 0, pairA: avail[0] ?? 0, pairB: avail[avail.length - 1] ?? 0,
        mode: get().mode === "diff" || get().mode === "blink" ? "flip" : get().mode,
      });
    } catch (e) {
      if (id === requestId) set({ status: "error", error: { code: e.code ?? "network", message: e.message } });
    } finally {
      clearTimeout(slow);
      if (id === requestId) set({ slowServer: false });
    }
  },

  selectTarget: (targetId, fov) => {
    const t = TARGETS.find((x) => x.target_id === targetId);
    if (t) get().openField({ ra: t.approx_center.ra, dec: t.approx_center.dec, fov: fov ?? 3, targetId });
  },
  setFov: (fov) => { const s = get(); if (s.ra != null) s.openField({ ra: s.ra, dec: s.dec, fov, targetId: s.targetId }); },

  setDetector: (d) => set((s) => {
    if (!s.manifest) return { detector: d };
    const avail = availableEpochs(s.manifest, d);
    return { detector: d, epochIndex: avail.includes(s.epochIndex) ? s.epochIndex : (avail[0] ?? s.epochIndex) };
  }),
  setEpoch: (i) => set({ epochIndex: i }),
  setEpochById: (epochId) => set((s) => {
    const i = s.manifest?.epochs.findIndex((e) => e.epoch_id === epochId) ?? -1;
    return i >= 0 ? { epochIndex: i } : {};
  }),
  play: () => set({ playing: true }),
  pause: () => set({ playing: false }),
  togglePlay: () => set((s) => ({ playing: !s.playing })),
  setFps: (f) => set({ fps: Math.min(8, Math.max(0.5, f)) }),
  setMode: (mode) => set((s) => ({
    mode,
    playing: mode === "blink" || mode === "diff" ? false : s.playing,
    epochIndex: mode === "blink" ? s.pairA : s.epochIndex,
  })),
  setPair: (a, b) => set({ pairA: a, pairB: b }),
  toggleLayer: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
  selectSource: (id) => set({ selectedSourceId: id }),
}));
```

`src/lib/manifest.js` (utilidades que usan casi todos los componentes):

```js
// Cuadro de una época para un detector, o null si esa fecha no tiene ese detector
export const frameFor = (m, epochIndex, det) =>
  m.epochs[epochIndex]?.frames.find((f) => f.detector === det) ?? null;

// Índices de las épocas que tienen cuadro para `det` (det = null: épocas con algún cuadro)
export const availableEpochs = (m, det) =>
  m.epochs
    .map((e, i) => ((det == null ? e.frames.length > 0 : e.frames.some((f) => f.detector === det)) ? i : -1))
    .filter((i) => i >= 0);

export const detectorInfo = (m, det) => m.detectors.find((d) => d.detector === det);
```

### 5.2 Los 5 objetivos y la carga de datos

`src/targets.js`. `approx_center` sirve solo para pedir el campo y para el aviso de 5.10; el centro real lo da el manifiesto. Cuando exista `GET /api/targets`, esta lista sale de ahí.

```js
export const TARGETS = [
  { target_id: "barnard",  name: "Barnard's Star",  short: "Barnard",    motion_arcsec_yr: 10.4, default_detector: 2,
    aliases: ["barnard", "barnards star", "barnard's star", "gj 699"], approx_center: { ra: 269.4463, dec: 4.7682 } },
  { target_id: "epsindib", name: "Epsilon Indi B",  short: "Eps Indi B", motion_arcsec_yr: 4.7,  default_detector: 5,
    aliases: ["eps indi b", "epsilon indi b", "eps ind b"], approx_center: { ra: 331.0966, dec: -56.8007 } },
  { target_id: "wise0855", name: "WISE 0855-0714",  short: "WISE 0855",  motion_arcsec_yr: 8.1,  default_detector: 6,
    aliases: ["wise 0855", "wise0855", "wise 0855-0714", "wise j085510.83-071442.5"], approx_center: { ra: 133.7587, dec: -7.2416 } },
  { target_id: "rwaur",    name: "RW Aurigae",      short: "RW Aur",     motion_arcsec_yr: 0,    default_detector: 3,
    aliases: ["rw aur", "rw aurigae"], approx_center: { ra: 76.9564, dec: 30.4014 } },
  { target_id: "rdra",     name: "R Draconis",      short: "R Dra",      motion_arcsec_yr: 0,    default_detector: 3,
    aliases: ["r dra", "r draconis"], approx_center: { ra: 248.1674, dec: 66.7550 } },
];

export const findTargetByName = (text) => {
  const q = text.trim().toLowerCase().replace(/\s+/g, " ");
  return TARGETS.find((t) => t.aliases.includes(q) || t.name.toLowerCase() === q) ?? null;
};
```

`src/lib/api.js`. Reglas:
- objetivo con FOV 3′ → archivo estático (no depende de Render);
- coordenada libre o FOV distinto → API, con espera de hasta 90 s (Render gratuito tarda en despertar);
- si la API falla y era un objetivo → estático;
- cada cuadro se descarga una sola vez (caché); se prefiere `data_url` y, si no hay, `image_url`.

```js
import { TARGETS } from "../targets";
import { MOCK_DATA, mockManifest } from "./mock";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "1";
const staticUrl = (id) => `/static/fields/${id}/manifest.json`;

async function fetchJson(url, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    const body = await r.json().catch(() => null);
    if (!r.ok) throw Object.assign(new Error(body?.error?.message ?? r.statusText), { code: body?.error?.code ?? `http_${r.status}` });
    return body;
  } catch (e) {
    if (e.name === "AbortError") throw Object.assign(new Error("The server did not answer in time."), { code: "timeout" });
    if (e.code) throw e;
    throw Object.assign(new Error("Could not reach the server."), { code: "network" });
  } finally {
    clearTimeout(timer);
  }
}

export async function loadField({ ra, dec, fov, targetId }) {
  if (USE_MOCKS) return { manifest: mockManifest({ ra, dec }, targetId), base: "" };
  const target = TARGETS.find((t) => t.target_id === targetId);
  if (target && fov === 3) return { manifest: await fetchJson(staticUrl(target.target_id), 15000), base: "" };
  const url = `${API_BASE}/api/field?ra=${ra.toFixed(5)}&dec=${dec.toFixed(5)}&fov_arcmin=${fov}`;
  try {
    return { manifest: await fetchJson(url, 90000), base: API_BASE };
  } catch (e) {
    if (target) return { manifest: await fetchJson(staticUrl(target.target_id), 15000), base: "" };
    throw e;
  }
}

export const resolveUrl = (url, base) => (/^(https?:|data:|blob:|mock:)/.test(url) ? url : base + url);

export function loadImage(url, base) {
  const img = new Image();
  img.crossOrigin = "anonymous";               // necesario si las imágenes vienen de Render
  img.src = resolveUrl(url, base);
  return img.decode().then(() => img);
}

const frameCache = new Map();
export function loadFrame(frame, base, nx, ny) {
  const url = frame.data_url ?? frame.image_url;
  const key = resolveUrl(url, base);
  if (!frameCache.has(key)) {
    let p;
    if (key.startsWith("mock:")) p = Promise.resolve({ kind: "data", data: MOCK_DATA.get(key) });
    else if (frame.data_url) {
      p = fetch(key)
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.arrayBuffer(); })
        .then((buf) => {
          if (buf.byteLength !== nx * ny * 4) throw new Error("Unexpected data size");
          const dv = new DataView(buf), data = new Float32Array(nx * ny);
          for (let k = 0; k < data.length; k++) data[k] = dv.getFloat32(4 * k, true); // little-endian
          return { kind: "data", data };
        });
    } else p = loadImage(frame.image_url, base).then((img) => ({ kind: "image", img }));
    p.catch(() => frameCache.delete(key));     // si falla, se puede reintentar
    frameCache.set(key, p);
  }
  return frameCache.get(key);
}
```

**Datos simulados** (`src/lib/mock.js`), para trabajar mientras no estén los estáticos reales. Contiene a propósito cada caso que el flipbook tiene que manejar: 3 fechas, un objeto frío que se mueve ~2.2 px al oeste (casi invisible en D1–D3), una variable quieta, la fecha 2 sin D4 y la fecha 2 en D1 con dos columnas sin dato. No es astronomía real: con `VITE_USE_MOCKS=0` deja de usarse.

```js
import { pixelToSky } from "./coords";

export const MOCK_DATA = new Map();
const LAMBDA = [[0.75, 1.09], [1.10, 1.62], [1.63, 2.41], [2.42, 3.82], [3.83, 4.41], [4.42, 5.00]];

function addGauss(arr, n, x0, y0, amp, sigma = 0.6) {
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++)
      arr[y * n + x] += amp * Math.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * sigma * sigma));
}

export function mockManifest(center, targetId = null) {
  const n = 31, c = 15, p = 6.2;
  const coldPeak = [0.01, 0.015, 0.02, 0.15, 0.6, 0.5];        // brillo del objeto frío por detector
  const dates = [["e1", "2025-05-25", 60820.5], ["e2", "2025-11-26", 61005.5], ["e3", "2026-05-30", 61190.5]];
  const fieldId = `mock_${center.ra.toFixed(4)}_${center.dec.toFixed(4)}`;
  const epochs = dates.map(([epoch_id, date_iso, mjd_avg], k) => {
    const mx = c - 1.1 + 1.1 * k;                              // se mueve hacia la derecha (oeste)
    const frames = [1, 2, 3, 4, 5, 6].filter((d) => !(k === 1 && d === 4)).map((d) => {
      const arr = new Float32Array(n * n).map(() => 0.02 * Math.random());
      addGauss(arr, n, mx, c, coldPeak[d - 1]);
      addGauss(arr, n, 6, 22, 0.5 * [1, 1.8, 0.6][k]);         // variable quieta
      addGauss(arr, n, 24, 7, 0.8);                            // estrella fija
      if (k === 1 && d === 1) for (let y = 0; y < n; y++) { arr[y * n] = NaN; arr[y * n + 1] = NaN; }
      const url = `mock://${fieldId}/${epoch_id}_d${d}`;
      MOCK_DATA.set(url, arr);
      return { detector: d, image_url: url, data_url: url, flags_url: null, n_exposures: 3, flagged_frac: 0.01 };
    });
    const expected_position = targetId ? { ...pixelToSky(mx, c, center, n, n, p), x: mx, y: c } : null;
    return { epoch_id, mjd_avg, date_iso, frames, expected_position };
  });
  return {
    field_id: fieldId, target_id: targetId, center, fov_arcmin: 3, pixscale_arcsec: p, nx: n, ny: n,
    orientation: "north_up_east_left", data_release: "MOCK", pipeline_commit: "mock", flux_unit: "arb",
    detectors: LAMBDA.map(([lo, hi], i) => ({ detector: i + 1, lambda_min_um: lo, lambda_max_um: hi,
      stretch: { type: "asinh", vmin: 0, vmax: 0.8 } })),
    epochs,
  };
}
```

**Comprobar:** en la consola del navegador, `useStore.getState().selectTarget("wise0855")` y luego `useStore.getState().manifest.epochs.length` → `3`.

### 5.3 Coordenadas

`src/lib/coords.js`: entiende lo que escribe el usuario, mide distancias en el cielo y convierte píxel ↔ RA/Dec con la convención de 4.1.

```js
const DEG = Math.PI / 180;
const valid = (ra, dec) => Number.isFinite(ra) && Number.isFinite(dec) && ra >= 0 && ra < 360 && dec >= -90 && dec <= 90;

// "133.7587 -7.2416", "08h55m10.8s -07d14m42s", "08:55:10.8 -07:14:42", "08 55 10.8 -07 14 42". null si no entiende.
export function parseCoords(input) {
  const s = input.trim().replace(/,/g, " ").replace(/\s+/g, " ");
  if (!s) return null;
  const two = s.match(/^([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)$/);
  if (two) {
    const ra = parseFloat(two[1]), dec = parseFloat(two[2]);
    return valid(ra, dec) ? { ra, dec } : null;
  }
  const t = s.toLowerCase().replace(/[hdm:'"°′″]/g, " ").replace(/s(?=\s|$)/g, " ").replace(/\s+/g, " ").trim();
  const parts = t.split(" ");
  if (parts.length !== 6) return null;
  const n = parts.map(Number);
  if (n.some((v) => !Number.isFinite(v))) return null;
  const ra = 15 * (Math.abs(n[0]) + n[1] / 60 + n[2] / 3600);
  const sign = parts[3].startsWith("-") ? -1 : 1;               // conserva el signo de "-00 30 00"
  const dec = sign * (Math.abs(n[3]) + n[4] / 60 + n[5] / 3600);
  return valid(ra, dec) ? { ra, dec } : null;
}

// Separación angular en minutos de arco
export function separationArcmin(a, b) {
  const d1 = a.dec * DEG, d2 = b.dec * DEG, dRa = (b.ra - a.ra) * DEG;
  const h = Math.sin((d2 - d1) / 2) ** 2 + Math.cos(d1) * Math.cos(d2) * Math.sin(dRa / 2) ** 2;
  return (2 * Math.asin(Math.min(1, Math.sqrt(h)))) / DEG * 60;
}

// Píxel del recorte -> cielo. x columna, y fila, base 0, enteros en el centro del píxel; fila 0 norte, columna 0 este
export function pixelToSky(x, y, center, nx, ny, pixscaleArcsec) {
  const x0 = (nx - 1) / 2, y0 = (ny - 1) / 2;
  const dec = center.dec - ((y - y0) * pixscaleArcsec) / 3600;
  const ra = center.ra - ((x - x0) * pixscaleArcsec) / 3600 / Math.cos(center.dec * DEG);
  return { ra: (ra + 360) % 360, dec };
}
```

**Comprobar** (valores verificados):
- `parseCoords("08h55m10.831s -07d14m42.53s")` → `{ra: 133.79513, dec: -7.24515}` (redondeado); igual con `08:55:10.831 -07:14:42.53` y `08 55 10.831 -07 14 42.53`.
- `parseCoords("00 00 00 -00 30 00").dec` → `-0.5`.
- `parseCoords("hola")` y `parseCoords("400 10")` → `null`.
- `separationArcmin({ra:133.79513, dec:-7.24515}, {ra:133.7587, dec:-7.2416})` → ~2.2.

### 5.4 Escala de brillo y resta

`src/lib/stretch.js`:
- `stretchToRGBA`: grises con la escala **fija** del detector (`vmin`, `vmax` del manifiesto) y curva asinh. NaN → morado oscuro.
- `differenceToRGBA`: B − A en gris centrado. 0 = gris medio; más brillante en B = blanco; más brillante en A = negro. El límite es el percentil 99 de |B − A|, para que un punto muy brillante no aplaste el resto.

```js
const NAN_RGBA = [58, 42, 74, 255];   // "sin dato": distinto del negro del cielo

export function stretchToRGBA(data, nx, ny, st) {
  const out = new Uint8ClampedArray(nx * ny * 4);
  const span = st.vmax - st.vmin || 1, beta = 0.1, norm = Math.asinh(1 / beta);
  for (let k = 0; k < nx * ny; k++) {
    const v = data[k], o = k * 4;
    if (!Number.isFinite(v)) { out.set(NAN_RGBA, o); continue; }
    const t = Math.min(1, Math.max(0, (v - st.vmin) / span));
    const c = Math.round(255 * (st.type === "asinh" ? Math.asinh(t / beta) / norm : t));
    out[o] = c; out[o + 1] = c; out[o + 2] = c; out[o + 3] = 255;
  }
  return out;
}

export function differenceToRGBA(a, b, nx, ny) {
  const n = nx * ny, d = new Float32Array(n), abs = [];
  for (let k = 0; k < n; k++) { d[k] = b[k] - a[k]; if (Number.isFinite(d[k])) abs.push(Math.abs(d[k])); }
  abs.sort((p, q) => p - q);
  const limit = Math.max(abs.length ? abs[Math.floor(0.99 * (abs.length - 1))] : 0, 1e-6);
  const out = new Uint8ClampedArray(n * 4);
  for (let k = 0; k < n; k++) {
    const o = k * 4;
    if (!Number.isFinite(d[k])) { out.set(NAN_RGBA, o); continue; }
    const c = Math.round(127.5 + 127.5 * Math.min(1, Math.max(-1, d[k] / limit)));
    out[o] = c; out[o + 1] = c; out[o + 2] = c; out[o + 3] = 255;
  }
  return out;
}
```

### 5.5 Cambiar la imagen actual por un canvas nítido

Si el frontend muestra las imágenes con `<img>` o con `background-image`, se reemplaza por un `<canvas>`. Con `<img>` y CSS no se controla que cada píxel SPHEREx sea un bloque exacto ni se pueden dibujar la resta, la retícula y los flags.

Reglas:
1. **Escala entera en píxeles del dispositivo:** `s = floor(anchoDisponible · devicePixelRatio / nx)`. El canvas mide `nx·s × ny·s` píxeles reales y se muestra a ese tamaño dividido por `devicePixelRatio`. Con escala no entera aparecen bordes borrosos (por ejemplo, con el zoom de Windows al 125 %).
2. `imageSmoothingEnabled = false` en el contexto y `image-rendering: pixelated` en CSS.
3. Orden de dibujo: imagen base → flags (55 % de opacidad) → recorrido → retícula → brújula y barra de 30″.

`src/lib/draw.js` (funciones puras, se llaman desde el componente):

```js
export function setupCanvas(canvas, cssWidth, nx, ny) {
  const dpr = window.devicePixelRatio || 1;
  const s = Math.max(1, Math.floor((cssWidth * dpr) / nx));
  canvas.width = nx * s;
  canvas.height = ny * s;
  canvas.style.width = `${(nx * s) / dpr}px`;
  canvas.style.height = `${(ny * s) / dpr}px`;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  return { ctx, s, dpr };
}

// Pinta un arreglo RGBA de nx×ny agrandado ×s sin suavizar
export function drawRGBA(ctx, rgba, nx, ny, s) {
  const off = document.createElement("canvas");
  off.width = nx; off.height = ny;
  const octx = off.getContext("2d");
  const img = octx.createImageData(nx, ny);
  img.data.set(rgba);
  octx.putImageData(img, 0, 0);
  ctx.drawImage(off, 0, 0, nx * s, ny * s);
}

const P = (x, y, s) => [(x + 0.5) * s, (y + 0.5) * s];   // centro del píxel (x, y) en el canvas

export function drawTrack(ctx, positions, s, dpr) {
  const pts = positions.filter(Boolean).map((p) => P(p.x, p.y, s));
  if (pts.length < 2) return;
  ctx.strokeStyle = "rgba(0,229,255,0.55)";
  ctx.lineWidth = Math.max(1, Math.round(1.5 * dpr));
  ctx.beginPath();
  pts.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.stroke();
  ctx.fillStyle = "rgba(0,229,255,0.8)";
  for (const [x, y] of pts) { ctx.beginPath(); ctx.arc(x, y, Math.max(2 * dpr, 0.12 * s), 0, 2 * Math.PI); ctx.fill(); }
}

// Retícula con hueco central (no tapa la fuente), borde negro y trazo cian
export function drawReticle(ctx, pos, s, dpr) {
  const [cx, cy] = P(pos.x, pos.y, s), r1 = 1.6 * s, r2 = 3.2 * s, lw = Math.max(1, Math.round(1.5 * dpr));
  const segs = [[cx - r2, cy, cx - r1, cy], [cx + r1, cy, cx + r2, cy], [cx, cy - r2, cx, cy - r1], [cx, cy + r1, cx, cy + r2]];
  for (const [color, width] of [["#000", lw + 2], ["#00e5ff", lw]]) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.beginPath();
    for (const [x1, y1, x2, y2] of segs) { ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); }
    ctx.stroke();
  }
}

// Brújula (N arriba, E a la izquierda) y barra de 30″
export function drawCompassAndScale(ctx, canvas, pixscaleArcsec, s, dpr) {
  const lw = Math.max(1, Math.round(1.5 * dpr)), L = 22 * dpr, ox = 12 * dpr + L, oy = canvas.height - 12 * dpr;
  ctx.strokeStyle = "#fff"; ctx.fillStyle = "#fff"; ctx.lineWidth = lw;
  ctx.font = `${11 * dpr}px system-ui, sans-serif`;
  ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox, oy - L); ctx.moveTo(ox, oy); ctx.lineTo(ox - L, oy); ctx.stroke();
  ctx.fillText("N", ox - 4 * dpr, oy - L - 4 * dpr);
  ctx.fillText("E", ox - L - 12 * dpr, oy + 4 * dpr);
  const len = (30 / pixscaleArcsec) * s, bx = canvas.width - 12 * dpr - len, by = canvas.height - 14 * dpr;
  ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + len, by); ctx.stroke();
  ctx.fillText("30″", bx + len / 2 - 9 * dpr, by - 5 * dpr);
}
```

Dentro del componente que hoy muestra la imagen (en la guía del visor se llama `FrameCanvas`), el dibujo queda así. `cssWidth` es el ancho del contenedor, medido con un `ResizeObserver`:

```jsx
useEffect(() => {
  const m = manifest, canvas = canvasRef.current;
  if (!m || !canvas || cssWidth <= 0) return;
  let cancelled = false;
  (async () => {
    const { ctx, s, dpr } = setupCanvas(canvas, cssWidth, m.nx, m.ny);
    let msg = null;
    if (diff) {
      const fa = frameFor(m, pairA, detector), fb = frameFor(m, pairB, detector);
      if (!fa || !fb) msg = `No D${detector} data for one of the two dates.`;
      else {
        const [a, b] = await Promise.all([loadFrame(fa, base, m.nx, m.ny), loadFrame(fb, base, m.nx, m.ny)]);
        if (cancelled) return;
        if (a.kind !== "data" || b.kind !== "data") msg = "Difference needs raw data (data_url) for both dates.";
        else drawRGBA(ctx, differenceToRGBA(a.data, b.data, m.nx, m.ny), m.nx, m.ny, s);
      }
    } else {
      const frame = frameFor(m, epochIndex, detector);
      if (!frame) msg = `No D${detector} data for this date.`;
      else {
        const f = await loadFrame(frame, base, m.nx, m.ny);
        if (cancelled) return;
        if (f.kind === "data") drawRGBA(ctx, stretchToRGBA(f.data, m.nx, m.ny, detectorInfo(m, detector).stretch), m.nx, m.ny, s);
        else ctx.drawImage(f.img, 0, 0, m.nx * s, m.ny * s);
        if (layers.flags && frame.flags_url) {
          const fl = await loadImage(frame.flags_url, base);
          if (cancelled) return;
          ctx.globalAlpha = 0.55; ctx.drawImage(fl, 0, 0, m.nx * s, m.ny * s); ctx.globalAlpha = 1;
        }
      }
    }
    setMessage(msg);
    const positions = m.epochs.map((e) => e.expected_position);
    if (layers.track) drawTrack(ctx, positions, s, dpr);
    const cur = diff ? positions[pairB] : positions[epochIndex];
    if (cur) drawReticle(ctx, cur, s, dpr);
    if (!compact) drawCompassAndScale(ctx, canvas, m.pixscale_arcsec, s, dpr);
  })().catch(() => !cancelled && setMessage("Could not load this image."));
  return () => { cancelled = true; };
}, [manifest, base, detector, epochIndex, diff, pairA, pairB, layers.flags, layers.track, cssWidth, compact]);
```

CSS del canvas:

```css
.frame-wrap { position: relative; width: 100%; }
.frame-wrap canvas { display: block; image-rendering: pixelated; }
```

**Lectura del puntero** (para mostrar píxel, RA/Dec y valor, y para marcar candidatos): en `onMouseMove`, `fx = (clientX − rect.left) / rect.width · nx`, `x = fx − 0.5` (igual para `y`), y `pixelToSky(x, y, manifest.center, nx, ny, pixscale_arcsec)`.

**Comprobar:** con los mocks y WISE 0855 en D6, se ve un punto en el centro con la retícula alrededor sin taparlo, la brújula abajo a la izquierda y la barra abajo a la derecha. Con el zoom del navegador al 125 %, los píxeles siguen siendo cuadrados nítidos.

### 5.6 Animación: precarga y reloj

Antes de animar se descargan todos los cuadros que va a mostrar la animación; si no, el primer ciclo se ve a saltos. En el componente del panel:

```jsx
const [ready, setReady] = useState(false);
const [progress, setProgress] = useState({ done: 0, total: 0 });
const isGrid = mode === "grid";

useEffect(() => {
  if (!manifest) return;
  let cancelled = false, done = 0;
  const dets = isGrid ? [1, 2, 3, 4, 5, 6] : [detector];
  const frames = manifest.epochs.flatMap((e) => e.frames.filter((f) => dets.includes(f.detector)));
  setReady(false);
  setProgress({ done: 0, total: frames.length });
  Promise.allSettled(frames.map((f) =>
    loadFrame(f, base, manifest.nx, manifest.ny).finally(() => { if (!cancelled) setProgress({ done: ++done, total: frames.length }); })
  )).then(() => { if (!cancelled) setReady(true); });
  return () => { cancelled = true; };
}, [manifest, base, detector, isGrid]);
```

Reloj (`src/hooks/useFlipbookPlayer.js`, se llama en el panel con `useFlipbookPlayer(ready)`):
- **Flipbook y vista de 6:** un cuadro cada `1/fps` s, solo por las fechas que tienen cuadro. El **último cuadro dura el doble**, para que se note dónde reinicia el ciclo.
- **Blink:** alterna A y B cada 500 ms (2 Hz), sin depender de Play.

```js
import { useEffect } from "react";
import { useStore } from "../store";
import { availableEpochs } from "../lib/manifest";

export function useFlipbookPlayer(ready) {
  const { manifest, detector, epochIndex, playing, fps, mode, pairA, pairB } = useStore();

  useEffect(() => {
    if (!manifest || mode !== "blink" || !ready) return;
    const id = setInterval(() => {
      const s = useStore.getState();
      s.setEpoch(s.epochIndex === pairA ? pairB : pairA);
    }, 500);
    return () => clearInterval(id);
  }, [manifest, mode, pairA, pairB, ready]);

  useEffect(() => {
    if (!manifest || !playing || !ready || (mode !== "flip" && mode !== "grid")) return;
    const avail = availableEpochs(manifest, mode === "grid" ? null : detector);
    if (avail.length < 2) return;
    const pos = avail.indexOf(epochIndex);
    const delay = ((pos === avail.length - 1 ? 2 : 1) * 1000) / fps;
    const t = setTimeout(() => useStore.getState().setEpoch(avail[(pos + 1) % avail.length]), delay);
    return () => clearTimeout(t);
  }, [manifest, detector, epochIndex, playing, fps, mode, ready]);
}
```

Mientras precarga, el panel muestra `Loading frames 2/3…` y Play queda desactivado.

**Comprobar:** Play recorre 2025-05-25 → 2025-11-26 → 2026-05-30 y vuelve al inicio, deteniéndose un poco más en la última fecha.

### 5.7 Controles y etiqueta

Los controles que ya existan se conectan a estas acciones; los que falten, se agregan.

| Control | Acción | Desactivado cuando |
|---|---|---|
| ◀ / ▶ | `setEpoch` a la fecha disponible anterior o siguiente | modo blink o diff |
| Play / Pause | `togglePlay` | modo blink o diff; menos de 2 fechas; precarga sin terminar |
| Deslizador de fecha | ver fragmento abajo | modo blink o diff; menos de 2 fechas |
| Speed (0.5, 1, 2, 4, 8) | `setFps` | — |
| Botones con las fechas | `setEpoch(i)` | — |
| Blink | `setMode(mode === "blink" ? "flip" : "blink")` | menos de 2 fechas |
| Difference | `setMode(mode === "diff" ? "flip" : "diff")` | menos de 2 fechas |
| A / B (selects de fecha) | `setPair(a, b)` | — |
| Flags, Expected track | `toggleLayer("flags")`, `toggleLayer("track")` | — |

El deslizador recorre **posiciones dentro de las fechas disponibles**, no índices de `manifest.epochs` (si la fecha 2 no tiene D4, en D4 el deslizador tiene 2 posiciones):

```jsx
const avail = availableEpochs(manifest, mode === "grid" ? null : detector);
const pos = Math.max(0, avail.indexOf(epochIndex));
<input type="range" min={0} max={Math.max(0, avail.length - 1)} value={pos}
       disabled={mode === "blink" || mode === "diff" || avail.length < 2}
       onChange={(e) => setEpoch(avail[Number(e.target.value)])} />
```

Si hay una sola fecha: `Only one date is available here, so motion can't be shown. Try the 6-detector view or another field.`

Etiqueta bajo el canvas:
- normal: `{date_iso} · MJD {mjd_avg} · D{n} ({λmin}–{λmax} µm) · date {i}/{N} · {n_exposures} exposures · {round(flagged_frac·100)}% flagged`, donde `i` y `N` cuentan las fechas disponibles del detector;
- blink: se agrega `· blinking A {fecha A} ↔ B {fecha B}`;
- resta: `Difference B − A · D{n} · B {fecha B} − A {fecha A} · white = brighter in B, black = brighter in A`.

Pie del panel: `{data_release} · pipeline {pipeline_commit} · center {RA Dec} · {nx}×{ny} px`.

### 5.8 Selector de detector y vista de 6

- Botones **D1–D6**: `setDetector(n)`. Desactivado si ese detector no tiene ningún cuadro en el campo. El rango λ va en el tooltip (`title`).
- Botón **All 6**: `setMode("grid")`.
- Vista de 6: seis canvas compactos (`compact`: sin brújula ni barra) de la misma fecha, en una grilla de 3 × 2. Cada uno usa la escala de **su propio** detector. Play anima los seis juntos porque comparten `epochIndex`. Clic en un panel → `setDetector(n)` y `setMode("flip")`. Si la fecha no tiene ese detector, el panel muestra `No D4 data for this date.`

**Comprobar:** con los mocks, el objeto del centro casi no se ve en D1–D3 y se ve claro en D5–D6; en la fecha 2, el panel D4 muestra el aviso.

### 5.9 Blink y resta

Ya están cubiertos por el estado (`mode`, `pairA`, `pairB`), el reloj (5.6) y el dibujo (`diff` en 5.5). Lo que hay que respetar:

- Por defecto A = primera fecha disponible y B = última.
- **Blink:** alterna A y B a 2 Hz. Un objeto que se mueve "salta"; una variable "parpadea" en su sitio.
- **Difference:** B − A del detector actual. Un objeto que se movió deja un par negro (dónde estaba) y blanco (dónde está). Una variable deja un solo punto. Las estrellas fijas desaparecen.
- La resta necesita `data_url` en las dos fechas; si solo hay PNG, el canvas muestra `Difference needs raw data (data_url) for both dates.`
- Con blink o resta activos, Play y el deslizador quedan desactivados.

### 5.10 Búsqueda y aviso de objetos que se mueven

Orden al pulsar `Go`:
1. Si el texto es el nombre de un objetivo (`findTargetByName`) → `selectTarget(id)`.
2. Si son coordenadas (`parseCoords`) → `openField({ ra, dec })`.
3. Si son coordenadas a menos de 8′ (y más de 0.2′) de un objetivo que se mueve, se muestra un aviso con botón. Es lo que pasa si alguien pega la coordenada del enunciado de WISE 0855.
4. Si no se entiende: `Not recognized. Enter RA Dec (e.g. 133.7587 -7.2416 or 08h55m10.8s -07d14m42s) or a test target name.`

```js
import { TARGETS } from "../targets";
import { separationArcmin } from "./coords";

export function nearMovingTarget(p) {
  for (const t of TARGETS.filter((x) => x.motion_arcsec_yr > 1)) {
    const sep = separationArcmin(p, t.approx_center);
    if (sep > 0.2 && sep < 8) return { target: t, sep };
  }
  return null;
}
// Texto: `This position is ${sep.toFixed(1)}′ from ${t.name}, which moves ${t.motion_arcsec_yr}″/yr;
//         catalog or challenge coordinates can be years old.`  Botón: `Open ${t.short} at its current position`
```

### 5.11 URL compartible y `/embed`

`src/hooks/useUrlSync.js`, llamado una vez en `App`:
1. Al abrir: lee la URL y carga el campo (`target` tiene prioridad sobre `ra`/`dec`).
2. Cuando el campo está listo: aplica `det`, `a`, `b`, `t`, `fps` y `mode`, una sola vez.
3. Cada cambio de estado se escribe en la URL con `history.replaceState` (no llena el historial).

| Parámetro | Ejemplo | Significado |
|---|---|---|
| `target` | `wise0855` | Uno de los 5 objetivos (opcional) |
| `ra`, `dec` | `133.75870`, `-7.24160` | Centro en grados, 5 decimales |
| `fov` | `3` | Minutos de arco |
| `det` | `6` | Detector 1–6 |
| `t` | `e2` | Fecha actual (`epoch_id`) |
| `mode` | `flip`, `blink`, `diff`, `grid` | Vista |
| `a`, `b` | `e1`, `e3` | Fechas del blink y de la resta |
| `fps` | `2` | Velocidad |

```js
import { useEffect, useRef } from "react";
import { useStore } from "../store";

const MODES = ["flip", "blink", "diff", "grid"];

export function useUrlSync() {
  const pending = useRef(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    pending.current = q;
    const s = useStore.getState();
    const fov = Number(q.get("fov")) || undefined;
    const ra = parseFloat(q.get("ra") ?? ""), dec = parseFloat(q.get("dec") ?? "");
    if (q.get("target")) s.selectTarget(q.get("target"), fov);
    else if (Number.isFinite(ra) && Number.isFinite(dec)) s.openField({ ra, dec, fov });
  }, []);

  useEffect(() => useStore.subscribe((s) => {
    const q = pending.current;
    if (!q || s.status !== "ready" || !s.manifest) return;
    pending.current = null;
    const idx = (id) => (id ? s.manifest.epochs.findIndex((e) => e.epoch_id === id) : -1);
    const det = Number(q.get("det"));
    if (det >= 1 && det <= 6) s.setDetector(det);
    const a = idx(q.get("a")), b = idx(q.get("b"));
    if (a >= 0 && b >= 0) s.setPair(a, b);
    const t = idx(q.get("t"));
    if (t >= 0) s.setEpoch(t);
    if (Number(q.get("fps"))) s.setFps(Number(q.get("fps")));
    if (MODES.includes(q.get("mode"))) s.setMode(q.get("mode"));
  }), []);

  useEffect(() => {
    let timer;
    return useStore.subscribe((s) => {
      if (s.status !== "ready" || !s.manifest) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        const e = s.manifest.epochs, q = new URLSearchParams();
        if (s.targetId) q.set("target", s.targetId);
        q.set("ra", s.manifest.center.ra.toFixed(5));
        q.set("dec", s.manifest.center.dec.toFixed(5));
        q.set("fov", String(s.fov));
        q.set("det", String(s.detector));
        q.set("t", e[s.epochIndex]?.epoch_id ?? "");
        q.set("mode", s.mode);
        q.set("a", e[s.pairA]?.epoch_id ?? "");
        q.set("b", e[s.pairB]?.epoch_id ?? "");
        q.set("fps", String(s.fps));
        window.history.replaceState(null, "", `${window.location.pathname}?${q}`);
      }, 200);
    });
  }, []);
}
```

**`/embed`:** en `App.jsx`, si `window.location.pathname.startsWith("/embed")`, se muestra solo el panel del flipbook y un enlace `Open in the full tool` a `"/" + window.location.search`. Necesita el `vercel.json` de 0.1.

**Comprobar:** copiar la URL en otra pestaña reproduce la misma vista. `/embed?target=rdra&det=3&mode=grid` muestra solo la vista de 6 de R Draconis. En Vercel, `/embed` funciona abierto directamente, no solo navegando desde `/`.

### 5.12 Atajos de teclado

Espacio play/pausa · ←/→ fecha anterior/siguiente · B blink · D resta · G vista de 6 · F flags · 1–6 detector · +/− velocidad · Esc vuelve al flipbook. No actúan si el foco está en un `input`, `select` o `textarea`.

### 5.13 FOV, carga y errores

- **FOV:** selector 2′, 3′, 5′ → `setFov`. Para los 5 objetivos, 3′ sale del estático y el resto de la API.
- **Cargando:** `Loading SPHEREx images…`. Si `slowServer` es `true` (3 s): `Waking up server (free hosting can take up to a minute).` El resto de la página sigue usable.
- **Error:** mensaje según `error.code` y botón `Retry`. `no_coverage` → `No SPHEREx images cover this position yet.`
- **Fecha sin el detector elegido:** `No D3 data for this date.` dentro del canvas.

### 5.14 Pasar de datos simulados a datos reales

1. Copiar los estáticos de los 5 objetivos que entrega Brian en `public/static/fields/<target_id>/`.
2. `.env.development`: `VITE_USE_MOCKS=0` y `VITE_API_BASE` con la URL de Render (o `http://localhost:8000`).
3. Probar los 5 objetivos (sección 6) y una coordenada libre.
4. Si las imágenes vienen de Render y no cargan, falta CORS en el backend (avisar a Brian).
5. Las mismas variables en Vercel.

No se tocan componentes: solo cambia de dónde salen los manifiestos.

### 5.15 Conexión con el resto de la herramienta

| Pieza | Cómo se conecta al flipbook |
|---|---|
| Tabla de clasificación | Al seleccionar una fuente: `selectSource(id)`, marcador en el canvas en su `x`, `y` (forma y color por clase) y `setMode("blink")` con primera y última fecha |
| Agente (`ActionRunner`) | `goto` → `openField` · `select_target` → `selectTarget` · `set_fov` → `setFov` · `set_detector` → `setDetector` · `show_detector_grid` → `setMode("grid")` · `set_epoch` → `setEpochById` · `play_flipbook` → `setFps` + `play` · `pause` → `pause` · `blink` → `setPair` + `setMode("blink")` · `show_difference` → `setPair` + `setMode("diff")` · `toggle_layer` → `toggleLayer` |
| Vista del cielo (Aladin) | Usa `manifest.center` y `fov` del mismo estado. Las imágenes por época se dibujan en el canvas del flipbook, no como capa de Aladin |
| Marcar candidato | Clic en el canvas → RA/Dec con `pixelToSky` → `POST /api/marks` con `field_id` y la `mjd_avg` de la fecha actual |

---

## 6. Pruebas con los 5 objetivos (datos reales)

| Objetivo | Detector | Qué debe verse | Si no se ve |
|---|---|---|---|
| WISE 0855 | D6 (y D5) | Punto que avanza ~2 px hacia la derecha (oeste) entre la primera y la última fecha; casi invisible en D1–D3 en la vista de 6 | Revisar que el centro venga del manifiesto y no de la coordenada del enunciado; revisar `expected_position` |
| Barnard's Star | D2 (visible en todos) | Avance de ~2–3 px hacia arriba (norte) entre la primera y la última fecha | Es muy brillante: activar flags (saturación) y avisar a Brian si el núcleo sale vacío |
| Epsilon Indi B | D5 | ~1 px: se nota con blink, apenas con play | Normal: está al límite de lo que resuelve SPHEREx. Se ve como una sola fuente (son dos enanas muy juntas) |
| RW Aurigae | D3 | No se mueve; cambia de brillo entre fechas | Si parece constante, revisar que no se autoescale cada cuadro |
| R Draconis | D3 | No se mueve; cambio de brillo grande; puede tener más fechas que los demás | Muy brillante: flags de saturación |

Para cada objetivo, además: la URL copiada reproduce la vista; la vista de 6 no se rompe si falta un detector; carga con el backend apagado.

---

## 7. Qué no hacer

- Autoescalar cada cuadro por separado.
- Suavizar píxeles o usar escalas no enteras.
- Mezclar detectores en una misma animación.
- Centrar un objetivo en coordenadas escritas a mano o del enunciado.
- Pedir datos a IRSA o S3 desde el navegador: todo pasa por el backend.
- Dejar `VITE_USE_MOCKS=1` en producción.
- Ocultar fuentes con flags.
- Mostrar números que no vengan del manifiesto o de la API.
- Usar la palabra "discovery": en la interfaz, "candidate".

---

## 8. Lo que el backend tiene que cumplir (a confirmar con Brian)

1. Convención de píxel de 4.1.
2. `data_url` en los estáticos de los 5 objetivos (float32 little-endian, `nx·ny·4` bytes; ~4 KB por cuadro de 31 × 31).
3. PNG con alfa 0 en píxeles sin dato; flags en PNG RGBA.
4. Misma escala (`stretch`) para todas las fechas de un detector en un campo.
5. `target_id`: `barnard`, `epsindib`, `wise0855`, `rwaur`, `rdra`.
6. Centro del campo ya propagado a la fecha de los datos.
7. CORS para el dominio de Vercel.
8. Códigos de error `no_coverage`, `fov_too_large`, `upstream_unavailable`.

---

## 9. Textos de la interfaz (inglés)

| Lugar | Texto |
|---|---|
| Búsqueda | `RA Dec or name (e.g. WISE 0855)` · botón `Go` |
| Búsqueda no entendida | `Not recognized. Enter RA Dec (e.g. 133.7587 -7.2416 or 08h55m10.8s -07d14m42s) or a test target name.` |
| Aviso de objeto que se mueve | `This position is {sep}′ from {name}, which moves {pm}″/yr; catalog or challenge coordinates can be years old.` · botón `Open {short} at its current position` |
| Estado inicial | `Enter coordinates or pick a test target.` |
| Cargando | `Loading SPHEREx images…` · a los 3 s: `Waking up server (free hosting can take up to a minute).` |
| Precarga | `Loading frames {done}/{total}…` |
| Sin cobertura | `No SPHEREx images cover this position yet.` · botón `Retry` |
| Una sola fecha | `Only one date is available here, so motion can't be shown. Try the 6-detector view or another field.` |
| Falta detector | `No D{n} data for this date.` |
| Resta sin datos crudos | `Difference needs raw data (data_url) for both dates.` |
| Etiqueta del cuadro | `{date} · MJD {mjd} · D{n} ({λmin}–{λmax} µm) · date {i}/{N} · {k} exposures · {p}% flagged` |
| Etiqueta de la resta | `Difference B − A · D{n} · B {dateB} − A {dateA} · white = brighter in B, black = brighter in A` |
| Controles | `Play` / `Pause`, `Speed`, `Blink`, `Difference`, `A`, `B`, `Flags`, `Expected track`, `All 6` |
| Embed | `Open in the full tool` |
