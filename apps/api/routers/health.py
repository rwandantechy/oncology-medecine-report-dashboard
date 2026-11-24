"""Service status. Open to every caller so the public site can tell if the API is up."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..core import content, settings
from ..db import snapshot
from ..services.ai_providers import provider_status

router = APIRouter(tags=["health"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> str:
    """Browser landing: point people at the public app instead of a JSON 404."""
    app_url = settings.public_app_url()
    safe_url = escape(app_url, quote=True)
    safe_label = escape(app_url)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>EveryDoseMatters API</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Arial, Helvetica, sans-serif;
      background: #eef1f4;
      color: #071f49;
    }}
    main {{
      max-width: 28rem;
      padding: 1.5rem;
      background: #fff;
      border: 1px solid #dce3ea;
    }}
    h1 {{
      font-size: 1.15rem;
      margin: 0 0 0.5rem;
    }}
    p {{
      margin: 0 0 0.85rem;
      color: #5a6f80;
      font-size: 0.9rem;
      line-height: 1.45;
    }}
    a {{
      color: #14345f;
      font-weight: 700;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <main>
    <h1>EveryDoseMatters API</h1>
    <p>This host serves the research API. Open the app here:</p>
    <p><a href="{safe_url}">{safe_label}</a></p>
  </main>
</body>
</html>
"""


@router.get("/api/health")
def health() -> dict:
    return {
        "status": content.STATUS_OK,
        "snapshot_available": snapshot.exists(),
        **provider_status(),
    }
