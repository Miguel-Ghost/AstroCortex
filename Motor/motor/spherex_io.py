"""Acceso a SPHEREx: índice (IRSA SIA), lectura parcial desde S3 y fotometría forzada.

Mismo método que el backend en producción (lectura con fsspec en bloques de 64 KB y
`.section[...]`): solo viajan los bloques del recorte, no el archivo de ~60 MB.
"""
from __future__ import annotations

import io
import json
import math
import time
import warnings
from dataclasses import dataclass

import numpy as np

FSSPEC_KWARGS = {"block_size": 65536, "cache_type": "blockcache"}
SIA_COLUMNS = ("access_url", "cloud_access", "t_min", "t_max", "obs_id", "energy_bandpassname")


# ----------------------------------------------------------------------------- índice
def sia_query(url: str, ra: float, dec: float, radius_deg: float, collection: str,
              timeout: float = 90.0, tries: int = 6, session=None) -> list[dict]:
    """Exposiciones de una colección cuya huella contiene (ra, dec). Reintenta 429/503/errores de red
    con espera 1, 2, 4, 8... s. Devuelve filas con las columnas de SIA_COLUMNS."""
    import requests
    from astropy.io.votable import parse_single_table
    params = {"COLLECTION": collection, "POS": f"circle {ra:.7f} {dec:.7f} {radius_deg}"}
    get = (session or requests).get
    delay, last = 1.0, None
    for attempt in range(1, tries + 1):
        try:
            r = get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < tries:
                last = f"HTTP {r.status_code}"
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            r.raise_for_status()
            break
        except Exception as exc:  # red caída, timeout
            last = repr(exc)
            if attempt == tries:
                raise RuntimeError(f"SIA falló tras {tries} intentos: {last}") from exc
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return filas_sia(r.content)


def filas_sia(content: bytes) -> list[dict]:
    """VOTable de SIA -> filas. Usa el atributo name de cada columna (no el ID, que IRSA llena con col1, col2...)."""
    from astropy.io.votable import parse_single_table
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = parse_single_table(io.BytesIO(content)).to_table(use_names_over_ids=True)
    low = {c.lower(): c for c in table.colnames}
    rows = []
    for row in table:
        rows.append({c: _py(row[low[c]]) for c in SIA_COLUMNS if c in low})
    return rows


def _py(v):
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, bytes):
        v = v.decode()
    if v is np.ma.masked:
        return None
    return v


def s3_key(cloud_access) -> str | None:
    """Clave S3 dentro de la columna cloud_access (JSON)."""
    if not isinstance(cloud_access, (str, dict)) or not cloud_access:
        return None
    try:
        data = json.loads(cloud_access) if isinstance(cloud_access, str) else cloud_access
    except (TypeError, ValueError):
        return None

    def find(node):
        if isinstance(node, dict):
            if isinstance(node.get("key"), str):
                return node["key"]
            for v in node.values():
                k = find(v)
                if k:
                    return k
        return None
    return find(data)


def key_from_url(url) -> str | None:
    """Clave S3 a partir de access_url de IRSA: lo que sigue a /ibe/data/spherex/ (mismo árbol que el bucket)."""
    if not isinstance(url, str) or "/ibe/data/spherex/" not in url:
        return None
    return url.split("/ibe/data/spherex/", 1)[1].split("?")[0]


def clave_s3(row: dict) -> str | None:
    return s3_key(row.get("cloud_access")) or key_from_url(row.get("access_url"))


def detector_number(bandpass: str | None) -> int | None:
    if not bandpass:
        return None
    s = str(bandpass).strip().upper()
    for d in range(1, 7):
        if s.endswith(f"D{d}"):
            return d
    return None


# ----------------------------------------------------------------------------- posiciones
def jyear_from_mjd(mjd: float) -> float:
    return 2000.0 + (mjd - 51544.5) / 365.25


