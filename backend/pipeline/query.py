"""Find SPHEREx exposures that cover a position, using IRSA SIA as an index only.

Rules from the team plan:
- one query per target and collection, cached;
- 1-2 simultaneous requests to IRSA; on 503/429 retry after 1, 2, 4... s (max 5 tries);
- always query spherex_dr1 and spherex_qr3 (+ _deep);
- never use keys under qr2/.

NOTE: not tested against IRSA from the development sandbox (no network access there).
"""

from __future__ import annotations

import io
import json
import time
from typing import Any

import httpx
from astropy.io.votable import parse_single_table

SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
S3_HTTPS_BASE = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/"
DEFAULT_COLLECTIONS = ("spherex_dr1", "spherex_qr3", "spherex_qr3_deep")
COLUMNS = ("access_url", "cloud_access", "t_min", "t_max", "obs_id", "energy_bandpassname")


def _to_python(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, bytes):
        return value.decode()
    return value


def sia_query(
    ra: float,
    dec: float,
    radius_deg: float = 0.05,
    collection: str = "spherex_dr1",
    timeout: float = 60.0,
    max_tries: int = 5,
) -> list[dict]:
    params = {"COLLECTION": collection, "POS": f"circle {ra} {dec} {radius_deg}"}
    delay = 1.0
    for attempt in range(1, max_tries + 1):
        response = httpx.get(SIA_URL, params=params, timeout=timeout)
        if response.status_code in (429, 503) and attempt < max_tries:
            time.sleep(delay)
            delay *= 2
            continue
        response.raise_for_status()
        break
    table = parse_single_table(io.BytesIO(response.content)).to_table()
    rows = []
    for row in table:
        rows.append({c: _to_python(row[c]) for c in COLUMNS if c in table.colnames})
    return rows


def s3_key_from_cloud_access(cloud_access: str | dict) -> str | None:
    """Extract the S3 key from the `cloud_access` column (a JSON blob)."""
    data = json.loads(cloud_access) if isinstance(cloud_access, str) else cloud_access

    def find_key(node: Any) -> str | None:
        if isinstance(node, dict):
            if isinstance(node.get("key"), str):
                return node["key"]
            for value in node.values():
                found = find_key(value)
                if found:
                    return found
        return None

    return find_key(data)


def exposures_for(
    ra: float, dec: float, radius_deg: float = 0.05, collections: tuple[str, ...] = DEFAULT_COLLECTIONS
) -> list[dict]:
    """Rows from all collections with an `s3_url` added; skips qr2/ keys and duplicates."""
    seen: set[str] = set()
    out: list[dict] = []
    for collection in collections:
        for row in sia_query(ra, dec, radius_deg, collection):
            key = s3_key_from_cloud_access(row.get("cloud_access") or "{}")
            if not key or key.startswith("qr2/") or key in seen:
                continue
            seen.add(key)
            out.append({**row, "collection": collection, "s3_url": S3_HTTPS_BASE + key})
    return out
