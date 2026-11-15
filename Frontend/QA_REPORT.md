# QA — AstroCortex — 15 de noviembre de 2026

## Resultado

El proyecto migra a React/Vite/Zustand y compila. El flipbook local utiliza los 94 cuadros entregados. Se realizaron pruebas funcionales con el navegador de esta sesión. **La integración con backend sigue pendiente. La esfera del cielo se restauró y se verificó con el renderizador compatible.**

## Comandos ejecutados

- `python scripts/verificar_static_fields.py` y `npm run verify:data`: PASS, cinco manifiestos, 16 épocas, 94 cuadros completos, dimensiones PNG/flags y longitudes BIN correctas.
- `npm test`: PASS, seis pruebas. Integridad/rutas de los 94 cuadros; ausencias reales de Epsilon Indi; B−A y A+B con NaN; percentil y gris de diferencia; coordenadas y orientación; desplazamiento real de WISE en el manifiesto.
- `npm run build`: PASS. Vite genera `dist/`; se incluye entrada de `/embed`.
- Revisión de `src/`: sin `makeField`, `local_generated`, `sceneRNG`, respuestas científicas locales inventadas ni generadores de cuadros.
- El CSS original completo se portó antes de añadir ajustes; el original se preserva en `reference/`.

## Verificación funcional en navegador

| Comprobación | Resultado observado |
|---|---|
| Intro | En recarga, overlay presente, dos paths visibles en `.intro-rays`, animación `rays`; al terminar queda oculto y no se reinicia al cambiar pestaña. |
| Cinco blancos | Barnard abre D2; Epsilon Indi/WISE abren D5; RW Aur/R Dra abren D3. Fechas, bandas y exposiciones coinciden con los manifiestos. |
| Play/Pause | La reproducción avanza entre las fechas reales; se observó WISE pasar a e3 y pausarse. |
| Spectrum / Light curve / Catalogs | Cada pestaña muestra `Not available yet.`; volver a Flipbook conserva un visor funcional. |
| Seis paneles | Se dibujan los seis PNG; Epsilon Indi e4 muestra literalmente `No D1 data for this date.` y `No D4 data for this date.`. |
| Blink, diferencia, suma | Controles y cambios de modo funcionan; suma y diferencia leen BIN, no capturas de PNG. Verificación matemática adicional en tests. |
| Flags | Checkbox cambia su estado; overlay usa PNG de flags a 0.55. |
| URL / recarga | Recarga con WISE, detector D3, época elegida y parámetros completos restaura la vista. |
| Agente sin backend | `Guide me` muestra la respuesta honesta de indisponibilidad; permanece en el blanco seleccionado y los controles siguen activos. |
| Orbe | Animación original portada; reposicionado al área del cielo en escritorio para no tapar controles. Arrastre implementado. |

Las pruebas visuales se hicieron en el viewport de escritorio disponible (aproximadamente 1365×938). Se conservan las media queries y se añaden mínimos de altura/scroll para móvil. No se verificaron físicamente 1366×768, 1440×900, 1920×1080 ni un dispositivo móvil; no se afirma cobertura de esos tamaños. Voz/micrófono no se activó para evitar solicitar permisos durante QA.

## Correcciones durante QA

Se corrigieron un cierre JSX y una duplicación de React en la previsualización configurando `resolve.dedupe`. El build y las pruebas se repitieron después. También se retiró la superposición del orbe sobre el flipbook y se alineó la matemática de diferencia/suma con las guías, sin inventar imágenes.

## Pendiente o no contrastado

- No se recibió `VITE_API_BASE`. No se llamaron los endpoints reales `/api/field`, `/api/sources`, `/api/catalogs`, `/api/agent` ni `/api/marks`; su compatibilidad en vivo sigue pendiente. Tampoco se probó autenticación, CORS o persistencia real de votos. GET de historial de votos pendiente.
- Las URLs spectrum/lightcurve/autotype son null; no hay series para probar gráficas reales. No se solicitan recursos null.
- Los JSON `/static/agent/<target_id>.json` no existen en los datos entregados. La indisponibilidad se maneja sin respuestas locales ficticias.
- Corrección posterior: se identificó el error real `WebGL2 not supported by your browser`. Era una cadena, por lo que leer solo `e.message` dejaba el aviso vacío. Se empaquetó Aladin v3.9.0-beta y se añadió Aladin v2 Canvas como alternativa automática, sin reemplazar la versión principal. Su código fuente y licencia se incluyen. Se cambió el espejo inicial AllWISE al de IRSA; se guardó su atlas Allsky original y properties para una vista general independiente del servicio. Se verificaron la esfera visible y sus marcadores reales. El renderizador WebGL2 principal no se puede verificar en este navegador que carece de él. Cambio de survey SPHEREx requiere WebGL2; altas resoluciones y otros surveys siguen dependiendo de sus servidores.
- Tours reales, overlays de catálogos, clasificador, seguimiento de fuentes y votos están preparados en código; necesitan una respuesta del backend para pruebas de extremo a extremo.
- Historial atrás/adelante verificado en navegador entre Barnard y RW Aur, con recarga del manifiesto correcto. `/embed` preparado en build; pendiente revisión final de la ruta publicada.

## Actualización: esfera y ubicación de los 94 cuadros

- Vista inicial y botón circular `Sky overview`: esfera completa (proyección SIN) con panorama AllWISE real. No se generaron texturas astronómicas.
- `Targets · 94` y el diálogo muestran recuentos derivados de los cinco manifiestos: Barnard 18, Epsilon Indi B 22, WISE 18, RW Aur 18, R Dra 18.
- Lista Objects incluye los blancos reales aunque no esté conectado el clasificador.
- Se separó el seguimiento de la fuente del paneo manual para que reproducir el flipbook no recentre el cielo cuando Track está apagado.
- Tests científicos, validador de datos y build se repitieron y pasan tras la corrección.

Pruebas finales de esfera: arrastre cambia las coordenadas, zoom modifica FoV, Center field acerca y Sky overview restaura la esfera. Play avanza las fechas sin recentrar la cámara con Track apagado. Diálogo Targets confirma 94 cuadros y el reparto 18/22/18/18/18. Se verificó en navegador el retorno de la esfera con el panorama local real.
