"""Render section videos and stitch them into a final video."""
import asyncio
import logging
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from sqlalchemy import select, update

import memory
import database.storage as storage
from config import OUTPUT_DIR, IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET
from database.initialization import SessionLocal
from database.models import Section, State
from media.voice import DEFAULT_VOICE, build_image_video, generate_voiceover

log = logging.getLogger("video_service")
_render_lock = asyncio.Lock()


def _scratch_dir() -> Path:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="job-", dir=OUTPUT_DIR))


def _run_ffmpeg(*args: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-300:]}")


def _make_section_audio(
    text: str,
    words_per_minute: int,
    voice_model: str | None,
    folder: Path,
) -> tuple[Path, dict]:
    audio = folder / "section.mp3"
    result = generate_voiceover(
        text,
        audio,
        target_wpm=words_per_minute,
        voice_model=voice_model or DEFAULT_VOICE,
    )
    return audio, result


def _stitch(files: list[Path], output: Path) -> None:
    lines = []
    for file in files:
        path = file.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{path}'")
    list_file = output.with_suffix(".txt")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _run_ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-movflags", "+faststart", str(output),
    )


async def render_section_video(section_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        section = await session.get(Section, section_id)
    if section is None or section.video_status == "ready":
        return

    revision = section.content_rev
    async with SessionLocal() as session:
        claimed = (
            await session.execute(
                update(Section)
                .where(
                    Section.id == section_id,
                    Section.content_rev == revision,
                    Section.video_status != "processing",
                )
                .values(video_status="processing", video_error=None)
                .returning(Section.id)
            )
        ).scalar_one_or_none()
        await session.commit()
    if claimed is None:
        return

    async with _render_lock:
        async with SessionLocal() as session:
            section = await session.get(Section, section_id)
            state = await session.get(State, section.state_id) if section else None

        if (
            section is None
            or state is None
            or section.content_rev != revision
            or section.video_status == "ready"
        ):
            return

        folder = _scratch_dir()
        uploaded_audio_path = None
        uploaded_video_path = None
        uploaded_credits_path = None
        uploaded_subtitle_path = None
        uncommitted_asset_paths: list[str] = []
        try:
            if not section.image_path:
                raise RuntimeError(
                    "This section has no image yet. Reroll the image or upload your own before rendering."
                )
            single_image = await storage.download_to(
                IMAGES_BUCKET,
                section.image_path,
                folder / f"section-image{Path(section.image_path).suffix or '.jpg'}",
            )
            heading_label = "Fact" if state.video_type == "facts" else "Chapter"
            heading_text = f"{heading_label} {section.position}: {section.title or 'Untitled'}"
            spoken_text = f"{heading_text}. {section.text}"

            async with memory.heavy:
                memory.report(f"narration start (section {section.position})")
                audio, voice_timing = await asyncio.to_thread(
                    _make_section_audio,
                    spoken_text,
                    state.words_per_minute,
                    state.voice_model,
                    folder,
                )
                video = folder / "section.mp4"
                memory.report(f"still-image title-card render start (section {section.position})")
                await asyncio.to_thread(
                    build_image_video,
                    single_image,
                    audio,
                    video,
                    voice_timing["duration_sec"],
                    title_label=f"{heading_label.upper()} {section.position}:",
                    title=section.title or "Untitled",
                )
                memory.report(f"section render done (section {section.position})")

            audio_path = f"{state.id}/{section.id}-{revision}.mp3"
            video_path = f"{state.id}/{section.id}-{revision}.mp4"
            credits_file = video.with_suffix(".credits.md")
            subtitle_file = video.with_suffix(".srt")
            credits_path = f"{state.id}/{section.id}-{revision}-credits.md" if credits_file.is_file() else None
            subtitle_path = f"{state.id}/{section.id}-{revision}.srt" if subtitle_file.is_file() else None

            await storage.upload_file(AUDIOS_BUCKET, audio_path, audio, "audio/mpeg")
            uploaded_audio_path = audio_path
            await storage.upload_file(VIDEOS_BUCKET, video_path, video, "video/mp4")
            uploaded_video_path = video_path
            if credits_path:
                await storage.upload_file(VIDEOS_BUCKET, credits_path, credits_file, "text/markdown")
                uploaded_credits_path = credits_path
            if subtitle_path:
                await storage.upload_file(VIDEOS_BUCKET, subtitle_path, subtitle_file, "application/x-subrip")
                uploaded_subtitle_path = subtitle_path

            async with SessionLocal() as session:
                async with session.begin():
                    current = await session.get(Section, section_id, with_for_update=True)
                    if current is None or current.content_rev != revision:
                        old = None
                    else:
                        old = (current.audio_path, current.video_path, current.credits_path, current.subtitle_path)
                        current.audio_path = audio_path
                        current.video_path = video_path
                        current.credits_path = credits_path
                        current.subtitle_path = subtitle_path
                        current.video_status = "ready"
                        current.video_error = None

            if old is None:
                await storage.delete_quiet(AUDIOS_BUCKET, [audio_path])
                await storage.delete_quiet(VIDEOS_BUCKET, [video_path, credits_path, subtitle_path])
            else:
                if old[0] and old[0] != audio_path:
                    await storage.delete_quiet(AUDIOS_BUCKET, [old[0]])
                stale_video_assets = [old_path for old_path in old[1:] if old_path and old_path not in {video_path, credits_path, subtitle_path}]
                await storage.delete_quiet(VIDEOS_BUCKET, stale_video_assets)
        except Exception as exc:
            log.exception("render failed for section %s", section_id)
            if uncommitted_asset_paths:
                await storage.delete_quiet(IMAGES_BUCKET, uncommitted_asset_paths)
            if uploaded_audio_path:
                await storage.delete_quiet(AUDIOS_BUCKET, [uploaded_audio_path])
            if any((uploaded_video_path, uploaded_credits_path, uploaded_subtitle_path)):
                await storage.delete_quiet(VIDEOS_BUCKET, [uploaded_video_path, uploaded_credits_path, uploaded_subtitle_path])
            async with SessionLocal() as session:
                await session.execute(
                    update(Section)
                    .where(Section.id == section_id, Section.content_rev == revision)
                    .values(
                        video_status="failed",
                        # Preserve the traceback tail; it contains the underlying worker exception.
                        video_error=f"{type(exc).__name__}: {exc}"[-2000:],
                    )
                )
                await session.commit()
        finally:
            shutil.rmtree(folder, ignore_errors=True)


_batch_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}


