# AstroCortex

Migración del HTML entregado el 15 de noviembre de 2026 a **React + Vite + JavaScript + Zustand**. Conserva el CSS completo del original, el logo SVG, los dos haces visibles de la intro, la esfera de partículas, la malla y el layout de paneles. El original sin cambios está en `reference/`.

## Ejecutar

Requiere Node.js 20.19+ o 22.12+.

```bash
npm install
npm run dev
```

Abrir la URL local que imprime Vite. No abrir `index.html` con doble clic: ahora es una aplicación con módulos y carga de archivos científicos por HTTP.

```bash
npm test
npm run verify:data
npm run build
npm run preview
```

## Flipbook con los datos entregados

Los cinco blancos y sus 94 coadds están completos en `public/static/fields/`, sin cambios de bytes respecto al ZIP. Inicio estático en WISE 0855, D5, a 2 fps. Ninguna imagen, fuente, clasificación o serie se genera como observación ficticia.

- Detectores D1–D6, seis paneles, fechas disponibles, reproducción y pausa, blink a 500 ms, diferencia B−A y suma A+B a partir de float32 little-endian.
- Precarga de PNG y flags antes de reproducir, último cuadro con doble duración, cancelación de solicitudes de manifiesto al cambiar blanco y protección ante respuestas tardías.
- NaN morado, píxel entero sin interpolación, flags a 0.55, retícula y trayectoria de `expected_position` o de la fuente seleccionada. Diferencia en gris con percentil 99 de |B−A|; suma con el stretch lineal del original.
- Unidades, fecha, MJD, banda efectiva, número de exposiciones, flags, release y pipeline del manifiesto.
- Ausencias reales de Epsilon Indi B e4 D1/D4 explícitas. Las parejas A/B pueden incluir una fecha ausente: se muestra el aviso, no se crea un cuadro.
- Solo FOV 3.2′. Espectro y curva no se deducen de los seis detectores: sus URLs son null y se muestra `Not available yet.`.

Buscar los alias de los cinco objetivos o coordenadas RA/Dec decimales o sexagesimales. Las coordenadas arbitrarias requieren `/api/field`; no se simula cobertura. Espacio reproduce/pausa y flechas recorren fechas cuando el foco no está en un control. Escape cierra el chat y sale de vista ampliada. Paneles redimensionables con puntero o flechas y restaurables con doble clic.

`Share` copia la URL. Se conservan `target, ra, dec, det, t, mode, grid, a, b, fps, src`; los cambios de blanco crean historial y las fechas actualizan la entrada actual. Recarga, atrás y adelante vuelven a cargar el manifiesto correspondiente. `/embed` abre el panel de campo ampliado.

## Backend opcional

Copiar `.env.example` a `.env.local` y establecer:

```dotenv
VITE_API_BASE=https://DOMINIO-REAL-DEL-EQUIPO
```

Es una variable de compilación; reconstruir y volver a desplegar después de cambiarla. El paquete recibido no proporcionó una URL real. No se inventó ninguna. CORS debe permitir el origen del frontend.

Contratos implementados: GET `/api/field`, `/api/sources`, `/api/catalogs`, POST `/api/agent` con `view_state` e historial, POST `/api/marks` con `user_label`, coordenadas, época y client_id. Ninguno se ha validado contra el servidor del equipo. Los votos solo se confirman después de HTTP exitoso. GET `/api/marks` y la visualización del historial de votos están pendientes.

Fuentes: filtro de clase, revisión y movimiento, razones, resumen, símbolo de clase, selección, seguimiento y marcadores. Gaia/WISE quedan desactivados sin catálogo. El agente tiene texto, voz cuando el navegador la soporta, pasos de tour y validación de acciones. Su respaldo intenta `/static/agent/<target_id>.json`; esos archivos no fueron entregados. Sin respuesta válida muestra el aviso de indisponibilidad, conservando el control manual. Los controles manuales del panel interrumpen un tour automático.

El cielo usa Aladin v3.9.0-beta (la misma versión del HTML), empaquetado localmente. Si falta WebGL2, carga automáticamente el renderizador Canvas de Aladin v2, con fuente y licencia incluidas en `public/vendor/`. La esfera AllWISE y sus marcadores están verificados en esta sesión. El atlas de vista general está guardado sin modificaciones en `public/static/sky/allwise/`; los detalles de mayor resolución se solicitan al espejo IRSA. El botón circular «Sky overview» vuelve a la esfera; «Center field» acerca al campo científico. Este panorama AllWISE es contexto, no pertenece a los 94 coadds SPHEREx. `Targets · 94` muestra el reparto por objetivo calculado desde sus manifiestos.

## Vercel

Importar el proyecto, preset **Vite**, comando `npm run build`, salida `dist`. Configurar `VITE_API_BASE` únicamente si se dispone del backend real. `vercel.json` resuelve `/embed`; los estáticos conservan sus rutas. El build también crea `dist/embed/index.html` para hosting estático. No hay claves ni secretos del backend en este proyecto.

## Estructura

`src/components/` contiene la interfaz; `src/store.js` es el estado común; `src/hooks/` gestiona reproducción, URL y tamaño; `src/lib/` contiene recursos, coordenadas, matemáticas, dibujo y acciones del agente. `docs/` conserva las guías entregadas. `tests/science.test.js` cubre los contratos científicos que pueden comprobarse sin backend.

Consultar `QA_REPORT.md` antes de considerar cerrada la integración externa.
