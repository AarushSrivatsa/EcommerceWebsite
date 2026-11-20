"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import database.storage as storage
from database.initialization import initialize_database
import deps
import memory
from aiagent.final_graph import build_graph
from routers import final_video, images, scripts, sections, youtube


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("startup: preparing the database", flush=True)
    await initialize_database()
    deps.graph = build_graph()
    print(f"startup: ready ({memory.rss_mb()} MB)", flush=True)
    try:
        yield
    finally:
        await storage.close()


app = FastAPI(title="Script to video", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def log_bad_request(request: Request, exc: RequestValidationError):
    """FastAPI's 422, with what was wrong written to the log (Render shows only "422 Unprocessable Entity")."""
    print(f"422: {request.method} {request.url.path} -> {exc.errors()}", flush=True)
    return await request_validation_exception_handler(request, exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", include_in_schema=False)
async def health():
    """For Render's health check."""
    return {"status": "ok", "ram_mb": memory.rss_mb()}


app.include_router(scripts.router)
app.include_router(sections.router)
app.include_router(images.router)
app.include_router(final_video.router)
app.include_router(youtube.router)


# ── the website: the built Vue app (frontend/dist), served by this same app ────
FRONTEND_BUILD = Path(__file__).resolve().parent / "frontend" / "dist"

if FRONTEND_BUILD.is_dir():                      # missing while developing; run `npm run build` in frontend/ or use `npm run dev`
    @app.get("/{path:path}", include_in_schema=False)
    async def website(path: str):
        """A real file from the build (js, css, images), otherwise index.html so Vue's router handles the page."""
        file = (FRONTEND_BUILD / path).resolve()
        if file.is_file() and FRONTEND_BUILD.resolve() in file.parents:
            return FileResponse(file)
        if path.startswith(("scripts", "convert_into_video", "youtube")):     # a mistyped API url must stay a 404, not a web page
            raise HTTPException(404, "not found")
        return FileResponse(FRONTEND_BUILD / "index.html")
