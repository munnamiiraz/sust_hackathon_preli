from __future__ import annotations

import os

APP_VERSION = "1.0.0"

_docs_enabled = os.getenv("DOCS_ENABLED", "true").lower() == "true"
DOCS_URL  = "/docs"  if _docs_enabled else None
REDOC_URL = "/redoc" if _docs_enabled else None

_raw_origins = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = (
    [o.strip() for o in _raw_origins.split(",")]
    if _raw_origins != "*"
    else ["*"]
)
