from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
from pathlib import Path

from langchain_groq import ChatGroq
from langgraph.types import interrupt
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from BaseState import BaseState
from config import OUTPUT_DIR
from database import SessionLocal, Section, save_state, load_section, load_sections, set_section_image

MAX_REWRITES = 3                      # after this many failed attempts the section is pushed anyway
SIMILARITY_THRESHOLDS = {"facts": 0.88, "story": 0.92}   # used when the state has no similarity_threshold
FALLBACK_SIMILARITY_THRESHOLD = 0.88
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"   # 768 dimensions, matches Vector(768) in database.py
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}   # same as voice.py (kept here so tests don't import kokoro)

brief_schema = {
    "type": "object",
    "properties": {
        "video_type": {"type": "string", "enum": ["facts", "story"]},
        "brief": {"type": "string"},
        "total_sections": {"type": "integer"},
    },
    "required": ["video_type", "brief", "total_sections"],
    "additionalProperties": False,
}

brief_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.4).bind(
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "brief", "strict": True, "schema": brief_schema},
    }
)
summary_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0.2)    # also writes the image suggestions
writer_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.8)

BRIEF_SYSTEM = """You are the manager of a YouTube video script generator. A separate writer LLM writes the script one section at a time, and it remembers nothing between sections. You never write a section yourself. You write the brief the writer works from.

There are two video types. If the video type is already given, use it. Otherwise decide it from the request.
- facts (a list of separate facts, tips, myths, rankings or similar): every section is exactly ONE fact. Tell that one fact fully: the fact, the surprising detail, and the context that makes it land, at the target length. Never add a second fact to fill the length.
- story (a narrative): every section is one CHAPTER. Each chapter advances the plot with its own beat, picks up where the previous one left off, and does not recap.
For anything else, use whichever fits better.

A good brief is self-contained. It states the one fact or chapter beat to cover, the angle, the tone, the target length in words, the names and facts from earlier sections it must stay consistent with, and what is already covered so it is not repeated. Brief exactly one section.

When the task is a user rewrite, the current text of that section is given. Brief the writer to apply exactly what the user asked and keep everything else: the same single fact or chapter beat, the names and facts other sections depend on, and the target length.

When corrections are listed, the previous attempt was rejected. Brief the same section again and fix every correction. If it was too similar, choose a clearly different fact or beat. If the length was off, ask for the right length.

Reply with JSON only: video_type, brief, total_sections."""

SUMMARY_SYSTEM = """You keep a short running summary of a video script that is written one section at a time. You get the summary so far and a newly saved section. Return the updated summary and nothing else.
Format: one short line per saved section, labeled with its title, like "Fact 03: ..." or "Chapter 03: ...", a few words each. Keep earlier lines exactly as they are. If the new section has the same title as an existing line, replace that line. For a story, start with one sentence on the plot so far."""

WRITER_SYSTEM = """You are the writer of a YouTube video script. You write exactly one section, following the brief you are given. You remember nothing from earlier sections, so rely only on the brief.

Rules:
- Output only the spoken narration, exactly as the narrator will read it aloud. No title, no heading, no labels like "Fact 3", no markdown, no emojis, no stage directions, no parentheses, no word count.
- Hit the target length in the brief as closely as you can.
- Write in short paragraphs separated by a blank line. Each paragraph is a natural beat, because the video pauses at every paragraph break.
- Cover only what the brief asks for. Do not add a second fact, do not recap earlier sections, and do not write an intro or outro unless the brief asks for one."""

IMAGE_PROMPT_SYSTEM = """You get one section of a video script. Describe the single image that should be on screen while it is narrated: a concrete subject or scene, at most 25 words, no text overlays, no real people's names. Reply with the description only."""


# ── helpers ───────────────────────────────────────────────────────────────────
def similarity_limit(state: BaseState) -> float:
    if state.similarity_threshold is not None:
        return state.similarity_threshold
    return SIMILARITY_THRESHOLDS.get(state.video_type, FALLBACK_SIMILARITY_THRESHOLD)


def _section_number(key, section_count: int) -> int | None:
    try:
        number = int(key)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= section_count else None