async def _render_all_pending(script_id: uuid.UUID) -> None:
    """Wait for in-flight scenes, then sequentially render every remaining section."""
    async with SessionLocal() as session:
        section_ids = list((
            await session.execute(
                select(Section.id)
                .where(Section.state_id == script_id)
                .order_by(Section.position)
            )
        ).scalars())

    for section_id in section_ids:
        wait_started = time.monotonic()
        while True:
            async with SessionLocal() as session:
                status = await session.scalar(
                    select(Section.video_status).where(Section.id == section_id)
                )
            if status is None or status != "processing":
                break
            if time.monotonic() - wait_started > 3600:
                raise TimeoutError(f"section render {section_id} remained processing for over one hour")
            await asyncio.sleep(1)

        if status != "ready":
            await render_section_video(section_id)


def _forget_batch_task(script_id: uuid.UUID, task: asyncio.Task[None]) -> None:
    if _batch_tasks.get(script_id) is task:
        _batch_tasks.pop(script_id, None)


async def render_all_pending(script_id: uuid.UUID) -> None:
    task = _batch_tasks.get(script_id)
    if task is None:
        task = asyncio.create_task(_render_all_pending(script_id))
        _batch_tasks[script_id] = task
        task.add_done_callback(
            lambda finished: _forget_batch_task(script_id, finished)
        )
    await asyncio.shield(task)


async def convert_into_video(script_id: uuid.UUID) -> None:
    folder = _scratch_dir()
    try:
        await render_all_pending(script_id)

        async with SessionLocal() as session:
            sections = list((
                await session.execute(
                    select(Section)
                    .where(Section.state_id == script_id)
                    .order_by(Section.position)
                )
            ).scalars())

        if not sections:
            raise RuntimeError("the script has no sections")

        for section in sections:
            if section.video_status != "ready" or not section.video_path:
                raise RuntimeError(
                    f"section {section.position} has no finished video "
                    f"({section.video_status}: {section.video_error})"
                )

        snapshot = [(section.id, section.content_rev) for section in sections]
        files = [
            await storage.download_to(
                VIDEOS_BUCKET,
                section.video_path,
                folder / f"{section.position:04d}.mp4",
            )
            for section in sections
        ]
        final = folder / "final.mp4"
        await asyncio.to_thread(_stitch, files, final)

        path = f"{script_id}/final-{uuid.uuid4().hex[:8]}.mp4"
        await storage.upload_file(VIDEOS_BUCKET, path, final, "video/mp4")

        async with SessionLocal() as session:
            async with session.begin():
                state = await session.get(State, script_id, with_for_update=True)
                if state is None:
                    applied, old_path = False, None
                else:
                    current_sections = (
                        await session.execute(
                            select(Section.id, Section.content_rev)
                            .where(Section.state_id == script_id)
                            .order_by(Section.position)
                        )
                    ).all()
                    unchanged = (
                        [tuple(row) for row in current_sections]
                        == [tuple(item) for item in snapshot]
                    )
                    old_path = state.final_video_path
                    state.final_video_path = path
                    state.final_video_status = "ready" if unchanged else "outdated"
                    state.final_video_error = None
                    applied = True

        await storage.delete_quiet(
            VIDEOS_BUCKET, [old_path] if applied else [path]
        )
    except Exception as exc:
        log.exception("final video failed for %s", script_id)
        async with SessionLocal() as session:
            await session.execute(
                update(State)
                .where(State.id == script_id)
                .values(
                    final_video_status="failed",
                    # Preserve the traceback tail so the actual failure is visible in the UI.
                    final_video_error=f"{type(exc).__name__}: {exc}"[-2000:],
                )
            )
            await session.commit()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
