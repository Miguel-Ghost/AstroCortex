"""Image pipeline: turns many SPHEREx exposures into an aligned flipbook of a small sky field.

Steps (one module each):
    query      -> which exposures cover the position (IRSA SIA, index only)
    read       -> read only a small zone of each exposure from S3 (IMAGE - ZODI, VARIANCE, FLAGS)
    grid       -> resample every cutout onto one common north-up grid with a fixed centre
    epochs     -> group exposures into visits (epochs)
    coadd      -> combine the exposures of one epoch and detector (inverse-variance mean)
    render     -> fixed stretch per detector, PNG + float32 data
    build_field-> orchestrates the steps and writes manifest.json (contract 7.2 of the frontend guide)
"""

DETECTORS = {
    1: (0.75, 1.09),
    2: (1.10, 1.62),
    3: (1.63, 2.41),
    4: (2.42, 3.82),
    5: (3.83, 4.41),
    6: (4.42, 5.00),
}
PIXSCALE_ARCSEC = 6.2
