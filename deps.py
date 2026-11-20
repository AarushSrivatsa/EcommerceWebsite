"""Shared FastAPI dependencies and background task management."""
import asyncio
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import select, update

import memory
import database.storage as storage
from aiagent.BaseState import BaseState
from database.initialization import SessionLocal
from database.models import Section, State

log = logging.getLogger("api")

RECURSION_LIMIT = 2000
GENERATION_TIMEOUT = 45 * 60
graph = None
_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def script_or_404(script_id: uuid.UUID) -> State:
    async with SessionLocal() as session:
        state = await session.get(State, script_id)
    if state is None:
        raise HTTPException(404, "script not found")
    return state


async def section_or_404(script_id: uuid.UUID, position: int) -> Section:
    async with SessionLocal() as session:
        section = (
            await session.execute(
                select(Section).where(
                    Section.state_id == script_id,
                    Section.position == position,
                )
            )
        ).scalar_one_or_none()
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    return section


def require_idle(state: State) -> None:
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is being generated, try again when it is done")


async def delete_files(files: dict[str, list[str]]) -> None:
    for bucket, paths in files.items():
        await storage.delete_quiet(bucket, paths)


def state_from_row(row: State, **changes) -> BaseState:
    values = {
        name: getattr(row, name)
        for name in BaseState.model_fields
        if getattr(row, name) is not None
    }
    return BaseState(**values).model_copy(update=changes)


async def run_graph(base: BaseState) -> None:
    await graph.ainvoke(base, {"recursion_limit": RECURSION_LIMIT})


async def generation_job(base: BaseState) -> None:
    memory.report(f"generation start ({base.id})")
    try:
        await asyncio.wait_for(run_graph(base), GENERATION_TIMEOUT)
    except Exception as exc:
        log.exception("generation failed for %s", base.id)
        error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        async with SessionLocal() as session:
            await session.execute(
                update(State)
                .where(State.id == base.id)
                .values(generation_status="failed", generation_error=error[:500])
            )
            await session.commit()
        return

    async with SessionLocal() as session:
        await session.execute(
            update(State)
            .where(State.id == base.id)
            .values(generation_status="ready")
        )
        await session.commit()
