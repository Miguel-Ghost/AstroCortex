export function parseCoordinates(text) {
  let parts = text.trim().split(/[\s,;]+/);
  if (
    parts.length === 2 &&
    parts.every((p) => p !== "" && Number.isFinite(+p))
  ) {
    const [a, d] = parts.map(Number);
    if (a >= 0 && a < 360 && d >= -90 && d <= 90) return [a, d];
  }
  const m = text.match(
    /^\s*(\d{1,2})[h:]\s*(\d{1,2})[m:]\s*([\d.]+)s?\s+([+-]?)(\d{1,2})[d°:]\s*(\d{1,2})[m':]\s*([\d.]+)[s"]?\s*$/i,
  );
  if (!m) return null;
  const [h, min, s, sign, d, dm, ds] = m.slice(1);
  const ra = (+h + min / 60 + s / 3600) * 15,
    dec = (+d + dm / 60 + ds / 3600) * (sign === "-" ? -1 : 1);
  return h < 24 &&
    min < 60 &&
    s < 60 &&
    dm < 60 &&
    ds < 60 &&
    Math.abs(dec) <= 90
    ? [ra, dec]
    : null;
}
export function pixelToSky(x, y, m) {
  return {
    ra:
      (m.center.ra -
        ((x - (m.nx - 1) / 2) * m.pixscale_arcsec) /
          3600 /
          Math.cos((m.center.dec * Math.PI) / 180) +
        360) %
      360,
    dec: m.center.dec - ((y - (m.ny - 1) / 2) * m.pixscale_arcsec) / 3600,
  };
}
export function skyToPixel(ra, dec, m) {
  const dra = ((ra - m.center.ra + 540) % 360) - 180;
  return {
    x:
      (m.nx - 1) / 2 -
      (dra * 3600 * Math.cos((m.center.dec * Math.PI) / 180)) /
        m.pixscale_arcsec,
    y: (m.ny - 1) / 2 - ((dec - m.center.dec) * 3600) / m.pixscale_arcsec,
  };
}
