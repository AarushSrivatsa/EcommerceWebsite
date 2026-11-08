from dotenv import load_dotenv
load_dotenv()

import asyncio
import json

from langchain_groq import ChatGroq
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

import memory
from BaseState import BaseState
from database import SessionLocal, Section, save_state, load_section

MAX_REWRITES = 3                      # after this many failed attempts the section is pushed anyway
SIMILARITY_THRESHOLDS = {"facts": 0.88, "story": 0.92}   # used when the state has no similarity_threshold
FALLBACK_SIMILARITY_THRESHOLD = 0.88
WRITER_ATTEMPTS = 3                   # tries when the writer LLM comes back empty
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"   # 768 dimensions, matches Vector(768) in database.py

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

# gpt-oss "thinks" before answering; with the default budget the thinking can eat all the tokens and Groq then
# returns an empty generation (json_validate_failed). So: low reasoning effort and a roomy token limit.
_BRIEF_KWARGS = dict(model="openai/gpt-oss-120b", temperature=0.4, max_tokens=4096, reasoning_effort="low")
brief_llm = ChatGroq(**_BRIEF_KWARGS).bind(
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "brief", "strict": True, "schema": brief_schema},
    }
)
brief_fallback_llm = ChatGroq(**_BRIEF_KWARGS)      # no schema mode: asked for JSON in plain words instead
summary_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0.2)    # also writes the image suggestions
# same reasoning limit as the brief LLM, so the thinking cannot use up all the tokens and leave an empty reply
writer_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.8, max_tokens=8192, reasoning_effort="low")

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


# ── embeddings ────────────────────────────────────────────────────────────────
def _embed_sync(text: str) -> list[float]:
    from fastembed import TextEmbedding                           # ONNX, no PyTorch
    embedder = TextEmbedding(EMBEDDING_MODEL)
    try:
        vector = next(iter(embedder.embed([text]))).tolist()
        memory.report("embedder loaded")
        return vector
    finally:
        del embedder                                              # not kept: the voice model needs that RAM
        memory.free()

async def embed(text: str) -> list[float]:
    async with memory.heavy:                                      # never at the same time as the voice model
        return await asyncio.to_thread(_embed_sync, text)         # keep the event loop free


async def suggest_image_prompt(text: str) -> str | None:
    """One-line description of the image that fits a section. Never raises: it is only a suggestion."""
    try:
        reply = await summary_llm.ainvoke([("system", IMAGE_PROMPT_SYSTEM), ("user", text)])
        return reply.content.strip() or None
    except Exception:
        return None


BRIEF_ATTEMPTS = 3


def _valid_brief(data) -> bool:
    return (isinstance(data, dict) and isinstance(data.get("brief"), str) and data["brief"].strip() != ""
            and data.get("video_type") in ("facts", "story") and isinstance(data.get("total_sections"), int))


async def get_brief(messages: list) -> dict:
    """Asks the manager LLM for the brief. Groq's strict JSON mode sometimes fails or returns nothing, so retry a
    few times, then fall back to a plain request for JSON. Raises only if everything fails."""
    last_error = None
    for _ in range(BRIEF_ATTEMPTS):
        try:
            data = json.loads((await brief_llm.ainvoke(messages)).content)
            if _valid_brief(data):
                return data
            last_error = ValueError(f"incomplete brief: {data!r}")
        except Exception as exc:                       # 400 json_validate_failed, empty or broken JSON
            last_error = exc

    try:
        reply = await brief_fallback_llm.ainvoke(messages + [(
            "user", "Reply with ONE JSON object and nothing else: "
                    '{"video_type": "facts" or "story", "brief": "...", "total_sections": <integer>}')])
        text = reply.content
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        if _valid_brief(data):
            return data
        last_error = ValueError(f"incomplete brief: {data!r}")
    except Exception as exc:
        last_error = exc
    raise RuntimeError(f"the manager LLM did not return a usable brief: {last_error}")


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

    # ── 3. nothing waiting, everything saved, nothing to rewrite: the graph is done ──
    elif state.total_sections and saved >= state.total_sections and not changes:
        update = {"next_step": "finish", "current_node": "router"}
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

    data = await get_brief([("system", BRIEF_SYSTEM), ("user", request)])

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

    text = ""
    for _ in range(WRITER_ATTEMPTS):
        reply = await writer_llm.ainvoke([("system", WRITER_SYSTEM), ("user", brief)])
        text = reply.content.strip()
        if text:
            break
    if not text:
        raise RuntimeError("the writer LLM returned an empty section")

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
    description, and clears the waiting section. The user's image is kept on a rewrite, but the section's
    video is marked as needing a re-render (content_rev is bumped)."""
    text = state.generator_response
    embedding = await embed(text)
    image_prompt = await suggest_image_prompt(text)

    stmt = insert(Section).values(
        state_id=state.id,
        position=state.current_section,
        text=text,
        word_count=state.generated_response_word_count or len(text.split()),
        embedding=embedding,
        image_prompt=image_prompt,
        video_status="pending",
        content_rev=1,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["state_id", "position"],
        set_={
            "text": stmt.excluded.text,
            "word_count": stmt.excluded.word_count,
            "embedding": stmt.excluded.embedding,
            "image_prompt": stmt.excluded.image_prompt,      # image_path is not touched
            "video_status": "pending",
            "video_error": None,
            "content_rev": Section.content_rev + 1,
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