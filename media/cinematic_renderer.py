"""Free, code-rendered cinematic scenes using the MIT-licensed Cinematic Skill engine.

This is not text-to-video inference. It creates moving camera shots, photo-board scenes,
animated cards and typography from the project's narration, storyboard and optional uploads.
"""
from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from vendor_cinematic_engine import Card, Film, PenMark, Print, Renderer

log = logging.getLogger("cinematic_renderer")

WIDTH, HEIGHT, FPS = 1280, 720, 24
ACCENT = (188, 76, 54)
CREAM = (242, 235, 220)


def _ensure_textures(prep: Path) -> None:
    """Create small procedural board/paper textures locally; no downloads or paid assets."""
    prep.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(41)

    board_path = prep / "cork_dark.png"
    if not board_path.exists():
        noise = rng.normal(0, 4.5, (512, 512, 1))
        base = np.array([37, 31, 27], dtype=np.float32).reshape(1, 1, 3)
        grain = np.repeat(noise, 3, axis=2)
        pixels = np.clip(base + grain, 0, 255).astype(np.uint8)
        Image.fromarray(pixels, "RGB").save(board_path, optimize=True)

    paper_path = prep / "paper.png"
    if not paper_path.exists():
        noise = rng.normal(0, 2.8, (512, 512, 1))
        base = np.array([224, 215, 194], dtype=np.float32).reshape(1, 1, 3)
        pixels = np.clip(base + np.repeat(noise, 3, axis=2), 0, 255).astype(np.uint8)
        Image.fromarray(pixels, "RGB").save(paper_path, optimize=True)


def _paragraphs(text: str) -> list[str]:
    return [
        " ".join(part.split())
        for part in re.split(r"\n\s*\n", text.strip())
        if part.strip()
    ]


def _short_text(value: str, limit: int) -> str:
    clean = " ".join((value or "").split()).strip()
    if len(clean) > limit:
        clean = clean[: limit - 1].rsplit(" ", 1)[0] + "…"
    return clean


def _body_lines(value: str) -> list[str]:
    clean = " ".join((value or "").split()).strip()
    if not clean:
        return ["The narration leads this scene."]
    lines = textwrap.wrap(clean, width=39, max_lines=2, placeholder="…")
    return lines or [clean[:39]]


