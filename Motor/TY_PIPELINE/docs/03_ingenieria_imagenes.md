# Ingeniería de características para imágenes SPHEREx (propuesta)

## Situación

Hay 1927 MEF, pero de **5 objetos**. Con 5 objetos no se puede entrenar ni evaluar un clasificador de
imágenes: cualquier métrica sería ruido y el modelo memorizaría los objetos. Por eso esta versión hace
control de calidad (`06_spherex/fits_qa.csv`) y espectros descriptivos, y deja las imágenes fuera del modelo.

## Qué sí conviene cuando haya más objetos

1. **Primero espectro, no píxeles.** Para T/Y lo que discrimina es la forma espectral: absorción de CH₄ a
   3.3 µm, H₂O cerca de 2.7 µm, CO a 4.6 µm y el pico cerca de 4 µm. Ya están calculados como índices en
   `indices_espectrales_piloto.csv`.
2. **Fotometría con ePSF** (no apertura): SPHEREx está submuestreado (FWHM ≈ 1.1 px).
3. **Forma del recorte** como variables tabulares: elongación, residuo del ajuste PSF, fracción de píxeles
   marcados en FLAGS.

## Aumento de datos con sentido físico (solo dentro de los pliegues de entrenamiento)

- Ruido gaussiano escalado con el plano `VARIANCE` real.
- Versiones más débiles (multiplicar flujo y recalcular ruido) para simular objetos más lejanos.
- Huecos de canales reales: apagar longitudes de onda donde otras exposiciones tienen FLAGS.
- No usar rotaciones/espejos genéricos sin rotar también la PSF y el WCS.

## Filtros

- Restar `ZODI` antes de medir.
- Máscara con las definiciones de cada cabecera (MSKN/MSKM); `SOURCE` no es defecto.
- No aplicar filtros de suavizado: degradan una PSF que ya está submuestreada.
