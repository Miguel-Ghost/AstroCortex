"""Lectura de entradas existentes (solo lectura) y verificación de recibos."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .common import read_json, sha256

# Columnas del catálogo de objetos que NO pueden usarse como predictores:
# identificadores, etiqueta y variables cuya procedencia difiere entre clases
# (las estrellas salen de Gaia 2016.0 y las enanas de la literatura).
OBJECTS_FORBIDDEN = {
    "oid": "identificador",
    "name": "identificador",
    "source": "procedencia de la muestra: delata la clase",
    "label": "etiqueta",
    "subdwarf": "metadato de la etiqueta",
    "sptnum": "tipo espectral: es la etiqueta",
    "spt_opt": "tipo espectral: es la etiqueta",
    "spt_ir": "tipo espectral: es la etiqueta",
    "ucs_ref_spt": "referencia de la etiqueta",
    "exoplanet": "solo existe para enanas",
    "young": "solo existe para enanas",
    "multiple_unresolved": "solo existe para enanas",
    "has_companion": "solo existe para enanas",
    "ucs_W1": "solo existe para enanas (UltracoolSheet)",
    "ucs_W2": "solo existe para enanas (UltracoolSheet)",
    "gaia_source_id": "identificador; su ausencia delata la clase",
    "gaia_field": "solo existe para estrellas de control",
    "epoch": "estrellas=2016.0 por construcción; delata la clase",
    "plx": "procedencia distinta por clase (Gaia vs literatura)",
    "pmra": "procedencia distinta por clase; se usa el μ medido por CatWISE",
    "pmdec": "procedencia distinta por clase; se usa el μ medido por CatWISE",
    "ra": "posición: solo para agrupar en zonas del cielo",
    "dec": "posición: solo para agrupar en zonas del cielo",
}

CATALOG_DTYPES = {"cc_flags": "string", "ab_flags": "string", "ph_qual": "string",
                  "cc_flg": "string", "bl_flg": "string", "rd_flg": "string",
                  "var_flg": "string", "source_id": "string", "designation": "string",
                  "unwise_objid": "string"}


def read_table(path: Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    raise ValueError(f"Formato no soportado: {path}")


def find_table(folder: Path, stem: str) -> Path:
    for ext in (".parquet", ".csv"):
        p = Path(folder) / f"{stem}{ext}"
        if p.is_file():
            return p
    raise FileNotFoundError(f"No existe {stem}.parquet/.csv en {folder}")


def load_objects(cfg: dict) -> tuple[pd.DataFrame, str]:
    path = find_table(Path(cfg["paths"]["processed"]), "objects")
    df = read_table(path)
    need = {"oid", "label", "ra", "dec"}
    if not need.issubset(df.columns):
        raise RuntimeError(f"objects sin columnas {need - set(df.columns)}")
    if df["oid"].duplicated().any():
        raise RuntimeError("oid duplicado en objects")
    df["label"] = df["label"].astype(str)
    return df, sha256(path)


def load_catalog(cfg: dict, name: str, objects_sha: str, extra: bool = False) -> tuple[pd.DataFrame, dict]:
    """Une los lotes CSV de NOIRLab verificando cada recibo contra objects.
    extra=True: lotes de la descarga complementaria (typipe.fetch_extra)."""
    if extra:
        folder = Path(cfg["paths"]["extra_catalogs"]) / name
        files = sorted(folder.glob("batch_*.csv"))
    else:
        folder = Path(cfg["paths"]["noirlab_catalogs"]) / name
        files = sorted(folder.glob("chunk_*.csv"))
    if not files:
        raise FileNotFoundError(f"Sin lotes para {name} en {folder}")
    frames, bad = [], []
    for f in files:
        receipt = f.with_suffix(".json")
        if not receipt.is_file():
            bad.append(f"{f.name}: sin recibo")
            continue
        meta = read_json(receipt)
        if meta.get("response_sha256", meta.get("sha256")) != sha256(f):
            bad.append(f"{f.name}: hash distinto al recibo")
            continue
        if meta.get("input_sha256") != objects_sha:
            bad.append(f"{f.name}: hecho con otro objects.parquet")
            continue
        frames.append(pd.read_csv(f, dtype=CATALOG_DTYPES, low_memory=False))
    if bad:
        raise RuntimeError(f"{name}: {len(bad)} lotes inválidos, p.ej. {bad[:3]}")
    frame = pd.concat(frames, ignore_index=True)
    frame["oid"] = pd.to_numeric(frame["oid"], errors="coerce").astype("int64")
    frame["sep_arcsec"] = angular_sep_arcsec(frame["ra_q"], frame["dec_q"], frame["ra"], frame["dec"])
    info = {"files": len(files), "rows": len(frame), "objects_with_candidates": int(frame["oid"].nunique())}
    return frame, info


def angular_sep_arcsec(ra1, dec1, ra2, dec2) -> np.ndarray:
    ra1, dec1, ra2, dec2 = (np.deg2rad(np.asarray(x, dtype=float)) for x in (ra1, dec1, ra2, dec2))
    a = (np.sin((dec1 - dec2) / 2) ** 2 +
         np.cos(dec1) * np.cos(dec2) * np.sin((ra1 - ra2) / 2) ** 2)
    return np.rad2deg(2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))) * 3600.0


def best_match(frame: pd.DataFrame, radius: float) -> pd.DataFrame:
    """Elige el candidato más cercano por objeto; conserva n de candidatos y
    la separación del segundo como métricas de calidad del cruce (no predictores)."""
    f = frame.loc[frame["sep_arcsec"] <= radius + 1e-6].sort_values(["oid", "sep_arcsec"]).copy()
    f["_rank"] = f.groupby("oid").cumcount()
    n = f.groupby("oid").size().rename("n_cand")
    second = f.loc[f["_rank"] == 1].set_index("oid")["sep_arcsec"].rename("sep2")
    best = f.loc[f["_rank"] == 0].drop(columns="_rank").set_index("oid")
    best = best.join(n).join(second)
    return best.reset_index()


def load_gaia(cfg: dict) -> pd.DataFrame | None:
    try:
        g = read_table(find_table(Path(cfg["paths"]["processed"]), "xm_gaia"))
    except FileNotFoundError:
        return None
    if "n_match" in g.columns:
        g = g.loc[g["n_match"].fillna(1) == 1]
    return g.drop_duplicates("oid")


def input_files(cfg: dict) -> list[Path]:
    proc = Path(cfg["paths"]["processed"])
    files = sorted(proc.glob("*.parquet")) + sorted(proc.glob("*.csv"))
    ucs = Path(cfg["paths"]["ultracoolsheet"])
    if ucs.is_file():
        files.append(ucs)
    idx = Path(cfg["paths"]["spherex_index"])
    if idx.is_file():
        files.append(idx)
    return files
