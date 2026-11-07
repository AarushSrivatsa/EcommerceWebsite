"""The super robot: starts the app and plugs and the combines the router mini lion robots together."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import database as db
import deps
from edges import build_graph
from routers import final_video, images, scripts, sections

"""
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀   ⣴⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀   ⠠⡀⠀⠀⠈⠛⠁⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀   ⢀⡀⠀⠀⠀⠹⣷⣦⣤⣠⣤⣴⣾⣿⣆⠀⠀⠀⠀⠀⠀
⠀⠀⠀ ⢀⣤⣶⣿⣿⣿⣿⣷⣦⡀⠈⠙⠻⠿⠿⠿⠿⠟⠛⠁⠀⠀⠀⠀⠀
⠀⠀⠀ ⠙⣿⣿⡿⠛⠛⠛⢿⣿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀ ⠘⠃⠀⠀⠀⠀ ⢀⣿⣿⡇⠀⠀⠀⢀⣴⣾⣿⣿⣿⣷⣦⡀⠀⠀
⠀⠀⠀⠀⠀⠀⠀  ⢰⣶⣶⣿⡿⠏⠀⠀⠀⣠⣾⣿⣿⡿⠟⠛⠿⣿⣿⡄⠀
⠀⠀⠀⠀⠀⠀⠀ ⠘⣿⣿⣿⣶⣤⣀⣠⣴⣿⣿⣿⡟⠁⠀⠀⠀ ⠹⣿⣿⠀
⠐⡄⠀⠀⠀⠀⠀⠀⠀⠀  ⠙⢿⣿⣿⠻⢿⣿⠿⠛⠀⠀⠀   ⢀⣿⣿⠇
⠀⢿⣄⠀⠀⠀⠀⠀⠀⠀⠀  ⣸⣿⡿⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀  ⣼⣿⣿⠀
⠀⠈⢿⣿⣶⣤⣀⣀⣀⣠⣴⣿⣿⠇⠀⠀⠹⣶⣦⣄⣀⣀⣠⣾⣿⣿⠇⠀
⠀⠀⠀⠙⢿⣿⣿⣿⣿⣿⣿⠟⠁⠀⠀⠀⠀ ⠙⠿⣿⣿⣿⣿⣿⡿⠋⠀⠀
⠀⠀⠀⠀⠀⠀⠈⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀   ⠈⠉⠉⠀⠀⠀⠀⠀
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await db.reset_interrupted_jobs()
    deps.graph = build_graph()
    yield


app = FastAPI(title="Script to video", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # tighten for production



@app.get("/health", include_in_schema=False)
async def health():
    """For Render's health check. Needs no API key (neither does the website itself: it is only html and js)."""
    return {"status": "ok"}


protected = [Depends(deps.require_api_key)]
app.include_router(scripts.router, dependencies=protected)
app.include_router(sections.router, dependencies=protected)
app.include_router(images.router, dependencies=protected)
app.include_router(final_video.router, dependencies=protected)


# ── the website: the built Vue app (frontend/dist), served by this same app ────
SITE = Path(__file__).parent / "frontend" / "dist"

if SITE.is_dir():                      # missing while developing; run `npm run build` in frontend/ or use `npm run dev`
    @app.get("/{path:path}", include_in_schema=False)
    async def website(path: str):
        """A real file from the build (js, css, images), otherwise index.html so Vue's router handles the page."""
        file = (SITE / path).resolve()
        if file.is_file() and SITE.resolve() in file.parents:
            return FileResponse(file)
        if path.startswith(("scripts", "convert_into_video")):     # a mistyped API url must stay a 404, not a web page
            raise HTTPException(404, "not found")
        return FileResponse(SITE / "index.html")