def _prepare_photos(
    prep: Path,
    image_paths: list[Path | None],
) -> tuple[list[str | None], dict[str, dict[str, int]]]:
    photo_dir = prep / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    photo_keys: list[str | None] = []
    metadata: dict[str, dict[str, int]] = {}

    for index, source in enumerate(image_paths):
        if source is None or not Path(source).is_file():
            photo_keys.append(None)
            continue

        key = f"beat_{index:03d}"
        destination = photo_dir / f"{key}.jpg"
        with Image.open(source) as original:
            image = original.convert("RGB")
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            image.thumbnail((2200, 1600), resampling)
            image.save(destination, "JPEG", quality=88, optimize=True)
            metadata[key] = {"w": image.width, "h": image.height}
        photo_keys.append(key)

    (photo_dir / "meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    return photo_keys, metadata


def _normalise_durations(
    paragraphs: list[str],
    durations: list[float] | None,
    total: float,
) -> list[float]:
    if not paragraphs:
        return [max(total, 0.8)]
    if not durations or len(durations) != len(paragraphs) or sum(durations) <= 0:
        weights = [max(1, len(part.split())) for part in paragraphs]
        denominator = sum(weights)
        return [total * weight / denominator for weight in weights]
    scale = total / sum(durations)
    return [max(0.05, float(value) * scale) for value in durations]


def render_cinematic_video(
    *,
    story_text: str,
    audio_path: Path,
    output_path: Path,
    duration_sec: float,
    paragraph_durations: list[float] | None,
    visual_plan: list[dict] | None,
    image_paths: list[Path | None],
    project_title: str,
    section_position: int,
    video_type: str | None = None,
) -> Path:
    """Render one narration section as a continuous cinematic board move and mux its voiceover."""
    paragraphs = _paragraphs(story_text)
    total_duration = max(0.8, float(duration_sec or 0.8))
    timings = _normalise_durations(paragraphs, paragraph_durations, total_duration)

    if len(image_paths) < len(paragraphs):
        image_paths = list(image_paths) + [None] * (len(paragraphs) - len(image_paths))
    image_paths = image_paths[: len(paragraphs)]

    plan = list(visual_plan or [])
    if len(plan) != len(paragraphs):
        plan = [{} for _ in paragraphs]

    work_dir = Path(output_path).parent / "cinematic-work"
    prep = work_dir / "assets" / "prep"
    _ensure_textures(prep)
    photo_keys, _ = _prepare_photos(prep, image_paths)

    doc = SimpleNamespace(dir=work_dir, prep=prep)
    film = Film(total_duration, fps=FPS, look="wall")
    film.auto_cues = False
    film.auto_whoosh = True
    film.fade_in = min(0.45, total_duration * 0.08)
    film.fade_out = min(1.1, total_duration * 0.12)

    beat_gap = 3900.0
    count = max(1, len(paragraphs))
    first_x = -((count - 1) * beat_gap) / 2
    positions = [first_x + index * beat_gap for index in range(count)]
    elapsed = 0.0
    accent = (190, 80, 52) if video_type == "story" else (178, 153, 94)

    for index, (paragraph, beat, key, x, beat_duration) in enumerate(
        zip(paragraphs, plan, photo_keys, positions, timings)
    ):
        start = elapsed
        end = min(total_duration, elapsed + beat_duration)
        elapsed = end

        narration = " ".join(str(beat.get("narration") or paragraph).split())
        visual = " ".join(str(beat.get("visual") or paragraph).split())
        on_screen = " ".join(str(beat.get("on_screen_text") or "").split())
        title = _short_text(on_screen or narration, 27).upper()
        title = title or f"BEAT {index + 1:02d}"
        body = _body_lines(visual)
        t_in = max(0.0, min(start, max(0.0, total_duration - 0.05)))
        t_out = min(total_duration - 0.1, end + 0.25) if end < total_duration - 0.25 else None

        if key:
            film.add(
                Print(
                    key,
                    x,
                    -420,
                    2300,
                    rot=(-0.45 if index % 2 else 0.35),
                    t_in=t_in,
                    t_out=t_out,
                    label=_short_text(title, 17),
                    paper=False,
                )
            )
            card_y = 1120
            film.add(
                Card(
                    x,
                    card_y,
                    2860,
                    760,
                    t_in=t_in + 0.12,
                    title=title,
                    lines=body,
                    accent=accent,
                    title_size=154,
                    body_size=94,
                )
            )
            film.add(
                PenMark(
                    "underline",
                    x,
                    card_y - 100,
                    1500,
                    t_in=min(total_duration - 0.01, t_in + 0.5),
                    dur=0.45,
                    width=18,
                    rgb=accent,
                    sfx=False,
                )
            )
            camera_y = 240
        else:
            film.add(
                Card(
                    x,
                    0,
                    3000,
                    1640,
                    t_in=t_in,
                    title=title,
                    lines=body,
                    accent=accent,
                    title_size=236,
                    body_size=132,
                )
            )
            film.add(
                PenMark(
                    "underline",
                    x,
                    180,
                    1700,
                    t_in=min(total_duration - 0.01, t_in + 0.55),
                    dur=0.5,
                    width=22,
                    rgb=accent,
                    sfx=False,
                )
            )
            camera_y = 0

        film.shot(t_in, x, camera_y, 0.52, rot=(-0.18 if index % 2 else 0.18))
        if beat_duration > 1.6:
            drift_at = min(end - 0.2, t_in + min(1.1, beat_duration * 0.3))
            if drift_at > t_in + 0.35:
                film.shot(drift_at, x + 120, camera_y - 35, 0.56)

    if not paragraphs:
        film.add(Card(0, 0, 3000, 1600, 0, title="CINEMATIC STORY", lines=[_short_text(project_title, 40)], accent=accent))
        film.shot(0, 0, 0, 0.5)

    # End with a composed pull-back that reveals the whole visual board.
    final_zoom = min(0.48, max(0.12, 3400.0 / (beat_gap * count + 2100.0)))
    film.shot(total_duration, 0, 0, final_zoom, radius=1600 / max(final_zoom, 0.01), strength=0.18)

    width, height, fps = WIDTH, HEIGHT, FPS
    renderer = Renderer(film, width, height, doc)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(math.ceil(total_duration * fps)))
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{width}x{height}", "-framerate", str(fps),
        "-i", "-", "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-threads", "1", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert process.stdin is not None
        for frame_number in range(frame_count):
            process.stdin.write(renderer.frame(frame_number).tobytes())
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        return_code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        raise

    if return_code:
        message = stderr.decode("utf-8", errors="replace").strip()[-1200:]
        raise RuntimeError(f"cinematic FFmpeg render failed: {message}")
    return output_path
