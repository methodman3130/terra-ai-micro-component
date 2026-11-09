"""TERRA-AI Micro-Component API.

Read-only by design. The prototype demonstrates a historical baseline and a
benchmark; it does not accept writes from the browser, so there is no path from
the public interface into the curated layer.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import current_user
from app.routers import auth_routes, benchmark, geo, meta, series

app = FastAPI(
    title="TERRA-AI Micro-Component",
    version="0.1.0",
    description=(
        "Historical baseline retrieval, cleaning and benchmark prototype for "
        "Benguet vegetable farmgate prices. University of the Cordilleras. "
        "PSA OpenSTAT data under CC BY 4.0."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("TERRA_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

# /health, /notice and /auth are open. Everything that returns data requires a
# signed-in account: the panel is institutional, not public, and provenance in
# particular names internal retrieval paths.
app.include_router(meta.router)
app.include_router(auth_routes.router)

protected = [Depends(current_user)]
app.include_router(series.router, dependencies=protected)
app.include_router(geo.router, dependencies=protected)
app.include_router(benchmark.router, dependencies=protected)


@app.get("/")
def root() -> dict:
    return {
        "service": "terra-ai-micro-component",
        "docs": "/docs",
        "notice": meta.PROTOTYPE_NOTICE["banner"],
    }