def parse_review(answer: dict, section_count: int) -> tuple[dict, dict, list]:
    """Turns the user's review answer into (images, changes, problems).
    images  {section: path or None}   None clears the image
    changes {section: text}           blank texts are ignored
    problems: things that could not be applied"""
    images, changes, problems = {}, {}, []

    for key, path in (answer.get("images") or {}).items():
        number = _section_number(key, section_count)
        if number is None:
            problems.append(f"image for section {key}: there is no such section")
        elif not path:
            images[number] = None
        elif not Path(path).is_file() or Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
            problems.append(f"image for section {number}: file not found or unsupported type ({path})")
        else:
            images[number] = str(path)

    for key, text in (answer.get("changes") or {}).items():
        number = _section_number(key, section_count)
        if number is None:
            problems.append(f"change for section {key}: there is no such section")
        elif str(text).strip():
            changes[number] = str(text).strip()

    return images, changes, problems


def fill_images(paths: list) -> list | None:
    """One image per section. A section without an image reuses the previous one, and leading gaps use the
    first image given. Returns None when no section has an image (audio only)."""
    first = next((path for path in paths if path), None)
    if first is None:
        return None
    filled, last = [], first
    for path in paths:
        last = path or last
        filled.append(last)
    return filled


# ── embeddings ────────────────────────────────────────────────────────────────
_embedder = None

def _embed_sync(text: str) -> list[float]:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer     # loaded on first use only
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder.encode(text, normalize_embeddings=True).tolist()

async def embed(text: str) -> list[float]:
    return await asyncio.to_thread(_embed_sync, text)            # keep the event loop free


