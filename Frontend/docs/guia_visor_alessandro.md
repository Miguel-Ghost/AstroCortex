# Guía del frontend: visor SPHEREx (Space Apps 2026, reto "Planet X and SPHEREx")

Versión: sábado 14 nov 2026, 13:15. Backend, contratos de datos y pipeline: Brian.

---

## 0. Instrucciones para la IA que use esta guía

- **Rol:** asistente de desarrollo frontend del equipo (lo usa Alessandro).
- **Stack fijo:** React con Vite, desplegado en Vercel. El backend es FastAPI en Render y lo hace Brian. Postgres guarda marcas y votos, y lo maneja el backend.
- **Idioma:** todo el texto visible de la interfaz va en **inglés** (requisito de la entrega). Esta guía está en español.
- **Trabajar contra mocks:** construir todo con datos simulados que respeten exactamente los contratos de la sección 7. Así el frontend no depende del backend ni del modelo. Al conectar la API real solo cambia la URL base (`VITE_API_BASE`).
- **No inventar datos astronómicos:** cada número que aparece en pantalla viene de la API o de los archivos estáticos.
- **Prioridades:** terminar todo lo P0 de la sección 4 antes de empezar P1.
- **Si algo choca:** los contratos de API los decide Brian, y lo que pide el enunciado del reto está por encima de esta guía.

---

## 1. Qué pide el reto

- Una herramienta web pública: se ingresan coordenadas (RA/Dec) y se ve la serie de imágenes SPHEREx de esa zona como un video corto (flipbook), para detectar objetos que **se mueven** o **cambian de brillo**.
- Objetivos de prueba: Barnard's Star, Epsilon Indi B, WISE 0855−0714, RW Aurigae y R Draconis.
- Consideraciones del enunciado:
  - coadd por cada uno de los 6 detectores;
  - sumar y restar fechas;
  - campo de visión (FOV) elegible;
  - capas de Gaia y WISE;
  - coordenadas en la URL (enlace compartible y embebible);
  - mostrar flags de calidad;
  - espectros al vuelo (extra);
  - fácil de actualizar con nuevos releases;
  - menciona Astropy y Aladin (CDS).
