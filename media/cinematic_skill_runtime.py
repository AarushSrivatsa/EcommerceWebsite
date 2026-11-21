"""Run the upstream Cinematic Skill project workflow for one narration section.

This module prepares a real Cinematic Skill project folder and invokes its vendored scripts:
asset grading, optional maps, camera/scene composition, sound-effect generation, soundtrack mix,
full film render, subtitles and image credits. It deliberately does not substitute the old
hand-built-card renderer.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("cinematic_skill")

SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "vendor"
    / "cinematic_skill"
    / "skills"
    / "cinematic-film"
)
SKILL_SCRIPTS = SKILL_ROOT / "scripts"

SCENE_SOURCE = r'''"""Application-generated scene, composed with the upstream Cinematic Skill engine."""
import json
import math
import re
import textwrap
from pathlib import Path

from engine import (
    BigText, Card, Counter, Film, FilmFrame, GeoMap, MapPin,
    PaperDoc, PenMark, Print, Route, Stamp, StringLine,
)

DATA = json.loads((Path(__file__).parent / "scene_data.json").read_text(encoding="utf-8"))
ACCENT = (184, 56, 43)
INK = (34, 31, 28)
CREAM = (242, 235, 220)


def _short(value, limit=30):
    value = " ".join(str(value or "").split())
    if len(value) > limit:
        value = value[:limit - 1].rsplit(" ", 1)[0] + "…"
    return value


def _lines(value, width=35):
    parts = textwrap.wrap(" ".join(str(value or "").split()), width=width, max_lines=2, placeholder="…")
    return parts or ["The narration leads this scene."]


def build_film(doc):
    beats = DATA["beats"]
    look = DATA.get("look", "wall")
    film = Film(doc.duration, fps=30, look=look)
    film.auto_cues = True
    film.auto_whoosh = True
    film.fade_in = 0.75
    film.fade_out = min(2.4, max(0.7, doc.duration * 0.06))

    count = max(1, len(beats))
    gap = 4200.0
    xs = [(index - (count - 1) / 2) * gap for index in range(count)]
    map_data = None
    map_obj = None
    map_names = DATA.get("map_places", [])
    if map_names:
        try:
            map_obj = film.add(GeoMap(doc.map("world"), 6200, origin=(0, 0), look="explainer"))
            map_data = map_obj
        except Exception:
            map_obj = None

    title = _short(DATA.get("title", "CINEMATIC FILM"), 42).upper()
    film.add(BigText(title, 0, -2050, 390, 0.0, rgb=INK, shadow=False, grunge=False, type_on=0.9))
    film.add(PenMark("underline", 0, -1870, min(7000, max(2200, len(title) * 205)), 30,
                     t_in=min(1.0, doc.duration * 0.15), dur=0.65, width=18, rgb=ACCENT))

    if map_obj:
        # Let the viewer understand the geography before travelling to the evidence clusters.
        film.shot(min(1.25, doc.duration * 0.12), 0, 0, 0.14, radius=18000, strength=0.18)
        previous = None
        for place_index, name in enumerate(map_names):
            try:
                point = map_obj.place(name)
            except Exception:
                continue
            at = min(doc.duration - 0.1, 0.9 + place_index * max(0.65, doc.duration / max(2, len(map_names) + 2)))
            film.add(MapPin(point[0], point[1], label=name, t_in=at, label_size=92))
            if previous is not None:
                film.add(Route(previous, point, t_in=max(0.0, at - 0.45), dur=0.85, bend=0.13, width=13))
            previous = point

    previous_anchor = None
    for index, beat in enumerate(beats):
        line_id = int(beat["id"])
        start = float(doc.L(line_id))
        end = float(doc.E(line_id))
        x = xs[index]
        photo_key = beat.get("photo_key")
        hero = _short(beat.get("typed") or beat.get("title") or beat.get("visual"), 25).upper()
        visual = beat.get("visual") or beat.get("narration") or ""
        kind = beat.get("hero_type", "archive")
        image_kind = beat.get("image_kind", "photo")

        # Every beat is a designed cluster: an archive print or an explicitly labelled
        # document recreation, a supporting card, a timed mark and a continuous camera move.
        if photo_key:
            print_item = film.add(Print(
                photo_key, x, -350, 2380,
                rot=(-0.65 if index % 2 else 0.55),
                t_in=max(0.0, start + 0.08),
                t_out=end + 0.65 if end < doc.duration - 0.8 else None,
                label=_short(beat.get("photo_label") or hero, 24),
                paper=(image_kind == "paper"),
            ))
            if kind == "archive":
                film.add(Stamp("ARCHIVE", x + 780, -1120, size=170, rot=-7,
                               t_in=min(doc.duration - 0.1, start + 0.55), rgb=(164, 34, 27)))
                if index % 2 == 0:
                    film.add(FilmFrame(print_item, t_in=min(doc.duration - 0.1, start + 0.35)))
            if kind == "document":
                film.add(Stamp("SOURCE", x + 780, -1120, size=150, rot=-5,
                               t_in=min(doc.duration - 0.1, start + 0.55), rgb=(164, 34, 27)))
        elif kind == "document":
            # This is always labelled as a recreation; it is not presented as a real source document.
            film.add(PaperDoc(
                x, -180, 2300, 3000, rot=(-0.4 if index % 2 else 0.35),
                t_in=max(0.0, start + 0.1),
                header=(("DOCUMENT RECREATION", 150, "cond"),),
                rows=14,
            ))
            film.add(Stamp("RECREATION", x + 750, -1040, size=142, rot=-6,
                           t_in=min(doc.duration - 0.1, start + 0.55), rgb=(164, 34, 27)))
        else:
            # When an archive has no reusable image, use the skill's native diagram/card
            # language rather than pretending that a generated graphic is a real photograph.
            film.add(Card(
                x, -150, 2700, 1500,
                t_in=max(0.0, start + 0.1),
                title=hero or f"BEAT {index + 1:02d}",
                lines=_lines(visual, 34),
                accent=ACCENT,
                title_size=210,
                body_size=116,
            ))

        card_y = 1440
        film.add(Card(
            x + 160, card_y, 2800, 850,
            t_in=min(doc.duration - 0.04, start + 0.22),
            title=hero or f"BEAT {index + 1:02d}",
            lines=_lines(visual, 43),
            accent=ACCENT,
            title_size=146,
            body_size=82,
            rgb=(245, 240, 230),
            text_rgb=INK,
        ))
        if photo_key:
            film.add(StringLine((x + 160, 650), (x + 160, 1010),
                                t_in=min(doc.duration - 0.04, start + 0.38), dur=0.6, sag=0.0, width=11))

        typed = _short(beat.get("on_screen_text"), 32).upper()
        if typed:
            film.add(BigText(typed, x, -1570, 230, min(doc.duration - 0.05, start + 0.25),
                             rgb=INK, shadow=False, grunge=False, type_on=0.42))
        focus_word = beat.get("focus_word") or ""
        if not focus_word:
            words = re.findall(r"[A-Za-z]+", str(beat.get("spoken") or beat.get("narration") or ""))
            focus_word = words[-1] if words else ""
        try:
            hit_time = doc.W(line_id, focus_word) if focus_word else start + (end - start) * 0.68
        except Exception:
            hit_time = start + (end - start) * 0.68
        film.add(PenMark("underline", x, 1700, 1600, 35,
                         t_in=min(doc.duration - 0.03, hit_time), dur=0.55, width=19, rgb=ACCENT))

        counter = beat.get("counter")
        if isinstance(counter, dict) and isinstance(counter.get("value"), (int, float)):
            film.add(Counter(
                x + 1120, 2280, 330, int(counter["value"]),
                min(doc.duration - 0.05, hit_time), dur=0.95,
                prefix=str(counter.get("prefix") or ""),
                suffix=str(counter.get("suffix") or ""),
                caption=_short(counter.get("caption") or "", 24) or None,
                rgb=ACCENT,
            ))

        if previous_anchor is not None:
            film.add(StringLine(previous_anchor, (x - 1120, -350),
                                t_in=max(0.0, start - 0.18), dur=0.9, sag=0.08, width=10))
        previous_anchor = (x - 1120, -350)

        # Land the camera just after the key spoken word, then drift before the next beat.
        focus_t = min(max(start + 0.25, hit_time + 0.18), max(start + 0.25, end - 0.15))
        film.shot(max(0.0, start), x - 120, 120, 0.48, rot=(-0.35 if index % 2 else 0.35),
                  radius=1750, strength=0.38)
        film.shot(min(doc.duration, focus_t), x, 180, 0.66, rot=(0.25 if index % 2 else -0.25),
                  radius=1380, strength=0.52)
        if end - focus_t > 0.55:
            film.shot(max(focus_t + 0.2, end - 0.22), x + 120, 380, 0.56,
                      radius=1950, strength=0.28)

    # A deliberate final pull-back reveals the connected board rather than cutting away.
    final_zoom = max(0.12, min(0.24, 11500 / (gap * count + 5500)))
    film.shot(doc.duration, 0, 0, final_zoom, radius=25000, strength=0.12)
    return film
'''


def _paragraphs(text: str) -> list[str]:
    return [
        " ".join(part.split())
        for part in re.split(r"\n\s*\n", text.strip())
        if part.strip()
    ]


def _run(script: Path, project: Path, *args: str, timeout: int = 3600) -> str:
    command = [sys.executable, str(script), "--project", str(project), *args]
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "MALLOC_ARENA_MAX": "2",
    })
    result = subprocess.run(
        command, cwd=str(SKILL_SCRIPTS), env=env,
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        details = (result.stderr or result.stdout or "script exited without diagnostics").strip()
        raise RuntimeError(f"{script.name} failed: {details[-2200:]}")
    return (result.stdout or "").strip()


def _normalise_durations(durations: list[float] | None, count: int, total: float) -> list[float]:
    if count <= 0:
        return []
    if not durations or len(durations) != count or sum(durations) <= 0:
        return [total / count] * count
    scale = total / sum(durations)
    scaled = [max(0.05, float(value) * scale) for value in durations]
    correction = total / sum(scaled)
    return [value * correction for value in scaled]


def _choose_look(title: str, video_type: str | None) -> str:
    text = title.lower()
    if any(word in text for word in ("product", "launch", "brand", "founder", "company", "business")):
        return "studio"
    if any(word in text for word in ("science", "physics", "engineering", "technology", "computer", "space")):
        return "blueprint"
    if video_type == "story" or any(word in text for word in ("history", "war", "biography", "documentary", "crime")):
        return "wall"
    return "slate"


def _write_project(
    *,
    project: Path,
    story_text: str,
    audio_path: Path,
    duration_sec: float,
    paragraph_durations: list[float] | None,
    visual_plan: list[dict] | None,
    image_paths: list[Path | None],
    project_title: str,
    video_type: str | None,
) -> None:
    import shutil

    paragraphs = _paragraphs(story_text)
    if not paragraphs:
        raise ValueError("Cinematic Skill needs narration paragraphs")
    plan = list(visual_plan or [])
    if len(plan) != len(paragraphs):
        plan = [
            plan[index] if index < len(plan) else {
                "narration": paragraph, "visual": paragraph,
                "image_search_query": paragraph, "hero_type": "archive",
                "image_kind": "photo", "on_screen_text": "",
            }
            for index, paragraph in enumerate(paragraphs)
        ]
    timings = _normalise_durations(paragraph_durations, len(paragraphs), max(0.8, duration_sec))

    audio_dir = project / "audio"
    photo_dir = project / "assets" / "photos"
    out_dir = project / "out"
    for directory in (audio_dir, photo_dir, out_dir):
        directory.mkdir(parents=True, exist_ok=True)
    narration_path = audio_dir / "narration.mp3"
    shutil.copy2(audio_path, narration_path)

    lines, segments, prepared_beats, photos = [], [], [], []
    cursor = 0.0
    for index, (paragraph, beat, duration, image_path) in enumerate(zip(paragraphs, plan, timings, image_paths)):
        line_id = index + 1
        spoken = " ".join(paragraph.split())
        end = min(duration_sec, cursor + duration)
        segment = {
            "id": line_id,
            "take": "T01_section",
            "caption": paragraph,
            "vo": spoken,
            "start": round(cursor, 4),
            "end": round(max(cursor + 0.05, end), 4),
            "gap_after": 0.0,
        }
        segments.append(segment)
        title = " ".join(str(beat.get("on_screen_text") or beat.get("visual") or paragraph).split())[:80]
        photo_key = None
        if image_path is not None and Path(image_path).is_file():
            photo_key = f"P{line_id:02d}"
            suffix = Path(image_path).suffix.lower() or ".jpg"
            filename = f"{photo_key}{suffix}"
            shutil.copy2(image_path, photo_dir / filename)
            photos.append({
                "id": photo_key,
                "what": str(beat.get("visual") or paragraph)[:180],
                "kind": beat.get("image_kind") if beat.get("image_kind") in {"photo", "paper", "doc", "color"} else "photo",
                "file": filename,
                "credit": beat.get("image_credit") or "",
                "license": beat.get("image_license") or "",
                "license_url": beat.get("image_license_url") or "",
                "source": beat.get("image_source_url") or "",
                "license_ok": bool(beat.get("image_license")),
            })
        words = re.findall(r"[A-Za-z]+", spoken)
        lines.append({
            "id": line_id,
            "text": paragraph,
            "spoken": spoken,
            "hero": str(beat.get("visual") or paragraph)[:180],
            "typed": str(beat.get("on_screen_text") or ""),
        })
        prepared_beats.append({
            **beat,
            "id": line_id,
            "title": title,
            "typed": str(beat.get("on_screen_text") or title),
            "spoken": spoken,
            "focus_word": words[-1] if words else "",
            "photo_key": photo_key,
        })
        cursor = end

    (project / "script.json").write_text(json.dumps({
        "title": project_title,
        "takes": [{"take": "T01_section", "lines": lines}],
        "fact_notes": [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "photos.json").write_text(json.dumps({
        "grade": "bw" if video_type == "story" else "natural",
        "photos": photos,
        "recreations": [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (audio_dir / "timing.json").write_text(json.dumps({
        "total_duration": float(duration_sec),
        "segments": segments,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    map_places = []
    for beat in prepared_beats:
        for place in beat.get("map_places", []) if isinstance(beat.get("map_places"), list) else []:
            name = " ".join(str(place).split())
            if name and name not in map_places:
                map_places.append(name)
    (project / "scene_data.json").write_text(json.dumps({
        "title": project_title,
        "look": _choose_look(project_title, video_type),
        "beats": prepared_beats,
        "map_places": map_places[:6],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "scene.py").write_text(SCENE_SOURCE, encoding="utf-8")

    if map_places:
        from media.cinematic_assets import geocode_places

        places = geocode_places(map_places[:6])
        if places:
            (project / "map.json").write_text(json.dumps({
                "maps": [{
                    "name": "world",
                    "source": "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json",
                    "object": "countries",
                    "projection": {"type": "equirect", "lon0": 0, "lat0": 15},
                    "places": places,
                }],
            }, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_commons_credits(script: Path, project: Path) -> str:
    """The upstream Commons CLI uses a required subcommand before its --project flag."""
    command = [sys.executable, str(script), "credits", "--project", str(project)]
    result = subprocess.run(
        command,
        cwd=str(SKILL_SCRIPTS),
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "MALLOC_ARENA_MAX": "2",
        },
    )
    if result.returncode:
        details = (result.stderr or result.stdout or "credits command exited without diagnostics").strip()
        raise RuntimeError(f"fetch_commons.py credits failed: {details[-1800:]}")
    return (result.stdout or "").strip()


def render_full_skill_video(
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
    """Prepare and run the vendored upstream Cinematic Skill, including audio and attribution."""
    audio_path = Path(audio_path).resolve()
    output_path = Path(output_path).resolve()
    project = (output_path.parent / f"cinematic-skill-section-{section_position}").resolve()
    if project.exists():
        shutil.rmtree(project, ignore_errors=True)
    project.mkdir(parents=True, exist_ok=True)
    _write_project(
        project=project,
        story_text=story_text,
        audio_path=audio_path,
        duration_sec=duration_sec,
        paragraph_durations=paragraph_durations,
        visual_plan=visual_plan,
        image_paths=image_paths,
        project_title=project_title,
        video_type=video_type,
    )

    # Run the upstream asset and scene workflow as separate bounded processes. Only one
    # full engine render worker is used on Render's small RAM plan.
    get_fonts = SKILL_SCRIPTS / "get_fonts.py"
    prep_assets = SKILL_SCRIPTS / "prep_assets.py"
    make_map = SKILL_SCRIPTS / "make_map.py"
    render = SKILL_SCRIPTS / "render.py"
    build_sfx = SKILL_SCRIPTS / "build_sfx.py"
    mix_soundtrack = SKILL_SCRIPTS / "mix_soundtrack.py"
    fetch_commons = SKILL_SCRIPTS / "fetch_commons.py"
    burn_captions = SKILL_SCRIPTS / "burn_captions.py"

    if (project / "map.json").exists():
        _run(make_map, project, timeout=240)
    _run(get_fonts, project, timeout=180)
    _run(prep_assets, project, timeout=360)
    _run(render, project, "--cues", timeout=240)
    _run(build_sfx, project, timeout=max(300, int(duration_sec * 8)))
    _run(
        mix_soundtrack, project,
        "--voice", "audio/narration.mp3",
        "--sfx", "audio/sfx.wav",
        "--out", "audio/mix.m4a",
        timeout=max(300, int(duration_sec * 8)),
    )
    draft = project / "out" / "section.mp4"
    _run(
        render, project,
        "--size", "1280x720",
        "--workers", "1",
        "--crf", "18",
        "--out", str(draft),
        "--audio", "audio/mix.m4a",
        timeout=max(600, int(duration_sec * 80)),
    )
    credits = project / "photos.json"
    if credits.exists():
        _run_commons_credits(fetch_commons, project)
    credits_markdown = project / "credits.md"
    if credits_markdown.exists() and (project / "map.json").exists():
        with credits_markdown.open("a", encoding="utf-8") as handle:
            handle.write(
                "\\n## Map data\\n\\n"
                "- Place lookup: OpenStreetMap Nominatim; © OpenStreetMap contributors (ODbL).\\n"
                "- Map boundaries: Natural Earth data distributed through world-atlas.\\n"
            )
    subtitle = project / "out" / "section.srt"
    _run(burn_captions, project, "--srt-only", "--out", str(subtitle), timeout=180)

    if not draft.is_file() or draft.stat().st_size < 1024:
        raise RuntimeError("upstream Cinematic Skill renderer did not create a valid MP4")
    shutil.copy2(draft, output_path)
    # Sidecars are retained beside the MP4 for the API to upload alongside the scene.
    if (project / "credits.md").exists():
        shutil.copy2(project / "credits.md", output_path.with_suffix(".credits.md"))
    if subtitle.exists():
        shutil.copy2(subtitle, output_path.with_suffix(".srt"))
    return Path(output_path)
