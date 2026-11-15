# Flipbook SPHEREx: correcciones con los datos reales

Versión: domingo 15 nov 2026, 12:45. Para: Alessandro y la IA que use como asistente.
Complementa la guía "Flipbook SPHEREx: qué pide el reto y qué cambiar en el frontend actual". **Donde esta hoja y esa guía no coincidan, manda esta hoja**: está hecha con los datos reales ya generados, no con supuestos.

---

## 1. Qué ya existe

Los estáticos de los 5 objetivos están listos, con el formato de la sección 4 de la guía: un cuadro por época y detector (coadd), PNG, flags y `data_url`.

```
static_fields/
  barnard/   manifest.json  e1_d1.png  e1_d1.bin  e1_d1_flags.png  …  e3_d6.*
  epsindib/  …  (4 épocas; la e4 no tiene D1 ni D4)
  wise0855/  …
  rwaur/     …
  rdra/      …
```

- 94 cuadros en total, de 31 × 31 px, 6.2″/px (FOV 3.2′). Norte arriba, este a la izquierda, enteros en el centro del píxel, fila 0 = norte (convención 4.1 de la guía).
- Cada `.bin` mide exactamente 3844 bytes (31·31·4, float32 little-endian, NaN sin dato).
- Cada cuadro es la suma ponderada de 3 a 45 exposiciones de esa época y ese detector (`n_exposures`).
- La escala de brillo (`stretch`) es fija por detector y objetivo.

**Paso 5.14 de la guía, versión real:** copiar la carpeta `static_fields/` que entrega Brian como `public/static/fields/` del proyecto. Las URLs del manifiesto ya empiezan con `/static/fields/<target_id>/…`.

---

## 2. Campos del manifiesto real

Iguales a la sección 4 de la guía, con estas diferencias:

| Campo | Valor real | Qué hacer |
|---|---|---|
| `fov_arcmin` | `3.2` (no `3`) | Mostrarlo tal cual. El estado interno puede seguir usando `fov = 3` para elegir el estático |
| `data_release` | `"spherex_dr1+spherex_qr3"` (WISE 0855: `"spherex_dr1"`) | Pie del panel |
| `pipeline_commit` | `"coadd-v1"` | Pie del panel |
| `frames[].lambda_range_um` | `[λmin, λmax]` de las exposiciones sumadas, o `null` | Opcional en la etiqueta del cuadro; si no, usar el rango del detector |
| `name`, `center_ref_mjd`, `image_is`, `flags_overlay` | Informativos | Se pueden ignorar |
| `spectrum_url`, `autotype_url`, `lightcurve_url`, `sources_url`, `catalogs_url` | `null` por ahora | Si es `null`, la pestaña muestra `Not available yet.` y no hace ninguna petición |

---

## 3. Cambios en el código de la guía

### 3.1 `src/targets.js`: centros reales y detector por defecto

Reemplaza la lista de la sección 5.2. Los centros son los que trae cada manifiesto. WISE 0855 pasa a D5 por defecto: en la primera fecha D6 tiene solo 3 exposiciones y se ve muy ruidoso; en D5 el objeto se ve en las tres fechas.

```js
export const TARGETS = [
  { target_id: "barnard",  name: "Barnard's Star",  short: "Barnard",    motion_arcsec_yr: 10.4, default_detector: 2,
    aliases: ["barnard", "barnards star", "barnard's star", "gj 699"], approx_center: { ra: 269.44622, dec: 4.76881 } },
  { target_id: "epsindib", name: "Epsilon Indi B",  short: "Eps Indi B", motion_arcsec_yr: 4.7,  default_detector: 5,
    aliases: ["eps indi b", "epsilon indi b", "eps ind b"], approx_center: { ra: 331.09629, dec: -56.80046 } },
  { target_id: "wise0855", name: "WISE 0855-0714",  short: "WISE 0855",  motion_arcsec_yr: 8.1,  default_detector: 5,
    aliases: ["wise 0855", "wise0855", "wise 0855-0714", "wise j085510.83-071442.5"], approx_center: { ra: 133.75945, dec: -7.24286 } },
  { target_id: "rwaur",    name: "RW Aurigae",      short: "RW Aur",     motion_arcsec_yr: 0,    default_detector: 3,
    aliases: ["rw aur", "rw aurigae"], approx_center: { ra: 76.95609, dec: 30.40113 } },
  { target_id: "rdra",     name: "R Draconis",      short: "R Dra",      motion_arcsec_yr: 0,    default_detector: 3,
    aliases: ["r dra", "r draconis"], approx_center: { ra: 248.16723, dec: 66.75502 } },
];
```

