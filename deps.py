"""Helpers every router uses: lookups that 404, background jobs, and the LangGraph instance."""
import asyncio
import logging
import secrets
import uuid

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBasic, HTTPBasicCredentials

import database as db
import storage
import video_service
from BaseState import BaseState
from config import API_KEY

log = logging.getLogger("api")

RECURSION_LIMIT = 2000
graph = None                       # set once at startup by main.py (deps.graph = build_graph())

_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    """Run a coroutine in the background (kept referenced so it is not garbage collected)."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# ── access control ────────────────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)    # also gives /docs an Authorize button
_basic = HTTPBasic(auto_error=False)


def _same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode(), b.encode())


async def require_api_key(key: str | None = Security(_api_key_header),
                          basic: HTTPBasicCredentials | None = Security(_basic)) -> None:
    """The API key can come as the X-API-Key header (scripts, curl) or as the password of the browser's
    login box (the website: the 401 below makes the browser ask once, then it remembers).
    With no API_KEY configured on the server, nothing gets in."""
    if not API_KEY:
        raise HTTPException(503, "API_KEY is not set on the server")
    if (key and _same(key, API_KEY)) or (basic and _same(basic.password, API_KEY)):
        return
    raise HTTPException(401, "missing or wrong API key", headers={"WWW-Authenticate": 'Basic realm="Script to video"'})


# ── lookups ───────────────────────────────────────────────────────────────────
async def script_or_404(script_id: uuid.UUID) -> db.State:
    state = await db.get_state(script_id)
    if state is None:
        raise HTTPException(404, "script not found")
    return state


async def section_or_404(script_id: uuid.UUID, position: int) -> db.Section:
    section = await db.get_section(script_id, position)
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    return section


def require_idle(state: db.State) -> None:
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is being generated, try again when it is done")


# ── storage + rendering ───────────────────────────────────────────────────────
async def delete_files(files: dict[str, list[str]]) -> None:
    for bucket, paths in files.items():
        await storage.delete_quiet(bucket, paths)


async def section_changed(script_id: uuid.UUID, section_id: uuid.UUID) -> None:
    """The final video is out of date and this section's video has to be rebuilt."""
    await db.mark_final_outdated(script_id)
    spawn(video_service.render_section_video(section_id))


# ── LangGraph ─────────────────────────────────────────────────────────────────
def state_from_row(row: db.State, **update) -> BaseState:
    values = {name: getattr(row, name) for name in BaseState.model_fields if getattr(row, name) is not None}
    return BaseState(**values).model_copy(update=update)


async def run_graph(base: BaseState) -> None:
    await graph.ainvoke(base, {"recursion_limit": RECURSION_LIMIT})


async def generation_job(base: BaseState, auto_render: bool) -> None:
    """Writes all sections (the caller has already claimed generation_status='generating')."""
    try:
        await run_graph(base)
    except Exception as exc:
        log.exception("generation failed for %s", base.id)
        await db.set_state_fields(base.id, generation_status="failed", generation_error=f"{type(exc).__name__}: {exc}"[:500])
        return
    await db.set_state_fields(base.id, generation_status="ready")
    if auto_render:
        await video_service.render_all_pending(base.id)