# ── router ────────────────────────────────────────────────────────────────────
async def router_node(state: BaseState) -> dict:
    saved = state.sections_completed or 0
    changes = dict(state.user_prompted_sectional_changes or {})    # {3: "make it funnier"}
    threshold = similarity_limit(state)
    total_words = round(state.estimated_duration_in_hours * 60 * state.words_per_minute)
    target = round(total_words / state.total_sections) if state.total_sections else None

    # ── 1. a section is waiting: check it ──────────────────────────────────────
    problems = []
    if state.generator_response:
        score = state.similarity_score
        if score is not None and score >= threshold:       # no score = nothing similar found = fine
            problems.append(
                f"The section is {score:.0%} similar to an earlier section (the limit is {threshold:.0%}). "
                "Choose a clearly different fact or beat, not a rewording of the same one."
            )

        count = state.generated_response_word_count
        if target and count is not None:
            margin = target * state.section_word_limit_error_percentage / 100
            lowest, highest = target - margin, target + margin
            if count < lowest:
                problems.append(
                    f"The section has {count} words but should have about {target} "
                    f"(allowed {lowest:.0f} to {highest:.0f}). Ask the writer for about {target - count} more words."
                )
            elif count > highest:
                problems.append(
                    f"The section has {count} words but should have about {target} "
                    f"(allowed {lowest:.0f} to {highest:.0f}). Ask the writer for about {count - target} fewer words."
                )

        # ── 2. it passed (or we are out of retries): update progress, send to push ──
        if not problems or state.rewrite_attempts >= MAX_REWRITES:
            reply = await summary_llm.ainvoke([
                ("system", SUMMARY_SYSTEM),
                ("user",
                 f"Summary so far:\n{state.progress_context or '(nothing yet)'}\n\n"
                 f"Newly saved section: {state.generated_response_title or 'untitled'}\n"
                 f"{state.generator_response}"),
            ])
            is_rewrite = state.current_section in changes          # a user rewrite replaces a saved section
            update = {
                "next_step": "push",
                "current_node": "router",
                "progress_context": reply.content.strip(),
                "sections_completed": saved if is_rewrite else saved + 1,
                "user_prompted_sectional_changes": {n: c for n, c in changes.items() if n != state.current_section},
                "rewrite_attempts": 0,
            }
            await save_state(state, update)
            return update

    # ── 3. nothing waiting and everything saved, nothing to rewrite: hand over to the user ──
    elif state.total_sections and saved >= state.total_sections and not changes:
        update = {"next_step": "review", "current_node": "router"}
        await save_state(state, update)
        return update

    # ── 4. otherwise write a brief: retry, user rewrite (lowest section first), or the next section ──
    if state.generator_response and state.current_section:      # the section that was just rejected
        number = state.current_section
    elif changes:
        number = min(changes)
    else:
        number = saved + 1

    old_text = None
    if number in changes:
        old_text = await load_section(state.id, number)          # the rewrite starts from the saved text
        task = f"Rewrite section {number}. The user asked: {changes[number]}"
    else:
        task = f"Write section {number}."

    if state.total_sections:
        length = (
            f"The script has {state.total_sections} sections (fixed), so return total_sections as {state.total_sections}. "
            f"Each section should be about {target} words."
        )
    else:
        length = (
            f"The whole script should be about {total_words} words. "
            "If the request names a number of items or chapters, that is the section count. "
            "Otherwise decide how many sections the script needs. Return your choice as total_sections."
        )

    if state.video_type:
        kind = f"The video type is already decided: {state.video_type}. Return video_type as {state.video_type}."
    else:
        kind = "Decide the video type from the request and return it as video_type."

    request = (
        f"<request>\n{state.user_prompt}\n</request>\n\n"
        f"<video_type>\n{kind}\n</video_type>\n\n"
        f"<length>\n{length}\n</length>\n\n"
        f"<saved_so_far>\nSections saved: {saved}\n{state.progress_context or 'nothing yet'}\n</saved_so_far>\n\n"
        f"<task>\n{task}\n</task>"
    )
    if old_text:
        request += f"\n\n<current_section_text>\n{old_text}\n</current_section_text>"
    if problems:
        fixes = "\n".join(f"- {problem}" for problem in problems)
        request += f"\n\n<rejected_section>\n{state.generator_response}\n</rejected_section>\n\n<corrections>\n{fixes}\n</corrections>"

    reply = await brief_llm.ainvoke([("system", BRIEF_SYSTEM), ("user", request)])
    data = json.loads(reply.content)

    video_type = state.video_type or data["video_type"]       # decided once, then fixed
    label = "Fact" if video_type == "facts" else "Chapter"

    update = {
        "next_step": "write",
        "current_node": "router",
        "video_type": video_type,
        "router_prompt": f"Title: {label} {number:02d}\n{data['brief']}",
        "current_section": number,
        "total_sections": state.total_sections or max(1, data["total_sections"]),
        "rewrite_attempts": state.rewrite_attempts + 1 if problems else state.rewrite_attempts,
    }
    await save_state(state, update)
    return update


# ── writer (writes the section and scores it) ─────────────────────────────────
async def writer_node(state: BaseState) -> dict:
    """Writes the section from the router's brief, then scores it against the saved sections of this script.
    The position being replaced is skipped, so a user rewrite is not compared with its old version."""
    title_line, _, brief = state.router_prompt.partition("\n")      # "Title: Fact 04" + the brief
    title = title_line.removeprefix("Title:").strip()

    reply = await writer_llm.ainvoke([("system", WRITER_SYSTEM), ("user", brief)])
    text = reply.content.strip()

    embedding = await embed(text)
    distance = Section.embedding.cosine_distance(embedding)
    stmt = (
        select(func.min(distance))
        .where(Section.state_id == state.id)
        .where(Section.position != state.current_section)
    )
    async with SessionLocal() as session:
        nearest = (await session.execute(stmt)).scalar_one_or_none()

    update = {
        "current_node": "writer",
        "generator_response": text,
        "generated_response_title": title,
        "generated_response_word_count": len(text.split()),
        "similarity_score": None if nearest is None else float(1 - nearest),   # None = nothing to compare = fine
    }
    await save_state(state, update)
    return update