def propagate(ra: float, dec: float, pmra_masyr: float, pmdec_masyr: float,
              epoch_jyear: float, target_jyear: float) -> tuple[float, float]:
    """Movimiento propio lineal (suficiente para recortes de 15 px: error << 1 px en 30 años)."""
    pmra = 0.0 if not np.isfinite(pmra_masyr) else pmra_masyr
    pmdec = 0.0 if not np.isfinite(pmdec_masyr) else pmdec_masyr
    dt = target_jyear - epoch_jyear
    dec2 = dec + pmdec * dt / 3.6e6
    ra2 = ra + pmra * dt / 3.6e6 / max(math.cos(math.radians(dec)), 1e-6)
    return ra2 % 360.0, max(min(dec2, 90.0), -90.0)


# ----------------------------------------------------------------------------- lectura
@dataclass
class Recorte:
    image: np.ndarray       # IMAGE − ZODI [MJy/sr], NaN fuera del detector
    variance: np.ndarray
    flags: np.ndarray       # int64; 0 fuera del detector
    flag_bits: dict         # nombre -> bit
    x: float                # posición del objeto dentro del recorte (0-based, centro de píxel)
    y: float
    x_full: float           # posición en el detector completo
    y_full: float
    mjd: float
    detector: int
    omega_sr: float
    wavelength_um: float | None


def _section(section, shape, xc, yc, size, fill):
    ny, nx = shape
    half = size // 2
    x0, y0 = int(round(xc)) - half, int(round(yc)) - half
    dtype = np.float64 if isinstance(fill, float) else np.int64
    out = np.full((size, size), fill, dtype=dtype)
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x0 + size, nx), min(y0 + size, ny)
    if cx0 < cx1 and cy0 < cy1:
        out[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] = section[cy0:cy1, cx0:cx1]
    return out, (x0, y0)


def flag_bits_from_header(header) -> dict:
    out = {}
    for key in header:
        k = str(key)
        if k.startswith("MSKN") and k[4:].isdigit():
            out[str(header[key]).strip().upper()] = int(k[4:])
    return out


