import asyncio
import logging
import mimetypes
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import database as db
import storage
import video_service
from BaseState import BaseState
from config import IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET
from edges import build_graph

log = logging.getLogger("api")
graph = None
RECURSION_LIMIT = 2000
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    await db.init_db()
    await db.reset_interrupted_jobs()
    graph = build_graph()
    yield


app = FastAPI(title="Script to video", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # tighten for production

_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    """Run a coroutine in the background (kept referenced so it is not garbage collected)."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# ── schemas ───────────────────────────────────────────────────────────────────
class ScriptCreate(BaseModel):
    user_prompt: str = Field(min_length=3)
    estimated_duration_in_hours: float = Field(gt=0)
    words_per_minute: int = Field(default=150, ge=60, le=300)
    total_sections: int | None = Field(default=None, ge=1, le=200)
    voice_model: str = "af_heart"
    video_type: Literal["facts", "story"] | None = None
    similarity_threshold: float | None = Field(default=None, gt=0, le=1)
    auto_render: bool = True              # build each section's video as soon as the script is written


class ScriptUpdate(BaseModel):
    voice_model: str | None = None
    words_per_minute: int | None = Field(default=None, ge=60, le=300)


class SectionCreate(BaseModel):
    text: str = Field(min_length=1)
    position: int | None = Field(default=None, ge=1)     # default: add at the end


class SectionUpdate(BaseModel):
    text: str = Field(min_length=1)


class RewriteIn(BaseModel):
    instruction: str = Field(min_length=1)               # "make it funnier", "shorter", ...


class SectionOut(BaseModel):
    position: int
    text: str
    word_count: int
    image_prompt: str | None
    image_url: str | None
    audio_url: str | None
    video_url: str | None                 # last finished video (may be older than the text while video_status != ready)
    video_status: str                     # pending | processing | ready | failed
    video_error: str | None
    updated_at: datetime | None


class FinalVideoOut(BaseModel):
    status: str                           # none | processing | ready | outdated | failed
    url: str | None
    error: str | None


class ScriptOut(BaseModel):
    id: uuid.UUID
    user_prompt: str
    video_type: str | None
    voice_model: str | None
    words_per_minute: int
    estimated_duration_in_hours: float
    total_sections: int | None
    sections_completed: int | None
    generation_status: str                # generating | ready | failed
    generation_error: str | None
    final_video: FinalVideoOut
    created_at: datetime | None
    updated_at: datetime | None


async def section_out(s: db.Section) -> SectionOut:
    image, audio, video = await asyncio.gather(
        storage.url(IMAGES_BUCKET, s.image_path), storage.url(AUDIOS_BUCKET, s.audio_path),
        storage.url(VIDEOS_BUCKET, s.video_path))
    return SectionOut(position=s.position, text=s.text, word_count=s.word_count, image_prompt=s.image_prompt,
                      image_url=image, audio_url=audio, video_url=video, video_status=s.video_status,
                      video_error=s.video_error, updated_at=s.updated_at)


async def script_out(s: db.State) -> ScriptOut:
    return ScriptOut(
        id=s.id, user_prompt=s.user_prompt, video_type=s.video_type, voice_model=s.voice_model,
        words_per_minute=s.words_per_minute, estimated_duration_in_hours=s.estimated_duration_in_hours,
        total_sections=s.total_sections, sections_completed=s.sections_completed,
        generation_status=s.generation_status, generation_error=s.generation_error,
        final_video=FinalVideoOut(status=s.final_video_status, url=await storage.url(VIDEOS_BUCKET, s.final_video_path),
                                  error=s.final_video_error),
        created_at=s.created_at, updated_at=s.updated_at)


# ── helpers ───────────────────────────────────────────────────────────────────
async def _script_or_404(script_id: uuid.UUID) -> db.State:
    state = await db.get_state(script_id)
    if state is None:
        raise HTTPException(404, "script not found")
    return state


async def _section_or_404(script_id: uuid.UUID, position: int) -> db.Section:
    section = await db.get_section(script_id, position)
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    return section


def _state_from_row(row: db.State, **update) -> BaseState:
    values = {name: getattr(row, name) for name in BaseState.model_fields if getattr(row, name) is not None}
    return BaseState(**values).model_copy(update=update)


async def _delete_files(files: dict[str, list[str]]) -> None:
    for bucket, paths in files.items():
        await storage.delete_quiet(bucket, paths)


async def _section_changed(script_id: uuid.UUID, section_id: uuid.UUID) -> None:
    """The final video is out of date and this section's video has to be rebuilt."""
    await db.mark_final_outdated(script_id)
    spawn(video_service.render_section_video(section_id))


async def _run_graph(base: BaseState) -> None:
    await graph.ainvoke(base, {"recursion_limit": RECURSION_LIMIT})


async def _generation_job(base: BaseState, auto_render: bool) -> None:
    """Writes all sections (the caller has already claimed generation_status='generating')."""
    try:
        await _run_graph(base)
    except Exception as exc:
        log.exception("generation failed for %s", base.id)
        await db.set_state_fields(base.id, generation_status="failed", generation_error=f"{type(exc).__name__}: {exc}"[:500])
        return
    await db.set_state_fields(base.id, generation_status="ready")
    if auto_render:
        await video_service.render_all_pending(base.id)


# ── scripts ───────────────────────────────────────────────────────────────────
@app.post("/scripts", response_model=ScriptOut, status_code=202)
async def create_script(body: ScriptCreate):
    """Starts writing the sections in the background. Poll GET /scripts/{id} and GET /scripts/{id}/sections."""
    base = BaseState(
        user_prompt=body.user_prompt, estimated_duration_in_hours=body.estimated_duration_in_hours,
        words_per_minute=body.words_per_minute, total_sections=body.total_sections, voice_model=body.voice_model,
        video_type=body.video_type, similarity_threshold=body.similarity_threshold, sections_completed=0)
    await db.save_state(base, {})
    await db.set_state_fields(base.id, generation_status="generating", generation_error=None)
    spawn(_generation_job(base, body.auto_render))
    return await script_out(await _script_or_404(base.id))


@app.get("/scripts", response_model=list[ScriptOut])
async def list_scripts(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return [await script_out(s) for s in await db.list_states(limit, offset)]


@app.get("/scripts/{script_id}", response_model=ScriptOut)
async def get_script(script_id: uuid.UUID):
    return await script_out(await _script_or_404(script_id))


@app.patch("/scripts/{script_id}", response_model=ScriptOut)
async def update_script(script_id: uuid.UUID, body: ScriptUpdate):
    """Changing the voice or speaking speed rebuilds every section video."""
    state = await _script_or_404(script_id)
    changes = body.model_dump(exclude_none=True)
    changes = {k: v for k, v in changes.items() if getattr(state, k) != v}
    if changes:
        await db.set_state_fields(script_id, **changes)
        await db.mark_all_sections_changed(script_id)
        await db.mark_final_outdated(script_id)
        spawn(video_service.render_all_pending(script_id))
    return await script_out(await _script_or_404(script_id))


@app.post("/scripts/{script_id}/generate", response_model=ScriptOut, status_code=202)
async def resume_generation(script_id: uuid.UUID, auto_render: bool = True):
    """Continue writing a script whose generation failed or was interrupted."""
    state = await _script_or_404(script_id)
    if not await db.claim_generation(script_id):
        raise HTTPException(409, "the script is already being generated")
    spawn(_generation_job(_state_from_row(state), auto_render))
    return await script_out(await _script_or_404(script_id))


@app.delete("/scripts/{script_id}", status_code=204)
async def delete_script(script_id: uuid.UUID):
    """Deletes the script, its sections, and every image, audio and video file stored for it."""
    state = await _script_or_404(script_id)
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is being generated, try again when it is done")
    files = await db.delete_state(script_id)
    if files:
        await _delete_files(files)


# ── sections ──────────────────────────────────────────────────────────────────
@app.get("/scripts/{script_id}/sections", response_model=list[SectionOut])
async def list_sections(script_id: uuid.UUID):
    await _script_or_404(script_id)
    return [await section_out(s) for s in await db.load_sections(script_id)]


@app.get("/scripts/{script_id}/sections/{position}", response_model=SectionOut)
async def get_section(script_id: uuid.UUID, position: int):
    return await section_out(await _section_or_404(script_id, position))


@app.post("/scripts/{script_id}/sections", response_model=SectionOut, status_code=201)
async def add_section(script_id: uuid.UUID, body: SectionCreate):
    """Add a section you wrote yourself (at the end, or at `position`, pushing the others down)."""
    from nodes import embed, suggest_image_prompt
    state = await _script_or_404(script_id)
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is being generated, try again when it is done")
    count = await db.count_sections(script_id)
    position = body.position or count + 1
    if position > count + 1:
        raise HTTPException(422, f"position must be between 1 and {count + 1}")
    text = body.text.strip()
    embedding, image_prompt = await asyncio.gather(embed(text), suggest_image_prompt(text))
    section = await db.insert_section(script_id, position, text=text, word_count=len(text.split()),
                                      embedding=embedding, image_prompt=image_prompt)
    await _section_changed(script_id, section.id)
    return await section_out(section)


@app.patch("/scripts/{script_id}/sections/{position}", response_model=SectionOut)
async def edit_section(script_id: uuid.UUID, position: int, body: SectionUpdate):
    """Write the section text yourself. Its video is rebuilt."""
    from nodes import embed, suggest_image_prompt
    await _section_or_404(script_id, position)
    text = body.text.strip()
    embedding, image_prompt = await asyncio.gather(embed(text), suggest_image_prompt(text))
    section = await db.update_section_content(script_id, position, text=text, word_count=len(text.split()),
                                              embedding=embedding, image_prompt=image_prompt)
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    await _section_changed(script_id, section.id)
    return await section_out(section)


@app.post("/scripts/{script_id}/sections/{position}/rewrite", response_model=SectionOut)
async def rewrite_section(script_id: uuid.UUID, position: int, body: RewriteIn):
    """Have the LangGraph rewrite this one section from an instruction. Its video is rebuilt."""
    state = await _script_or_404(script_id)
    section = await _section_or_404(script_id, position)
    count = await db.count_sections(script_id)
    if not await db.claim_generation(script_id):
        raise HTTPException(409, "the script is being generated, try again when it is done")
    try:
        base = _state_from_row(
            state, user_prompted_sectional_changes={position: body.instruction.strip()},
            sections_completed=count, total_sections=count, generator_response=None, generated_response_title=None,
            generated_response_word_count=None, similarity_score=None, current_section=None, next_step=None,
            rewrite_attempts=0)
        await _run_graph(base)
    except Exception as exc:
        log.exception("rewrite failed for %s section %s", script_id, position)
        await db.set_state_fields(script_id, generation_status="ready")
        raise HTTPException(502, f"rewrite failed: {type(exc).__name__}: {exc}")
    await db.set_state_fields(script_id, generation_status="ready")
    section = await _section_or_404(script_id, position)
    await _section_changed(script_id, section.id)
    return await section_out(section)


@app.put("/scripts/{script_id}/sections/{position}/image", response_model=SectionOut)
async def set_section_image(script_id: uuid.UUID, position: int, file: UploadFile = File(...)):
    """Upload (or replace) the image for a section. Its video is rebuilt with the new image."""
    section = await _section_or_404(script_id, position)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(415, f"use one of: {', '.join(sorted(IMAGE_EXTENSIONS))}")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(422, "empty file")

    path = f"{script_id}/{section.id}-{uuid.uuid4().hex[:8]}{suffix}"
    await storage.upload_bytes(IMAGES_BUCKET, path, data, mimetypes.guess_type(path)[0] or "application/octet-stream")
    updated = await db.update_section_content(script_id, position, image_path=path)
    if updated is None:                                    # deleted while uploading
        await storage.delete_quiet(IMAGES_BUCKET, [path])
        raise HTTPException(404, f"section {position} not found")
    await storage.delete_quiet(IMAGES_BUCKET, [section.image_path])
    await _section_changed(script_id, updated.id)
    return await section_out(updated)


@app.delete("/scripts/{script_id}/sections/{position}/image", response_model=SectionOut)
async def remove_section_image(script_id: uuid.UUID, position: int):
    """Remove the image (the video goes back to a plain dark card) and delete the file."""
    section = await _section_or_404(script_id, position)
    updated = await db.update_section_content(script_id, position, image_path=None)
    await storage.delete_quiet(IMAGES_BUCKET, [section.image_path])
    await _section_changed(script_id, updated.id)
    return await section_out(updated)


@app.post("/scripts/{script_id}/sections/{position}/render", response_model=SectionOut, status_code=202)
async def rerender_section(script_id: uuid.UUID, position: int):
    """Force a rebuild of this section's video (e.g. after a failure)."""
    section = await _section_or_404(script_id, position)
    updated = await db.update_section_content(script_id, position)     # bumps the revision, status -> pending
    await _section_changed(script_id, section.id)
    return await section_out(updated)


@app.delete("/scripts/{script_id}/sections/{position}", status_code=204)
async def delete_section(script_id: uuid.UUID, position: int):
    """Deletes the section and its image, audio and video files; later sections move up by one."""
    state = await _script_or_404(script_id)
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is being generated, try again when it is done")
    section = await db.delete_section(script_id, position)
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    await _delete_files({IMAGES_BUCKET: [section.image_path], AUDIOS_BUCKET: [section.audio_path],
                         VIDEOS_BUCKET: [section.video_path]})
    await db.mark_final_outdated(script_id)


# ── the final video ───────────────────────────────────────────────────────────
@app.post("/convert_into_video/{script_id}", response_model=ScriptOut, status_code=202)
async def convert_into_video(script_id: uuid.UUID):
    """Stitches the per-section videos into one video (rebuilding any section video that is out of date first).
    Runs in the background: poll GET /scripts/{id}/video until status is 'ready'."""
    state = await _script_or_404(script_id)
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is still being written")
    if await db.count_sections(script_id) == 0:
        raise HTTPException(409, "the script has no sections")
    if not await db.claim_final_video(script_id):
        raise HTTPException(409, "the video is already being built")
    spawn(video_service.convert_into_video(script_id))
    return await script_out(await _script_or_404(script_id))


@app.get("/scripts/{script_id}/video", response_model=FinalVideoOut)
async def get_final_video(script_id: uuid.UUID):
    return (await script_out(await _script_or_404(script_id))).final_video


@app.delete("/scripts/{script_id}/video", status_code=204)
async def delete_final_video(script_id: uuid.UUID):
    """Deletes the stitched video file (the section videos stay)."""
    state = await _script_or_404(script_id)
    if state.final_video_status == "processing":
        raise HTTPException(409, "the video is being built")
    old = await db.clear_final_video(script_id)
    await storage.delete_quiet(VIDEOS_BUCKET, [old])