- Modelo de interfaz sugerido en los recursos oficiales: WiseView (http://byw.tools/wiseview).

---

## 2. Qué es el producto

Toma la experiencia de NASA Eyes on Asteroids (escena interactiva, clic en un objeto, panel de información, recorridos guiados) y la lleva **al cielo con datos SPHEREx** en vez del sistema solar. Tiene cuatro piezas:

1. **Vista del cielo (contexto):** una esfera del cielo interactiva con Aladin Lite, que se rota y se acerca. Los objetivos y las fuentes clasificadas aparecen como marcadores clicables.
2. **Panel del campo:** flipbook SPHEREx por épocas y detectores, blink, resta, flags, espectro, curva de luz y catálogos.
3. **Motor clasificatorio (pieza central):** clasifica cada fuente del campo y pone primero a los candidatos.
4. **Agente guía:** genera los recorridos (pasos con texto y acciones sobre el visor) y responde preguntas usando solo datos de la API.

**Flujo típico:**
1. El usuario busca una coordenada o un nombre, elige uno de los 5 objetivos, o le pide al agente "Guide me".
2. El visor centra el cielo y carga el campo SPHEREx.
3. El flipbook muestra las épocas, y una retícula marca dónde debería estar el objeto en cada fecha.
4. La tabla de clasificación lista las fuentes del campo, con los candidatos arriba.
5. El usuario selecciona una fuente, revisa la evidencia y vota (Real / Artifact / Not sure).

### Equipo

| Persona | Responsabilidad |
|---|---|
| Brian | Backend (FastAPI, caché, base de datos, despliegue, estáticos), contratos de API, endpoint del agente, supervisión del pipeline de datos |
| Miguel | Preprocesamiento para el modelo (valores faltantes, outliers, balanceo); propone usar una red neuronal |
| Paolo | EDA, feature engineering e importancia de variables |
| Alessandro | Frontend (esta guía) |

---

## 3. Qué cuerpos se analizan

### 3.1 Datos de SPHEREx que condicionan el visor

- **Píxel:** 6.2″ × 6.2″.
- **Seis detectores (bandas)**, cada uno con un rango de longitud de onda:

| Detector | λ (µm) | Qué se ve mejor |
|---|---|---|
| D1 | 0.75–1.09 | estrellas normales |
| D2 | 1.10–1.62 | estrellas normales |
| D3 | 1.63–2.41 | estrellas normales, enanas L |
| D4 | 2.42–3.82 | transición |
| D5 | 3.83–4.41 | enanas marrones frías (máximo cerca de 4 µm) |
| D6 | 4.42–5.00 | enanas marrones frías |

- Los detectores trabajan en pares que miran la misma zona al mismo tiempo (D1–D4, D2–D5, D3–D6).
- **Cadencia:** SPHEREx cubre todo el cielo cada ~6 meses. Cerca de los polos eclípticos hay más visitas. El número de épocas por objetivo **todavía se está contando**, así que el visor no puede asumir un número fijo: puede haber 2–4 épocas o muchas más.
- **Cada imagen trae varias capas:** IMAGE, FLAGS, VARIANCE, ZODI (fondo zodiacal) y PSF. El backend las entrega ya procesadas: IMAGE − ZODI, recortadas y en una grilla común.
- **Consecuencia directa:** en todo el lapso de datos (~1.5 años) los movimientos son de **1 a 3 píxeles**. Esto define las reglas de la sección 6.

### 3.2 Tipos de cuerpos

| Tipo | Ejemplo | Cómo se ve en el visor | Cómo lo identifica el sistema | Etiqueta en la API |
|---|---|---|---|---|
| Estrella fija | la mayoría de fuentes | igual en todas las fechas | no se mueve, está en Gaia | `star` |
| Estrella cercana con gran movimiento propio | Barnard's Star | punto que se desplaza entre la primera y la última fecha; visible en los 6 detectores | movimiento medido + Gaia | `star` con `evidence.motion_px` > 0 |
| Enana marrón fría (tipos T e Y) | Epsilon Indi B, WISE 0855 | se desplaza; débil o ausente en D1–D3 y brillante en D5–D6 | movimiento WISE→SPHEREx, índice de metano alto, ausente o débil en Gaia | `cold_brown_dwarf` |
| Estrella variable | RW Aurigae, R Draconis | no se mueve; cambia de brillo entre fechas | curva de luz (flujo vs fecha) | `star` con `evidence.variable: true` |
| Asteroide o cometa | aparecen en campos cualquiera | aparece en una fecha y no en las demás, o se ve desplazado entre exposiciones cercanas | cruce con JPL Small-Body Identification | `asteroid_comet` |
| Galaxia | campos lejos del plano galáctico | mancha más ancha que una estrella; no se mueve | ancho comparado con la PSF, catálogos | `galaxy` |
| Desconocido | — | ninguna clase con confianza suficiente | probabilidades bajo el umbral | `unknown`, mostrado como "Needs review" |
| Artefacto (no es un cuerpo) | rayos cósmicos, saturación, fantasmas, persistencia | puntos o manchas que no son reales | bits de FLAGS | no se clasifica; se señala con la capa de flags |

**Fuera de alcance:**
- Exoplanetas: el planeta queda a 0.02–0.27 px de su estrella, así que no se puede separar.
- Planeta Nueve: no se promete.
- Tránsitos.

### 3.3 Los 5 objetivos de prueba

| Objetivo | Qué es | Qué debe mostrar el visor | Movimiento en SPHEREx | Notas |
|---|---|---|---|---|
| Barnard's Star | enana roja M4 a ~1.8 pc; el mayor movimiento propio conocido | desplazamiento claro entre fechas | ~10.4″/año ≈ 1.7 px/año (~2.5 px en 1.5 años) | la posición J2000 de catálogos está ~4.5′ desplazada: usar siempre la posición que da la API |
| Epsilon Indi B | par de enanas marrones (T1 + T6) a ~3.6 pc; en SPHEREx se ve como una sola fuente | movimiento + brillo en bandas rojas; espectro con clasificación automática (autotype) | ~4.7″/año ≈ 0.75 px/año (~1.1 px en 1.5 años) | ~2′ desplazada desde J2000 |
| WISE 0855−0714 | enana marrón tipo Y, la más fría conocida; ~2.3 pc | casi invisible en D1–D3, visible en D5–D6; movimiento | ~8.1″/año ≈ 1.3 px/año (~2 px en 1.5 años) | la coordenada del enunciado es de 2010; en 2025–2026 el objeto está ~125–131″ al oeste. **Nunca centrar en la coordenada del enunciado.** No está en Gaia |
| RW Aurigae | estrella joven T Tauri con disco; variable irregular | cambio de brillo entre fechas; curva de luz | despreciable | el autotype no aplica (sus plantillas son de enanas) |
| R Draconis | variable Mira (gigante roja pulsante), periodo ~245 días; a ~9° del polo norte eclíptico, así que probablemente tenga más épocas | cambio de brillo grande; curva de luz | despreciable | muy brillante en infrarrojo: revisar flags de saturación; el autotype no aplica |

Los espectros de los 5 objetivos están precalculados y se sirven como archivos estáticos.

### 3.4 Qué significa "descubrir" en esta herramienta

- La orientación a descubrimiento del equipo busca **candidatos nuevos de enanas marrones frías**: fuentes que se mueven entre WISE (2010–2020) y SPHEREx (2025–2026), tienen índice de metano alto, no aparecen en catálogos y reciben votos de usuarios.
- WISE es necesario para la búsqueda general. Con solo SPHEREx (~1.5 años), casi ninguna enana se mueve 1 px o más; con la línea de base WISE 2010 → SPHEREx 2026, se mueve ~20 % de ellas.
- La interfaz los llama **"candidates"**, nunca "discoveries". El método se valida midiendo qué fracción de enanas conocidas recupera.

---

## 4. Alcance del MVP y prioridades

### P0 (sin esto no hay entrega)

1. Búsqueda por RA/Dec (en grados y sexagesimal) y por nombre, más accesos directos a los 5 objetivos.
2. Estado en la URL: `?ra=…&dec=…&fov=…&det=…&t=…`, para compartir y embeber.
3. Flipbook por épocas: play/pausa, velocidad, slider de fecha y una etiqueta con fecha (ISO y MJD), detector y rango λ.
4. Selector de detector D1–D6 y una **vista de 6 paneles** (los 6 detectores de una época lado a lado).
5. Blink entre dos fechas elegibles (por defecto, la primera contra la última).
6. Retícula en la posición esperada del objetivo en cada fecha, más el trazo de su recorrido.
7. Capa de flags activable.
8. Selector de FOV (p. ej. 2′, 3′, 5′).
9. **Panel de clasificación** con la lista de fuentes del campo. Usa el mock hasta que el motor esté listo.
10. Datos estáticos de los 5 objetivos que funcionan aunque el backend esté caído.

### P1

11. Resta y suma de fechas.
12. Capas de Gaia DR3 y WISE (CatWISE) como marcadores con popup.
13. Espectro (los 5 objetivos, estático) y curva de luz (para las variables).
14. Agente guía con recorridos generados por el agente.
15. Vista del cielo con Aladin Lite.
16. Marcar candidato y votar.

La vista del cielo queda en P1 porque depende de un servicio externo (CDS). El diseño de pantalla de la sección 5 ya le deja su espacio, para que no haya que rehacer el layout cuando entre.

### P2

17. Eyes on Asteroids incrustado (iframe con `?embed=true`) para asteroides identificados por JPL.
18. Vecindario solar en 3D como pantalla de inicio.
19. Espectros al vuelo para cualquier coordenada.

---

## 5. Pantalla y componentes

```
┌────────────────────────────────────────────────────────────────────────────┐
│ TopBar: [Search: name or RA Dec] [Barnard] [Eps Indi B] [WISE 0855]        │
│         [RW Aur] [R Dra]   FOV ▾   [Guide me]                              │
├──────────────────────────────────┬─────────────────────────────────────────┤
│                                  │ FieldPanel  (tabs)                      │
│  SkyView (Aladin Lite)           │ Flipbook | Spectrum | Light curve |     │
│  - objetivos y fuentes por clase │ Catalogs                                │
│  - marcadores Gaia / WISE        │ ┌─────────────┐  [D1][D2][D3]           │
│  (antes de que entre Aladin,     │ │ frame canvas│  [D4][D5][D6]           │
│   esta zona muestra el flipbook  │ │ (pixelado)  │                         │
│   en grande)                     │ └─────────────┘                         │
│                                  │ ◀ ⏯ ▶  date slider  Blink A/B  Diff     │
├──────────────────────────────────┴───────────────────┬─────────────────────┤
│ Classification: tabla de fuentes (clase, confianza,  │ AgentPanel          │
│ evidencia) + detalle de la fuente seleccionada       │ (chat + pasos)      │
└──────────────────────────────────────────────────────┴─────────────────────┘
```

### Componentes

| Componente | Responsabilidad |
|---|---|
| `AppStore` (Zustand o Context) | Estado único: `{ra, dec, fovArcmin, targetId, detector, epochIndex, blink:{a,b,on}, diff:{a,b,on}, layers:{flags,gaia,wise,sources}, selectedSourceId, tour:{steps,index,running}}` |
| `UrlSync` | Mantiene el estado y la query string sincronizados |
| `TopBar`, `SearchBox` | Entiende `133.7587 -7.2416`, `08h55m10.8s -07d14m42s` y nombres |
| `SkyView` | Envoltorio de Aladin Lite (sección 10) |
| `FieldPanel` | Pestañas del campo |
| `FrameCanvas` | Dibuja un cuadro con píxeles nítidos, retícula y flags |
| `DetectorGrid` | Vista de 6 paneles |
| `TimelineControls` | Play, slider, blink, resta |
| `SpectrumChart`, `LightCurveChart` | Gráficos (Recharts o Plotly) |
| `ClassificationTable`, `SourceDetail` | Motor clasificatorio (sección 8) |
| `AgentPanel`, `ActionRunner` | Agente y ejecución de acciones (sección 9) |
| `VoteButtons` | Marcas y votos |

---

## 6. Reglas para mostrar imágenes astronómicas

- **Píxeles nítidos:** `image-rendering: pixelated` (o vecino más cercano en canvas) y escala entera (×8 a ×12). Sin suavizado, porque los movimientos son de 1–3 px.
- **Misma escala de contraste en todas las fechas** de un mismo detector. El backend la fija por campo y detector y la entrega en el manifiesto. Si cada cuadro se autoescala por separado, una estrella variable parece constante y el ruido parece variación.
- Estiramiento asinh o zscale; escala de grises por defecto.
- NaN (borde del detector, sin dato) en un color distinto del negro.
- Retícula de posición esperada con un hueco en el centro, para no tapar la fuente.
- Cada cuadro lleva una etiqueta con fecha, MJD, detector y rango λ.
- Flags como capa semitransparente, con una leyenda por grupo de bits. Las fuentes marcadas como SOURCE u OUTLIER no se ocultan: un objeto que se mueve suele caer en esas marcas.
- Orientación: norte arriba y este a la izquierda (convención astronómica), con un indicador N/E.
- Las clases se distinguen por color **y** forma, no solo por color.

---

## 7. Contratos de datos (propuesta del backend, a confirmar con Brian)

Reglas generales:
- URL base en `VITE_API_BASE`.
- Los 5 objetivos también existen como archivos estáticos en `/static/fields/<target_id>/`, **con el mismo esquema** que la API. Así el frontend tiene una sola ruta de código.
- Errores: `{"error": {"code": "...", "message": "..."}}`.
- Los valores de los ejemplos son ilustrativos.

### 7.1 `GET /api/targets`

```json
[
  {
    "target_id": "wise0855",
    "name": "WISE 0855-0714",
    "kind": "cold_brown_dwarf",
    "behavior": ["moves"],
    "short_description": "Coldest known brown dwarf (Y type), about 2.3 pc away.",
    "static_manifest_url": "/static/fields/wise0855/manifest.json"
  }
]
```

`behavior` puede contener `"moves"`, `"varies"` o ambos.

### 7.2 `GET /api/field?ra=…&dec=…&fov_arcmin=…` (manifiesto del campo)

```json
{
  "field_id": "f_133.7589_-7.2417_3",
  "target_id": "wise0855",
  "center": {"ra": 133.7589, "dec": -7.2417},
  "fov_arcmin": 3.0,
  "pixscale_arcsec": 6.2,
  "nx": 31,
  "ny": 31,
  "orientation": "north_up_east_left",
  "data_release": "spherex_dr1",
  "pipeline_commit": "abc1234",
  "flux_unit": "MJy/sr",
  "detectors": [
    {"detector": 1, "lambda_min_um": 0.75, "lambda_max_um": 1.09, "stretch": {"type": "asinh", "vmin": -0.02, "vmax": 0.8}},
    {"detector": 6, "lambda_min_um": 4.42, "lambda_max_um": 5.00, "stretch": {"type": "asinh", "vmin": -0.05, "vmax": 1.5}}
  ],
  "epochs": [
    {
      "epoch_id": "e1",
      "mjd_avg": 60820.5,
      "date_iso": "2025-05-25",
      "frames": [
        {"detector": 6, "image_url": "/static/fields/wise0855/e1_d6.png", "data_url": null, "flags_url": "/static/fields/wise0855/e1_d6_flags.png", "n_exposures": 4, "flagged_frac": 0.03}
      ],
      "expected_position": {"ra": 133.7600, "dec": -7.2418, "x": 14.4, "y": 15.0}
    },
    {
      "epoch_id": "e2",
      "mjd_avg": 61005.5,
      "date_iso": "2025-11-26",
      "frames": [],
      "expected_position": {"ra": 133.7589, "dec": -7.2417, "x": 15.0, "y": 15.0}
    },
    {
      "epoch_id": "e3",
      "mjd_avg": 61190.5,
      "date_iso": "2026-05-30",
      "frames": [],
      "expected_position": {"ra": 133.7578, "dec": -7.2416, "x": 15.7, "y": 15.0}
    }
  ],
  "spectrum_url": "/static/fields/wise0855/spectrum.csv",
  "autotype_url": "/static/fields/wise0855/autotype.json",
  "lightcurve_url": null,
  "sources_url": "/api/sources?field_id=f_133.7589_-7.2417_3",
  "catalogs_url": "/api/catalogs?field_id=f_133.7589_-7.2417_3"
}
```

Notas:
- `x`, `y` son coordenadas de píxel del recorte. La fila 0 es el norte (arriba) y la columna 0 el este (izquierda).
- `image_url`: PNG ya estirado con la escala fija del detector. Es lo que se usa en P0.
- `data_url` (opcional, P1): binario float32 little-endian de `ny × nx`, por filas, con NaN donde no hay dato. Sirve para hacer la resta y el contraste en el navegador sin pedir nada al servidor. Si no viene, la resta la entrega el backend como PNG.
- Una época puede no tener los 6 detectores. Hay que mostrar el hueco sin romper la vista.

### 7.3 `GET /api/sources?field_id=…` (salida del motor clasificatorio)

```json
{
  "field_id": "f_133.7589_-7.2417_3",
  "method": "model",
  "model_version": "nn-0.3",
  "pipeline_commit": "abc1234",
  "data_release": "spherex_dr1",
  "calibrated": true,
  "classes": ["star", "galaxy", "asteroid_comet", "cold_brown_dwarf", "unknown"],
  "thresholds": {"star": 0.5, "galaxy": 0.5, "asteroid_comet": 0.5, "cold_brown_dwarf": 0.6},
  "sources": [
    {
      "source_id": "s_0012",
      "ra": 133.7589,
      "dec": -7.2417,
      "x": 15.0,
      "y": 15.0,
      "label": "cold_brown_dwarf",
      "class_probs": {"star": 0.05, "galaxy": 0.01, "asteroid_comet": 0.02, "cold_brown_dwarf": 0.88, "unknown": 0.04},
      "evidence": {
        "motion_px": 2.0,
        "pm_mas_yr": {"pmra": -8124, "pmdec": 673},
        "methane_index": 13.2,
        "in_gaia": false,
        "in_catwise": true,
        "jpl_match": null,
        "variable": false,
        "flagged_frac": 0.02
      },
      "obs_ids": ["..."],
      "epoch_mjd": 61005.5
    }
  ]
}
```

- `method` vale `"model"` o `"rule"` (ver 8.4).
- `calibrated: false` significa que las probabilidades no se muestran como porcentaje (ver 8.5).

### 7.4 `GET /api/catalogs?field_id=…&epoch_mjd=…`

```json
{
  "epoch_mjd": 61005.5,
  "gaia": [{"source_id": "123", "ra": 133.75, "dec": -7.24, "g_mag": 15.2, "pmra": -3.1, "pmdec": 1.2}],
  "wise": [{"name": "J085502.13-071444.5", "ra": 133.759, "dec": -7.2417, "w1": 17.4, "w2": 13.9}]
}
```

Las posiciones vienen ya llevadas a `epoch_mjd` por el backend.

### 7.5 Espectro (CSV estático para los 5 objetivos)

```
wavelength_um,flux,flux_err,detector,mjd
3.85,0.0123,0.0011,5,60821.2
```

La unidad de `flux` está en `flux_unit` del manifiesto. `autotype.json` (solo WISE 0855 y Epsilon Indi B) trae el tipo espectral estimado y los parámetros usados.

### 7.6 Curva de luz

```json
[{"mjd": 60820.5, "detector": 3, "lambda_um": 2.1, "flux": 1.23, "flux_err": 0.02}]
```

Se compara siempre el mismo detector entre fechas. En SPHEREx cada exposición cae en otra longitud de onda, así que mezclar detectores en una misma línea no tiene sentido.

### 7.7 Marcas y votos

`POST /api/marks`

```json
{"field_id": "f_...", "source_id": "s_0012", "ra": 133.7589, "dec": -7.2417, "epoch_mjd": 61005.5, "user_label": "real", "comment": "", "client_id": "anon-uuid"}
```

- `user_label` vale `"real"`, `"artifact"` o `"not_sure"`.
- `GET /api/marks?field_id=…` devuelve los votos del campo.

### 7.8 Agente: `POST /api/agent`

Ver sección 9.

---

## 8. Motor clasificatorio (pieza central)

### 8.1 Qué hace

Para cada fuente detectada en el campo, estima la probabilidad de cada clase de la sección 3.2. Después ordena las fuentes para que primero aparezcan los candidatos: enanas frías, y desconocidos que se mueven.

### 8.2 Entradas (las prepara el equipo de datos)

- espectro o colores SPHEREx (flujo por banda o canal);
- movimiento (WISE → SPHEREx);
- ancho de la fuente comparado con la PSF (separa estrellas de galaxias);
- cruce con catálogos (Gaia, CatWISE, JPL), usado como etiquetas de entrenamiento o como variables;
- calidad: fracción de píxeles con flags.

### 8.3 Quién hace qué

- **Miguel:** preprocesamiento (valores faltantes, outliers, balanceo) y propuesta de modelo con red neuronal.
- **Paolo:** EDA, feature engineering e importancia de variables.
- **Brian:** sirve el modelo por la API (`/api/sources`) y guarda cada predicción con la versión del modelo y del pipeline.
- **Alessandro:** lo muestra (8.5).

El tipo de modelo (red neuronal u otro) **no cambia nada en el frontend**: la interfaz solo consume el contrato 7.3.

### 8.4 Respaldo sin entrenamiento

Existe una regla física que no necesita entrenamiento: **índice de metano** = F(3.83–4.41 µm) / F(3.20–3.45 µm), combinado con movimiento.
- Si el modelo no está listo (se decide el domingo a las 12:00), la API devuelve `"method": "rule"` con el mismo formato.
- La interfaz muestra entonces "Rule-based" en lugar de "Model".

Valores de referencia del índice, útiles para el tooltip:
- ~1 de M7 a L6;
- ~2 en T0, ~4 en T3, ~13 en T6, ~56 en T9 y ~115 en Y1;
- los contaminantes conocidos llegan hasta ~3.15.

El umbral final todavía está pendiente.

### 8.5 Cómo mostrarlo

- **Tabla de fuentes.** Columnas: Source, Class, Confidence, Moves (px), Methane idx, Gaia, CatWISE, JPL, Flags %.
  - Orden por defecto: `cold_brown_dwarf` primero, luego `unknown` con movimiento, después el resto.
  - Filtros por clase y "Only moving".
- **Al seleccionar una fila:**
  - se resalta el marcador en el cielo y en el flipbook;
  - el panel de detalle muestra barras de probabilidad por clase;
  - aparecen chips de evidencia ("Moves 2.0 px", "Methane index 13.2", "Not in Gaia", "In CatWISE");
  - aparecen los botones de voto (Real / Artifact / Not sure).
- **`unknown`** se muestra como **"Needs review"**, nunca como descubrimiento.
- **Si `calibrated` es `false`**, se muestra el orden (rank) y no porcentajes.
- **Pie del panel:** `method`, `model_version`, `data_release` y `pipeline_commit`, para que el resultado sea reproducible.
- **El "por qué"** se arma con las variables de evidencia, que vienen de los datos y no del modelo. Si Paolo entrega la importancia global de variables, va en una sección "About the model" con un gráfico de barras, no como explicación de cada fuente.
- Se usa el mismo color y la misma forma por clase en el cielo, el flipbook y la tabla.

### 8.6 Qué no hacer

- Agregar una clase "exoplanet".
- Mostrar como porcentaje una probabilidad que no está calibrada.
- Ocultar fuentes con flags sin avisarlo.
- Llamar "discovery" a un candidato.

---

## 9. Agente guía (los recorridos los genera el agente)

### 9.1 Qué hace

- Recibe una pregunta ("Show me a brown dwarf that moves", "Guide me through WISE 0855", "Which sources here need review?") o el botón "Guide me".
- Genera un recorrido: una lista de pasos, cada uno con un texto corto y las acciones que el visor ejecuta.
- Consulta los endpoints del backend y solo afirma lo que esos datos dicen.

### 9.2 Contrato

Request:

```json
{
  "message": "Guide me through WISE 0855",
  "view_state": {"ra": 133.7589, "dec": -7.2417, "fov_arcmin": 3, "target_id": "wise0855", "detector": 6, "epoch_id": "e1", "selected_source_id": null},
  "history": []
}
```

Response:

```json
{
  "reply": "WISE 0855 is the coldest known brown dwarf. Here is how it looks in SPHEREx.",
  "steps": [
    {"say": "This is WISE 0855 in detector 6 (4.42-5.00 µm).", "actions": [{"type": "select_target", "target_id": "wise0855"}, {"type": "set_detector", "detector": 6}]},
    {"say": "Compare the first and last dates: it moves about 2 pixels to the west.", "actions": [{"type": "blink", "epoch_a": "e1", "epoch_b": "e3"}, {"type": "highlight", "ra": 133.7589, "dec": -7.2417, "label": "WISE 0855"}]},
    {"say": "In the bluer detectors it almost disappears.", "actions": [{"type": "show_detector_grid"}]},
    {"say": "The classifier rates it as a cold brown dwarf.", "actions": [{"type": "select_source", "source_id": "s_0012"}, {"type": "open_tab", "tab": "classification"}]}
  ],
  "sources_used": ["/api/field?ra=133.7589&dec=-7.2417&fov_arcmin=3", "/api/sources?field_id=f_133.7589_-7.2417_3"]
}
```

### 9.3 Vocabulario de acciones (cerrado)

| `type` | Parámetros | Efecto |
|---|---|---|
| `goto` | `ra`, `dec`, `fov_arcmin?` | centra el cielo y carga el campo |
| `select_target` | `target_id` | carga uno de los 5 objetivos |
| `set_fov` | `fov_arcmin` | cambia el campo de visión |
| `set_detector` | `detector` (1–6) | cambia el detector |
| `show_detector_grid` | — | vista de 6 paneles |
| `set_epoch` | `epoch_id` | va a una fecha |
| `play_flipbook` | `fps?` | reproduce |
| `pause` | — | pausa |
| `blink` | `epoch_a`, `epoch_b` | alterna dos fechas |
| `show_difference` | `epoch_a`, `epoch_b` | muestra la resta |
| `toggle_layer` | `layer` (`flags`, `gaia`, `wise`, `sources`), `on` | activa o desactiva una capa |
| `highlight` | `ra`, `dec`, `label` | marcador temporal |
| `select_source` | `source_id` | selecciona una fuente en tabla, cielo y flipbook |
| `open_tab` | `tab` (`flipbook`, `spectrum`, `lightcurve`, `catalogs`, `classification`) | abre una pestaña |
| `ask_vote` | `source_id` | muestra los botones de voto |

### 9.4 Ejecución en el frontend

- `ActionRunner` valida cada acción con un esquema (p. ej. zod). Una acción desconocida o con parámetros inválidos se ignora y queda registrada.
- Controles del recorrido: Next, Back, Auto (avanza cada N segundos) y Stop.
- Si el usuario toca el visor, el recorrido se pausa: el control manual está siempre disponible.
- El panel muestra el historial de acciones ejecutadas, y un detalle plegable con `sources_used`.
- La clave del proveedor de IA vive solo en el backend.

### 9.5 Respaldo para la evaluación

Las respuestas del agente para los 5 objetivos se generan con el propio agente y se guardan como JSON estático. Se usan si la API del agente falla o tarda durante la evaluación.

---

## 10. Vista del cielo con Aladin Lite (Eyes on Asteroids, pero del cielo)

- **Paquete:** npm `aladin-lite` (v3; al 14 nov 2026 la versión publicada es 3.9.2-beta). Necesita WebGL2. Licencia LGPL-3.0-or-later.
- **Inicialización:** se exporta `A` por defecto; `A.init` es una promesa que hay que esperar antes de crear el visor.

Código mínimo en React:

```jsx
import { useEffect, useRef } from "react";
import A from "aladin-lite";

export function SkyView({ ra, dec, fovDeg, onObjectClick }) {
  const divRef = useRef(null);
  const aladinRef = useRef(null);

  // Crear una sola vez (en StrictMode los efectos corren dos veces en desarrollo)
  useEffect(() => {
    let cancelled = false;
    A.init.then(() => {
      if (cancelled || aladinRef.current) return;
      const aladin = A.aladin(divRef.current, {
        survey: "CDS/P/allWISE/color",
        projection: "SIN",
        cooFrame: "equatorial",
        fov: fovDeg,
        target: `${ra} ${dec}`,
        showReticle: false,
      });
      aladin.on("objectClicked", (obj) => { if (obj) onObjectClick?.(obj); });
      aladinRef.current = aladin;
    });
    return () => { cancelled = true; };
  }, []);

  // Seguir el estado global
  useEffect(() => {
    const aladin = aladinRef.current;
    if (!aladin) return;
    aladin.gotoRaDec(ra, dec);
    aladin.setFoV(fovDeg);
  }, [ra, dec, fovDeg]);

  return <div ref={divRef} style={{ width: "100%", height: "100%" }} />;
}
```

- **Fondo:** probar primero el mapa SPHEREx `CDS/P/SPHEREx/QR2/D1`, que distribuye CDS. Si no carga o no se ve bien a la escala de un campo, usar `CDS/P/allWISE/color` o `CDS/P/2MASS/color`, que vienen en la lista por defecto de Aladin. Conviene dar un selector de fondo al usuario. Para cambiar de mapa están `setImageSurvey` y `newImageSurvey` (revisar la documentación de v3).
- **Marcadores:** una capa `A.catalog({...})` por clase, agregada con `addCatalog`. Los puntos se crean con `A.marker(ra, dec, {popupTitle, popupDesc})` o `A.source(ra, dec, data)`.
- **Movimiento suave para la acción `goto` del agente:** `animateToRaDec`.
- **Eventos útiles:** `objectClicked`, `positionChanged` y `zoomChanged`, para sincronizar el estado y la URL.
- **Proyección `"SIN"`** (ortográfica): al alejarse, el cielo se ve como un globo.
- **Reparto de tareas entre vistas:** Aladin da el contexto. Las imágenes SPHEREx por época se dibujan en el canvas propio del flipbook y no como capa de Aladin. Así es más simple y el contraste queda bajo control.
- **Documentación:** https://aladin.cds.unistra.fr/AladinLite/doc/API y https://cds-astro.github.io/aladin-lite/

---

## 11. Datos estáticos y resiliencia

- Los 5 objetivos (manifiesto, PNG, espectro, fuentes clasificadas y respuestas del agente) van como archivos estáticos en Vercel, con el mismo esquema que la API.
- Si la API no responde a tiempo, los 5 objetivos se cargan desde los estáticos. Para coordenadas libres se muestra un error claro.
- El backend gratuito tarda en despertar tras un rato sin uso, así que hace falta un estado de carga visible ("Waking up server…") que no bloquee el resto de la interfaz.

---

## 12. Entrega y fechas

- Interfaz en inglés.
- Demo: video de ≤30 s o ≤7 diapositivas (falta confirmar el formato del pitch local).
- Envío: domingo 15 antes de las 23:59 (meta: 22:00).
- Puntos de control: sábado 14:00 se define el modelo; domingo 12:00 entra el modelo o se usa la regla.
- Capturas útiles para el pitch:
  - WISE 0855 en la vista de 6 detectores (solo aparece en las bandas rojas);
  - el blink mostrando el desplazamiento;
  - la tabla de clasificación con candidatos arriba;
  - un paso de un recorrido del agente.

---

## 13. Orden de trabajo sugerido

1. Proyecto, store, sincronización con la URL y mocks con los contratos de la sección 7, incluidos los 5 objetivos.
   - Para los mocks de imágenes: arreglos o PNG sintéticos de 31×31 con una fuente gaussiana (FWHM ≈ 1 px) que se desplaza ~2 px entre la primera y la última época, y otra fuente que cambia de brillo.
2. `FrameCanvas` y `TimelineControls`: píxeles nítidos, play, slider, detector, vista de 6 paneles, blink y retícula.
3. Accesos a los 5 objetivos con los estáticos.
4. Panel de clasificación: tabla, detalle y votos (con el mock).
5. Capa de flags y selector de FOV.
6. `SkyView` con Aladin, marcadores por clase y capas de Gaia/WISE.
7. `AgentPanel` y `ActionRunner`, con respuestas mock del agente.
8. Conectar la API real a medida que esté lista, pulir y sacar capturas.

---

## 14. Qué no hacer

- Pedir datos a IRSA o a S3 directamente desde el navegador: todo pasa por el backend. Aladin sí carga sus mapas de fondo desde CDS.
- Centrar WISE 0855 en la coordenada del enunciado.
- Autoescalar cada cuadro por separado.
- Suavizar píxeles.
- Inventar números en textos o tooltips.
- Crear la instancia de Aladin de nuevo en cada render.
- Poner claves de API en el frontend.
- Prometer exoplanetas o "descubrimientos".

---

## 15. Glosario

| Término | Significado |
|---|---|
| RA/Dec | coordenadas en el cielo (ascensión recta y declinación), en grados |
| FOV | campo de visión, el ancho de la zona mostrada |
| Época | grupo de observaciones de una misma visita (días); SPHEREx vuelve a cada zona cada ~6 meses |
| Coadd | combinación de varias exposiciones de una época en una sola imagen, una por detector |
| Detector / banda | uno de los 6 sensores de SPHEREx, cada uno con su rango de longitud de onda |
| λ | longitud de onda, en micrómetros (µm) |
| MJD | fecha juliana modificada (días); el backend también entrega la fecha ISO |
| Flags | bits por píxel que marcan problemas (saturación, rayos cósmicos, fantasmas, etc.) |
| ZODI | brillo de fondo del polvo del sistema solar; se resta de la imagen |
| PSF | forma que tiene una fuente puntual en la imagen (~6″ de ancho en SPHEREx) |
| Movimiento propio | desplazamiento aparente de una estrella en el cielo, en mas/año (milisegundos de arco por año) |
| Enana marrón T / Y | objetos entre estrella y planeta; los T e Y son los más fríos y brillan sobre todo cerca de 4–5 µm |
| Índice de metano | cociente de flujo entre 3.83–4.41 µm y 3.20–3.45 µm; alto en enanas T/Y |
| HiPS | formato de mapas del cielo por mosaicos que usa Aladin |
| Gaia DR3 | catálogo de posiciones y movimientos de ~1 800 millones de estrellas (óptico) |
| CatWISE2020 | catálogo infrarrojo de WISE con movimientos propios |
| JPL Small-Body Identification | servicio que dice qué asteroides o cometas hay en una posición y fecha |
| Mira | estrella gigante roja que pulsa y cambia mucho de brillo en meses |
| T Tauri | estrella muy joven, rodeada de un disco, con variaciones irregulares de brillo |

---

## 16. Referencias

- SPHEREx en IRSA: https://irsa.ipac.caltech.edu/Missions/spherex.html
- Instrumento SPHEREx (bandas y píxel): https://spherex.caltech.edu/page/instrument
- Tutoriales SPHEREx de IRSA: https://caltech-ipac.github.io/irsa-tutorials/spherex/
- WiseView (modelo de interfaz sugerido): http://byw.tools/wiseview
- Aladin Lite (API): https://aladin.cds.unistra.fr/AladinLite/doc/API
- Aladin Lite (documentación técnica): https://cds-astro.github.io/aladin-lite/
- NASA Eyes on Asteroids (inspiración de la experiencia): https://eyes.nasa.gov/apps/asteroids/
