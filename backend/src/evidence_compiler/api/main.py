"""FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from evidence_compiler.api.routes import evidence, runs, sources
from evidence_compiler.app import AppContext
from evidence_compiler.llm import llm_configured


def create_app(ctx: AppContext | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = ctx or AppContext()
        yield

    app = FastAPI(title="Evidence Compiler", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sources.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        settings = app.state.ctx.settings
        return {
            "status": "ok",
            "llm_configured": llm_configured(settings),
            "llm_provider": settings.llm_provider,
            "llm_model": settings.strong_model
            if settings.strong_model == settings.fast_model
            else f"{settings.strong_model} + {settings.fast_model}",
            "pricing_configured": settings.price_input_per_m is not None
            and settings.price_output_per_m is not None,
        }

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