def leer_recorte(url_or_path: str, position_at_mjd, size: int = 15, remote: bool = True,
                 read_lambda: bool = True) -> Recorte | None:
    """Lee IMAGE, VARIANCE, FLAGS y ZODI alrededor de la posición del objeto en la fecha de la
    exposición (MJD-AVG). Devuelve None si el objeto cae fuera del detector."""
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_area
    from astropy import log as astropy_log
    astropy_log.setLevel("WARNING")  # el aviso SIP del WCS espectral se repite en cada exposición y no aporta
    kw = {"use_fsspec": True, "fsspec_kwargs": FSSPEC_KWARGS} if remote else {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fits.open(url_or_path, lazy_load_hdus=True, **kw) as h:
            hdr = h["IMAGE"].header
            mjd = float(hdr.get("MJD-AVG") or h[0].header.get("MJD-AVG"))
            ra, dec = position_at_mjd(mjd)
            wcs = WCS(hdr).celestial
            ny, nx = int(hdr["NAXIS2"]), int(hdr["NAXIS1"])
            x, y = (float(v) for v in wcs.world_to_pixel_values(ra, dec))
            if not (np.isfinite(x) and np.isfinite(y)) or not (-1 <= x <= nx and -1 <= y <= ny):
                return None
            img, (x0, y0) = _section(h["IMAGE"].section, (ny, nx), x, y, size, np.nan)
            zod, _ = _section(h["ZODI"].section, (ny, nx), x, y, size, np.nan)
            var, _ = _section(h["VARIANCE"].section, (ny, nx), x, y, size, np.nan)
            flg, _ = _section(h["FLAGS"].section, (ny, nx), x, y, size, 0)
            bits = flag_bits_from_header(h["FLAGS"].header)
            omega = float(proj_plane_pixel_area(wcs)) * (math.pi / 180.0) ** 2
            lam = None
            if read_lambda:
                try:
                    import astropy.units as u
                    ww = WCS(hdr, fobj=h, key="W")
                    ww.sip = None
                    v = ww.pixel_to_world(x, y)
                    v = v[0] if isinstance(v, (list, tuple)) else v
                    lam = float(u.Quantity(v).to_value(u.um))
                except Exception:  # noqa: BLE001 — metadato opcional
                    lam = None
            det = hdr.get("DETECTOR")
    img = img - zod
    return Recorte(image=img, variance=var, flags=flg, flag_bits=bits, x=x - x0, y=y - y0,
                   x_full=x, y_full=y, mjd=mjd, detector=int(det) if det is not None else -1,
                   omega_sr=omega, wavelength_um=lam)


# ----------------------------------------------------------------------------- fotometría
def _gauss_pixel_integral(x0: float, y0: float, sigma: float, shape) -> np.ndarray:
    """PSF gaussiana integrada en cada píxel (suma 1 en el plano infinito)."""
    from scipy.special import erf
    ny, nx = shape
    xs = np.arange(nx)
    ys = np.arange(ny)
    s = sigma * math.sqrt(2.0)
    fx = 0.5 * (erf((xs + 0.5 - x0) / s) - erf((xs - 0.5 - x0) / s))
    fy = 0.5 * (erf((ys + 0.5 - y0) / s) - erf((ys - 0.5 - y0) / s))
    return np.outer(fy, fx)


def fotometria_forzada(rc: Recorte, sigma_px: float, r_ap: float, anillo: tuple[float, float],
                       bits_no_mask: list[str], cobertura_min: float) -> dict:
    """Flujo total por ajuste lineal de la PSF (posición fija = la predicha), fondo por mediana
    en anillo. Unidades: Jy. Devuelve también el estado y la fracción de píxeles marcados."""
    keep = {b.upper() for b in bits_no_mask}
    bad_mask = 0
    for name, bit in rc.flag_bits.items():
        if name not in keep:
            bad_mask |= 1 << bit
    if not rc.flag_bits:  # sin definiciones en la cabecera: máscara conservadora estándar
        bad_mask = sum(1 << b for b in (0, 1, 2, 6, 9, 10, 11, 15, 17, 20, 22, 23, 24, 25, 26, 27, 28))
    img, var, flg = rc.image, rc.variance, rc.flags
    yy, xx = np.indices(img.shape)
    rr = np.hypot(xx - rc.x, yy - rc.y)
    good = np.isfinite(img) & np.isfinite(var) & (var > 0) & ((flg & bad_mask) == 0)
    out = {"x": rc.x_full, "y": rc.y_full, "mjd": rc.mjd, "detector": rc.detector,
           "lambda_um": rc.wavelength_um, "omega_sr": rc.omega_sr}
    core = rr <= r_ap
    out["frac_marcados_nucleo"] = float(1 - good[core].mean()) if core.any() else None
    outlier_bit = rc.flag_bits.get("OUTLIER")
    out["frac_outlier_nucleo"] = (float(((flg[core] >> outlier_bit) & 1).mean())
                                  if outlier_bit is not None and core.any() else None)
    ring = good & (rr >= anillo[0]) & (rr <= anillo[1])
    if ring.sum() < 8:
        out["estado"] = "SIN_FONDO"
        return out
    bkg = float(np.median(img[ring]))
    mad = float(np.median(np.abs(img[ring] - bkg))) * 1.4826
    psf = _gauss_pixel_integral(rc.x, rc.y, sigma_px, img.shape)
    use = good & core
    cover = float(psf[use].sum())
    out.update({"fondo_mjysr": bkg, "fondo_mad": mad, "cobertura_psf": cover})
    if cover < cobertura_min:
        out["estado"] = "NUCLEO_ENMASCARADO"
        return out
    w = 1.0 / var[use]
    p = psf[use]
    d = img[use] - bkg
    den = float(np.sum(w * p * p))
    amp = float(np.sum(w * p * d) / den)        # MJy/sr integrados (suma de la PSF = 1)
    err = float(1.0 / math.sqrt(den))
    to_jy = rc.omega_sr * 1e6
    out.update({"flux_jy": amp * to_jy, "err_jy": err * to_jy, "snr": amp / err if err > 0 else None,
                "estado": "OK"})
    return out
