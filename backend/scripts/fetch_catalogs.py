"""Gaia DR3 and CatWISE2020 around each published field -> static/fields/<folder>/catalogs.json.

Run where there is internet (Render does not need it: the files are committed):
    python -m scripts.fetch_catalogs            # all fields
    python -m scripts.fetch_catalogs wise0855   # one field

Queries NOIRLab Astro Data Lab anonymously (the service the team already used for the classifier
catalogues). The cone radius covers the corners of the 3.2' cutout. Positions are kept at their own
catalogue epoch (Gaia 2016.0, CatWISE MJD 57170 = 2015.4) with their proper motions; the source
builder propagates them to the SPHEREx dates before matching.
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from app.config import get_settings
from app.services.static_store import StaticStore
from pipeline.sources import CATWISE_EPOCH_MJD, Grid
from pipeline.targets import mjd_to_jyear

DATALAB = "https://datalab.noirlab.edu/query/query"
TOKEN = "anonymous.0.0.anon_access"
RADIUS_DEG = 0.045  # 2.7': covers the cutout corners (2.27') plus motion since the catalogue epoch
GAIA_EPOCH_MJD = 57388.5  # J2016.0


def query(sql: str, timeout: float = 120.0) -> list[dict]:
    url = DATALAB + "?" + urllib.parse.urlencode({"sql": sql, "ofmt": "csv", "async": "false"})
    request = urllib.request.Request(url, headers={"X-DL-AuthToken": TOKEN, "User-Agent": "astrocortex/0.2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8")
    if text.lstrip().startswith(("<", "{")):
        raise RuntimeError(f"Data Lab returned an error: {text[:300]}")
    return list(csv.DictReader(io.StringIO(text)))


def _f(value: str | None, ndigits: int) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else round(number, ndigits)  # NaN -> None


def gaia_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "source_id": str(r["source_id"]),
            "ra": _f(r["ra"], 7),
            "dec": _f(r["dec"], 7),
            "g_mag": _f(r.get("phot_g_mean_mag"), 3),
            "pmra": _f(r.get("pmra"), 2),  # mas/yr, includes cos(dec)
            "pmdec": _f(r.get("pmdec"), 2),
            "parallax": _f(r.get("parallax"), 3),
        }
        for r in rows
    ]


def catwise_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        pmra, pmdec = _f(r.get("pmra"), 4), _f(r.get("pmdec"), 4)  # CatWISE gives arcsec/yr
        out.append(
            {
                "name": r["source_name"].strip(),
                "ra": _f(r.get("ra_pm") or r["ra"], 7),
                "dec": _f(r.get("dec_pm") or r["dec"], 7),
                "w1": _f(r.get("w1mpro"), 3),
                "w2": _f(r.get("w2mpro"), 3),
                "pmra": None if pmra is None else round(pmra * 1000.0, 1),  # -> mas/yr
                "pmdec": None if pmdec is None else round(pmdec * 1000.0, 1),
                "sig_pm": _f(max(_f(r.get("sigpmra"), 4) or 0.0, _f(r.get("sigpmdec"), 4) or 0.0) * 1000.0, 1),
            }
        )
    return out


def catalogs_for(ra: float, dec: float) -> tuple[list[dict], list[dict]]:
    gaia = query(
        "SELECT source_id, ra, dec, phot_g_mean_mag, pmra, pmdec, parallax FROM gaia_dr3.gaia_source "
        f"WHERE q3c_radial_query(ra, dec, {ra}, {dec}, {RADIUS_DEG})"
    )
    catwise = query(
        "SELECT source_name, ra, dec, ra_pm, dec_pm, w1mpro, w2mpro, pmra, pmdec, sigpmra, sigpmdec "
        f"FROM catwise2020.main WHERE q3c_radial_query(ra, dec, {ra}, {dec}, {RADIUS_DEG})"
    )
    return gaia_rows(gaia), catwise_rows(catwise)


def layer_document(manifest: dict, gaia: list[dict], wise: list[dict], source: str) -> dict:
    """catalogs.json for /api/catalogs and the source builder.

    Each row keeps its catalogue position (ra_cat, dec_cat, at the catalogue epoch) and gets ra, dec
    propagated to the field's reference date, which is where the map layers draw it. Rows outside
    the cutout (plus a 0.25' margin) are dropped.
    """
    grid = Grid(manifest)
    ref_year = mjd_to_jyear(float(manifest.get("center_ref_mjd") or manifest.get("center_mjd") or 0.0))
    margin_px = 0.25 * 60 / grid.pix

    def move(row: dict, year: float, pm_ok: bool) -> dict | None:
        pmra = (row.get("pmra") or 0.0) if pm_ok else 0.0
        pmdec = (row.get("pmdec") or 0.0) if pm_ok else 0.0
        dt = ref_year - year
        dec = row["dec"] + pmdec * dt / 3.6e6
        ra = (row["ra"] + pmra * dt / 3.6e6 / math.cos(math.radians(dec))) % 360.0
        if not grid.inside(*grid.to_xy(ra, dec), margin=margin_px):
            return None
        return {**row, "ra_cat": row["ra"], "dec_cat": row["dec"], "ra": round(ra, 7), "dec": round(dec, 7)}

    catwise_year = mjd_to_jyear(CATWISE_EPOCH_MJD)
    gaia_out = [r for r in (move(g, 2016.0, True) for g in gaia) if r]
    wise_out = []
    for w in wise:
        significant = (
            w.get("sig_pm") is not None
            and w.get("pmra") is not None
            and (math.hypot(w["pmra"], w["pmdec"] or 0.0) > 3 * w["sig_pm"])
        )
        row = move(w, catwise_year, significant)
        if row:
            wise_out.append(row)
    return {
        "field_id": manifest.get("field_id"),
        "epoch_mjd": manifest.get("center_ref_mjd"),
        "synthetic": False,
        "source": source,
        "positions": "ra, dec at epoch_mjd (proper motion applied); ra_cat, dec_cat at the catalogue epoch",
        "gaia_epoch_mjd": GAIA_EPOCH_MJD,
        "wise_epoch_mjd": CATWISE_EPOCH_MJD,
        "gaia": sorted(gaia_out, key=lambda r: (r["g_mag"] is None, r["g_mag"] or 0.0)),
        "wise": sorted(wise_out, key=lambda r: (r["w1"] is None, r["w1"] or 0.0)),
    }


def main(argv: list[str]) -> int:
    """`--from-file F` imports a download made elsewhere ({"fields": {folder: {"gaia", "wise"}}})."""
    settings = get_settings()
    store = StaticStore(settings.fields_dir, settings.targets_file)
    imported = None
    if argv[:1] == ["--from-file"]:
        imported = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        argv = argv[2:]
    refs = [store.resolve(a) for a in argv] if argv else store.fields()
    for ref in refs:
        if ref is None:
            print("unknown field", file=sys.stderr)
            return 2
        manifest = store.manifest(ref.field_id)
        if imported is not None:
            block = imported["fields"].get(ref.folder)
            if block is None:
                print(f"{ref.field_id}: not in the file, skipped")
                continue
            gaia, wise, source = block["gaia"], block["wise"], imported.get("source", "imported")
        else:
            gaia, wise = catalogs_for(manifest["center"]["ra"], manifest["center"]["dec"])
            source = "NOIRLab Astro Data Lab: gaia_dr3.gaia_source, catwise2020.main"
        doc = layer_document(manifest, gaia, wise, source)
        path = settings.fields_dir / ref.folder / "catalogs.json"
        path.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"{ref.field_id}: {len(doc['gaia'])} Gaia, {len(doc['wise'])} CatWISE in the cutout -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