### 3.2 Selector de FOV (5.13)

Solo hay datos de 3.2′. El selector muestra una sola opción, `3′`, o se oculta, hasta que el backend genere otros tamaños. No se ofrecen 2′ ni 5′.

### 3.3 Coordenadas libres

El backend solo tiene los 5 campos. Para cualquier otra coordenada, `GET /api/field` responde `404` con `{"error": {"code": "no_coverage", ...}}`. El frontend ya lo maneja (`No SPHEREx images cover this position yet.`). Debajo del mensaje, agregar los 5 botones de objetivos: `Try a test target:`.

### 3.4 Textos que no se deben afirmar

En la sección 2.1 de la guía, el punto 8 decía que WISE 0855 "casi no se ve en D1–D3". En los datos reales hay una fuente débil cerca de su posición también en D1–D3, sin confirmar si es el mismo objeto. La interfaz **no lleva ese texto**; la vista de 6 detectores muestra lo que hay. Lo mismo vale para cualquier frase astronómica que no venga del manifiesto o de la API.

---

## 4. Qué debe verse con cada objetivo (reemplaza la tabla de la sección 6)

| Objetivo | Fechas | Detector | Qué debe verse | Normal, no es error |
|---|---|---|---|---|
| WISE 0855 | e1 2025-05-06, e2 2025-11-12, e3 2026-05-01 | D5 (también D6) | Punto débil en la retícula que se corre ~1.3 px a la derecha (oeste) de e1 a e3 (x 14.3 → 15.0 → 15.6) | e1 tiene pocas exposiciones (3–8) y se ve con más ruido |
| Barnard's Star | e1 2025-08-29, e2 2026-03-20, e3 2026-08-22 | D2 | Sube ~1.6 px (norte) de e1 a e3 (y 15.9 → 15.0 → 14.3) | El centro de la estrella sale morado (sin dato): está saturado y el archivo original no trae valor ahí |
| Epsilon Indi B | e1 2025-05-09 … e4 2026-09-27 | D5 | Se corre ~1 px a la izquierda y abajo (este y sur) de e1 a e4; se nota con blink | e4 no tiene D1 ni D4: el canvas muestra `No D1 data for this date.` |
| RW Aurigae | e1 2025-09-10, e2 2026-03-03, e3 2026-09-11 | D3 | Quieto en el centro; cambio de brillo entre fechas | — |
| R Draconis | e1 2025-06-20, e2 2025-11-26, e3 2026-06-07 | D3 | Quieto; estrella muy brillante | Centro morado por saturación; ~10 % de píxeles con flags |

Para cada objetivo, además: Play recorre todas las fechas; blink y resta funcionan con `data_url`; la URL copiada reproduce la vista; carga con el backend apagado.

---

## 5. Lo que hace el backend (Brian)

- Sirve los mismos archivos en `/static/fields/<target_id>/…`, para que las URLs del manifiesto funcionen tanto desde Vercel como desde la API.
- `GET /api/targets` devuelve la lista de la sección 3.1 (mismos campos), más `static_manifest_url`.
- `GET /api/field?ra=…&dec=…&fov_arcmin=…`: si la posición está a menos de 1′ del centro de uno de los 5 objetivos, devuelve su manifiesto (sea cual sea el FOV); si no, `404` con `no_coverage`.
- CORS abierto para el dominio de Vercel y `localhost:5173`.
