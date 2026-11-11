"""Builds the videos: one per section (voiceover + its image), then one final video stitched from them.

Kokoro and ffmpeg are heavy, so they run in a thread and one section is rendered at a time. The finished files
live in the Supabase buckets; OUTPUT_DIR is only scratch space for a job and is cleaned up when the job ends.
"""
import asyncio
import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import database as db
import memory
import storage
from config import OUTPUT_DIR, IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET
from voice import DEFAULT_VOICE, VIDEO_SIZE, generate_voiceover

log = logging.getLogger("video_service")

_render_lock = asyncio.Lock()      # one section render at a time


# ── small helpers ─────────────────────────────────────────────────────────────
def _scratch_dir() -> Path:
    """A fresh temporary folder for one job."""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="job-", dir=OUTPUT_DIR))


def _run_ffmpeg(*args: str) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-300:]}")


def _dark_card() -> Path:
    """The picture shown for a section that has no image of its own."""
    card = Path(OUTPUT_DIR) / "dark_card.png"
    if not card.exists():
        card.parent.mkdir(parents=True, exist_ok=True)
        width, height = VIDEO_SIZE
        _run_ffmpeg("-f", "lavfi", "-i", f"color=c=0x101010:s={width}x{height}", "-frames:v", "1", str(card))
    return card


def _make_section_files(text: str, words_per_minute: int, voice_model: str | None,
                        image: Path | None, folder: Path) -> tuple[Path, Path]:
    """Voiceover (mp3) and video (mp4) of one section: the image stays on screen while the text is read."""
    audio, video = folder / "section.mp3", folder / "section.mp4"
    generate_voiceover(
        text, audio,
        target_wpm=words_per_minute,
        voice_model=voice_model or DEFAULT_VOICE,
        image_paths=[image or _dark_card()],
        video_path=video,
    )
    return audio, video


def _stitch(files: list[Path], output: Path) -> None:
    """Joins the section videos in order. They were all encoded the same way, so nothing is re-encoded."""
    lines = []
    for file in files:
        path = file.resolve().as_posix().replace("'", "'\\''")      # how ffmpeg's list format escapes a quote
        lines.append(f"file '{path}'")
    list_file = output.with_suffix(".txt")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _run_ffmpeg("-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", "-movflags", "+faststart", str(output))


# ── one section ───────────────────────────────────────────────────────────────
async def render_section_video(section_id: uuid.UUID) -> None:
    """Builds the voiceover and video of one section and stores them. Calling it twice, or for a section that
    changed or was deleted meanwhile, is safe: the stale work is thrown away."""
    section = await db.get_section_by_id(section_id)
    if section is None or section.video_status == "ready":
        return
    rev = section.content_rev
    if not await db.set_section_processing(section_id, rev):
        return                                                   # it changed since: a newer call handles it

    async with _render_lock:
        section = await db.get_section_by_id(section_id)         # it may have waited here a while
        if section is None or section.content_rev != rev or section.video_status == "ready":
            return
        state = await db.get_state(section.state_id)
        if state is None:
            return

        folder = _scratch_dir()
        try:
            image = None
            if section.image_path:
                image = await storage.download_to(
                    IMAGES_BUCKET, section.image_path, folder / f"image{Path(section.image_path).suffix}")

            async with memory.heavy:                              # the voice model never shares RAM with the embedder
                memory.report(f"render start (section {section.position})")
                audio, video = await asyncio.to_thread(
                    _make_section_files, section.text, state.words_per_minute, state.voice_model, image, folder)
                memory.report(f"render done (section {section.position})")

            audio_path = f"{state.id}/{section.id}-{rev}.mp3"     # the revision in the name: a new render never
            video_path = f"{state.id}/{section.id}-{rev}.mp4"     # overwrites the file the old one points to
            await storage.upload_file(AUDIOS_BUCKET, audio_path, audio, "audio/mpeg")
            await storage.upload_file(VIDEOS_BUCKET, video_path, video, "video/mp4")

            old = await db.finish_section_render(section_id, rev, audio_path, video_path)
            if old is None:                                       # changed or deleted while rendering
                await storage.delete_quiet(AUDIOS_BUCKET, [audio_path])
                await storage.delete_quiet(VIDEOS_BUCKET, [video_path])
            else:                                                 # remove the files of the previous render
                for bucket, old_file, new_file in ((AUDIOS_BUCKET, old[0], audio_path), (VIDEOS_BUCKET, old[1], video_path)):
                    if old_file and old_file != new_file:
                        await storage.delete_quiet(bucket, [old_file])
        except Exception as exc:
            log.exception("render failed for section %s", section_id)
            await db.fail_section_render(section_id, rev, f"{type(exc).__name__}: {exc}"[:500])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


_batches: set[uuid.UUID] = set()


async def render_all_pending(script_id: uuid.UUID) -> None:
    """Renders every section whose video is not up to date, one after another.
    A second call for the same script while one is running does nothing (the first one covers it)."""
    if script_id in _batches:
        return
    _batches.add(script_id)
    try:
        for section in await db.load_sections(script_id):
            if section.video_status != "ready":
                await render_section_video(section.id)
    finally:
        _batches.discard(script_id)


# ── the final video ───────────────────────────────────────────────────────────
async def convert_into_video(script_id: uuid.UUID) -> None:
    """Stitches the section videos into the final video (after rebuilding any that are out of date).
    The caller has already set final_video_status to 'processing'; this ends it as ready, outdated or failed."""
    folder = _scratch_dir()
    try:
        await render_all_pending(script_id)

        sections = await db.load_sections(script_id)
        if not sections:
            raise RuntimeError("the script has no sections")
        for section in sections:
            if section.video_status != "ready":
                raise RuntimeError(f"section {section.position} has no finished video "
                                   f"({section.video_status}: {section.video_error})")
        snapshot = [(section.id, section.content_rev) for section in sections]    # what this video is made from

        files = [await storage.download_to(VIDEOS_BUCKET, section.video_path, folder / f"{section.position:04d}.mp4")
                 for section in sections]
        final = folder / "final.mp4"
        await asyncio.to_thread(_stitch, files, final)

        path = f"{script_id}/final-{uuid.uuid4().hex[:8]}.mp4"
        await storage.upload_file(VIDEOS_BUCKET, path, final, "video/mp4")

        applied, old = await db.finish_final_video(script_id, path, snapshot)   # 'outdated' if a section changed meanwhile
        await storage.delete_quiet(VIDEOS_BUCKET, [old] if applied else [path])
    except Exception as exc:
        log.exception("final video failed for %s", script_id)
        await db.set_state_fields(script_id, final_video_status="failed",
                                  final_video_error=f"{type(exc).__name__}: {exc}"[:500])
    finally:
        shutil.rmtree(folder, ignore_errors=True)