# ── push ──────────────────────────────────────────────────────────────────────
async def push_section_node(state: BaseState) -> dict:
    """Saves the approved section (insert, or replace if that position exists) with a suggested image
    description, and clears the waiting section. A rewrite keeps the image the user already picked."""
    text = state.generator_response
    embedding = await embed(text)
    image_reply = await summary_llm.ainvoke([("system", IMAGE_PROMPT_SYSTEM), ("user", text)])

    stmt = insert(Section).values(
        state_id=state.id,
        position=state.current_section,
        text=text,
        word_count=state.generated_response_word_count or len(text.split()),
        embedding=embedding,
        image_prompt=image_reply.content.strip(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["state_id", "position"],
        set_={
            "text": stmt.excluded.text,
            "word_count": stmt.excluded.word_count,
            "embedding": stmt.excluded.embedding,
            "image_prompt": stmt.excluded.image_prompt,      # image_path is not touched
            "updated_at": func.now(),
        },
    )
    async with SessionLocal() as session:
        await session.execute(stmt)
        await session.commit()

    update = {                                   # nothing is waiting any more, so the router moves on
        "current_node": "push_section",
        "generator_response": None,
        "generated_response_title": None,
        "generated_response_word_count": None,
        "similarity_score": None,
    }
    await save_state(state, update)
    return update


# ── review (human in the loop) ────────────────────────────────────────────────
async def review_node(state: BaseState) -> dict:
    """Pauses the graph and shows the user every section. The user's answer (the resume value) looks like:
        {"changes": {1: "make it funnier", 4: "shorter"},     # rewritten by the router, only these sections
         "images":  {1: "images/a.png", 3: None},             # image per section, None clears it
         "approve": True}                                      # script is good: render audio and video
    If there are changes they win over approve: the sections are rewritten and the user reviews again.
    Everything before interrupt() runs again on resume, so it only reads."""
    sections = await load_sections(state.id)
    label = "Fact" if state.video_type == "facts" else "Chapter"
    view = [
        {"section": s.position, "title": f"{label} {s.position:02d}", "text": s.text, "words": s.word_count,
         "image_prompt": s.image_prompt, "image_path": s.image_path}
        for s in sections
    ]

    notice = None
    while True:
        answer = interrupt({
            "message": "Review the script. Send changes per section, set images, or approve to render.",
            "notice": notice,
            "sections": view,
        }) or {}
        images, changes, problems = parse_review(answer, len(sections))
        if not problems:
            break
        notice = "Nothing was applied. Send the whole answer again. Problems: " + "; ".join(problems)

    for number, path in images.items():
        await set_section_image(state.id, number, path)

    if changes:                                     # the router rewrites these sections, lowest number first
        update = {"next_step": "rewrite", "user_prompted_sectional_changes": changes, "rewrite_attempts": 0}
    elif answer.get("approve"):
        update = {"next_step": "render"}
    else:
        update = {"next_step": "review"}            # only images changed (or nothing): ask again
    update["current_node"] = "review"
    await save_state(state, update)
    return update


# ── render (audio, then video) ────────────────────────────────────────────────
async def render_node(state: BaseState) -> dict:
    """Voices the whole script, then builds the video with one image per section (if any images were set)."""
    from voice import generate_voiceover, split_paragraphs      # kokoro/torch only load when rendering

    sections = await load_sections(state.id)
    if [s.position for s in sections] != list(range(1, (state.total_sections or 0) + 1)):
        raise ValueError("saved sections are not numbered 1..total_sections without gaps")

    texts = [s.text for s in sections]
    images = fill_images([s.image_path for s in sections])
    folder = Path(OUTPUT_DIR) / str(state.id)

    options = {}
    if images:
        options = {
            "image_paths": images,
            "video_path": folder / "video.mp4",
            "section_paragraph_counts": [len(split_paragraphs(text)) for text in texts],
        }

    result = await asyncio.to_thread(                           # TTS and ffmpeg are blocking
        generate_voiceover,
        "\n\n".join(texts),
        folder / "voiceover.mp3",
        target_wpm=state.words_per_minute,
        voice_model=state.voice_model,
        **options,
    )

    update = {
        "next_step": "finished",
        "current_node": "render",
        "audio_path": result["audio_path"],
        "video_path": result.get("video_path"),
    }
    await save_state(state, update)
    return update