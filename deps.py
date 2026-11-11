"""Helpers every router uses: lookups that 404, background jobs, and the LangGraph instance."""
import asyncio
import logging
import uuid

from fastapi import HTTPException

import database as db
import memory
import storage
from BaseState import BaseState

log = logging.getLogger("api")

RECURSION_LIMIT = 2000
GENERATION_TIMEOUT = 45 * 60       # seconds; a job that takes longer is marked failed, and "Continue writing" picks it up
graph = None                       # set once at startup by main.py (deps.graph = build_graph())

_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    """Run a coroutine in the background (kept referenced so it is not garbage collected)."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


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


# ── LangGraph ─────────────────────────────────────────────────────────────────
def state_from_row(row: db.State, **update) -> BaseState:
    values = {name: getattr(row, name) for name in BaseState.model_fields if getattr(row, name) is not None}
    return BaseState(**values).model_copy(update=update)


async def run_graph(base: BaseState) -> None:
    await graph.ainvoke(base, {"recursion_limit": RECURSION_LIMIT})


async def generation_job(base: BaseState) -> None:
    """Writes all sections (the caller has already claimed generation_status='generating')."""
    memory.report(f"generation start ({base.id})")
    try:
        await asyncio.wait_for(run_graph(base), GENERATION_TIMEOUT)
    except Exception as exc:
        log.exception("generation failed for %s", base.id)
        await db.set_state_fields(base.id, generation_status="failed", generation_error=(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)[:500])
        return
    await db.set_state_fields(base.id, generation_status="ready")