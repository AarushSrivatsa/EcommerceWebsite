"""The super robot: starts the app and plugs and the combines the router mini lion robots together."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    """For Render's health check. The only route that needs no API key."""
    return {"status": "ok"}


protected = [Depends(deps.require_api_key)]
app.include_router(scripts.router, dependencies=protected)
app.include_router(sections.router, dependencies=protected)
app.include_router(images.router, dependencies=protected)
app.include_router(final_video.router, dependencies=protected)