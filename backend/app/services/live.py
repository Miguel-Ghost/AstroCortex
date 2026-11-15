"""Live fields: a SPHEREx field for any RA/Dec, built on request (LIVE_FIELDS=true).

When /api/field finds no published field, the same pipeline that built the published ones runs
for a still point at (ra, dec): IRSA SIA as the index (spherex_dr1 and spherex_qr3), at most
6 exposures per epoch and detector, partial reads from S3, coadd and manifest. Results are
cached on local disk, keyed by ra/dec rounded to 0.01 deg, so a repeated request is a file read.

BR-JOB-01: no request waits more than LIVE_TIMEOUT_S; the build keeps running and fills the
cache, so the next request finds it. BR-JOB-02: IRSA unavailable -> 503 upstream_unavailable;
no exposures -> 404 no_coverage. A folder is published atomically (built aside, then renamed),
so a half-written field is never served.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

import httpx

from app.config import Settings
from app.errors import ApiError
from pipeline.targets import Target

log = logging.getLogger("api")
LIVE_COLLECTIONS = ("spherex_dr1", "spherex_qr3")
NO_COVERAGE_TTL_S = 3600.0
NO_COVERAGE = ("no_coverage", "No SPHEREx images cover this position yet.")
UPSTREAM = (
    "upstream_unavailable",
    "The SPHEREx archive (IRSA) is not answering right now. Try again in a few minutes.",
)


def live_field_id(ra: float, dec: float) -> str:
    ra_r, dec_r = round(ra % 360.0, 2) % 360.0, round(dec, 2)
    return f"live_{ra_r + 0.0:.2f}_{dec_r + 0.0:.2f}"  # + 0.0 turns -0.0 into 0.0


def default_fetch(target: Target, max_per_epoch_detector: int) -> list:
    from pipeline.build_field import fetch_cutouts

    return fetch_cutouts(target, 31, max_per_epoch_detector, workers=4, collections=LIVE_COLLECTIONS)


class LiveFields:
    def __init__(self, settings: Settings, fetch: Callable[[Target, int], list] | None = None):
        self.settings = settings
        self.root = Path(settings.live_cache_dir)
        self.fetch = fetch or default_fetch
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="live-field")
        self._lock = threading.Lock()
        self._inflight: dict[str, Future] = {}
        self._no_coverage: dict[str, float] = {}

    def get(self, ra: float, dec: float) -> dict:
        field_id = live_field_id(ra, dec)
        cached = self._read(field_id)
        if cached is not None:
            return cached
        if self._no_coverage.get(field_id, 0.0) > time.monotonic():
            raise ApiError(404, *NO_COVERAGE)
        with self._lock:
            future = self._inflight.get(field_id)
            if future is None:
                ra_r, dec_r = (float(v) for v in field_id.removeprefix("live_").rsplit("_", 1))
                future = self._pool.submit(self._build, field_id, ra_r, dec_r)
                self._inflight[field_id] = future
        try:
            return future.result(timeout=self.settings.live_timeout_s)
        except FutureTimeout as exc:
            raise ApiError(
                504,
                "live_field_timeout",
                f"Building this field takes longer than {self.settings.live_timeout_s:.0f} s. It keeps building; "
                "try again in a minute.",
            ) from exc

    def _read(self, field_id: str) -> dict | None:
        path = self.root / field_id / "manifest.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _build(self, field_id: str, ra: float, dec: float) -> dict:
        started = time.monotonic()
        try:
            target = Target(
                target_id=field_id, name=f"RA {ra:.2f} Dec {dec:.2f}", kind="field", behavior=[], ra=ra, dec=dec
            )
            try:
                cutouts = self.fetch(target, self.settings.live_max_per_epoch_detector)
            except httpx.HTTPStatusError as exc:
                log.warning("live field: IRSA error", extra={"field_id": field_id, "status": exc.response.status_code})
                raise ApiError(503, *UPSTREAM) from exc
            except (httpx.TransportError, TimeoutError, OSError) as exc:
                log.warning("live field: IRSA unreachable", extra={"field_id": field_id, "error": str(exc)})
                raise ApiError(503, *UPSTREAM) from exc
            if not cutouts:
                self._no_coverage[field_id] = time.monotonic() + NO_COVERAGE_TTL_S
                raise ApiError(404, *NO_COVERAGE)
            from pipeline.build_field import build_field

            self.root.mkdir(parents=True, exist_ok=True)
            final = self.root / field_id
            work = self.root / f".{field_id}.{os.getpid()}.{threading.get_ident()}"
            shutil.rmtree(work, ignore_errors=True)
            manifest = build_field(
                target,
                cutouts,
                work,
                f"/static/live/{field_id}",
                field_id=field_id,
                expected_positions=False,
                data_release=self.settings.data_release,
                pipeline_commit=self.settings.commit,
            )
            if final.exists():  # another worker finished first: keep its copy
                shutil.rmtree(work, ignore_errors=True)
            else:
                os.replace(work, final)
            log.info(
                "live field built",
                extra={"field_id": field_id, "cutouts": len(cutouts), "seconds": round(time.monotonic() - started, 1)},
            )
            return self._read(field_id) or manifest
        finally:
            with self._lock:
                self._inflight.pop(field_id, None)
