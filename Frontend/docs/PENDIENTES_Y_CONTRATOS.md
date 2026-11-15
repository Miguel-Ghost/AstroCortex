# Pendientes y contratos — versión verificada al armar el handoff

## Aportado y verificado

- `AstroCortex_Sky.html`: base original (92 478 bytes). Dos variantes recuperadas de la biblioteca tienen SHA-256 idéntico; se incluyó una sola para evitar duplicación.
- `migracion_frontend_astrocortex.md`: guía principal completa. No se ha ejecutado todavía la migración React en este handoff.
- `flipbook_frontend_paso_a_paso.md` y `guia_visor_alessandro.md`: documentos de apoyo aportados previamente.
- `LEEME_flipbook_datos_reales.md`: entregado dentro del ZIP `static_fields.zip`.
- Datos: manifiestos de 5 blancos, 94 fotogramas, BIN little-endian y masks. Las rutas y longitudes se comprobaron con el script de validación.

## No aportado o no comprobado

- URL efectiva de FastAPI/Render, disponibilidad y versiones actuales; requerirá `VITE_API_BASE` al integrarse.
- Respuestas reales de `GET /api/sources`, `/api/catalogs`, `GET/POST /api/marks`, `POST /api/agent`; son contratos descritos por la guía, no endpoints comprobados en este paquete.
- JSON de respaldo `/static/agent/<id>.json` (no incluido); la UI debe tener fallback seguro si no está.
- Documento independiente «Dinámica del motor clasificatorio» mencionado en migración no ha sido adjuntado; no simular su contenido. La guía principal sí incluye mapeo para `review_reasons`.
- Credenciales GitHub, Vercel o backend; Work no debe afirmar haber desplegado sin confirmación real.

## Manejo esperado

- Los cinco blancos funcionan por estáticos sin configurar API.
- `GET /api/field` solo para otras coordenadas, con 404 `no_coverage` cuando corresponda; mostrar objetivos de ejemplo.
- Manifiesto con URLs auxiliares nulas: no llamar esas URLs, visualizar `Not available yet.`.
- Para APIs de clasificador y agente, intentar conexión solo cuando `VITE_API_BASE` esté configurado; si falla, renderizar panel con estado recuperable y registrar la incidencia.
- No construir observaciones inventadas, etiquetas no verificadas ni confirmaciones de descubrimiento astronómico.

## Validación de entrega de Work

- Ejecutar `python scripts/verificar_static_fields.py` sobre el paquete antes de copiar datos.
- En el proyecto final, ejecutar `npm run build` y pruebas de navegador al menos en WISE0855, Epsilon Indi B y Barnard, además de flujo de URL.
- Entregar app y QA report con diferencias entre guías y API descubiertas al integrar.
