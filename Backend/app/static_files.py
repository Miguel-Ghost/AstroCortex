"""Static field files: explicit content types and one-hour browser/CDN cache."""

from __future__ import annotations

import mimetypes

from starlette.staticfiles import StaticFiles

CACHE_CONTROL = "public, max-age=3600"

# Explicit types: system mimetypes tables differ between machines (Windows, Render's Linux image).
mimetypes.add_type("application/octet-stream", ".bin")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("application/json", ".json")


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = CACHE_CONTROL
        return response
