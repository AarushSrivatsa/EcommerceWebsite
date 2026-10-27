from dotenv import load_dotenv
load_dotenv()

import json
from langchain_groq import ChatGroq
from BaseState import BaseState
from database import save_state

MAX_REWRITES = 3                      # after this many failed attempts the section is pushed anyway
DEFAULT_SIMILARITY_THRESHOLD = 0.85

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
summary_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0.2)

BRIEF_SYSTEM = """You are the manager of a YouTube video script generator. A separate writer LLM writes the script one section at a time, and it remembers nothing between sections. You never write a section yourself. You write the brief the writer works from.

There are two video types. If the video type is already given, use it. Otherwise decide it from the request.
- facts (a list of separate facts, tips, myths, rankings or similar): every section is exactly ONE fact. Tell that one fact fully: the fact, the surprising detail, and the context that makes it land, at the target length. Never add a second fact to fill the length.
- story (a narrative): every section is one CHAPTER. Each chapter advances the plot with its own beat, picks up where the previous one left off, and does not recap.
For anything else, use whichever fits better.

A good brief is self-contained. It states the one fact or chapter beat to cover, the angle, the tone, the target length in words, the names and facts from earlier sections it must stay consistent with, and what is already covered so it is not repeated. Brief exactly one section.

When corrections are listed, the previous attempt was rejected. Brief the same section again and fix every correction. If it was too similar, choose a clearly different fact or beat. If the length was off, ask for the right length.

Reply with JSON only: video_type, brief, total_sections."""

SUMMARY_SYSTEM = """You keep a short running summary of a video script that is written one section at a time. You get the summary so far and a newly saved section. Return the updated summary and nothing else.
Format: one short line per saved section, labeled with its title, like "Fact 03: ..." or "Chapter 03: ...", a few words each. Keep earlier lines exactly as they are. If the new section has the same title as an existing line, replace that line. For a story, start with one sentence on the plot so far."""


async def router_node(state: BaseState) -> dict:
    saved = state.sections_completed or 0
    changes = list(state.user_prompted_sectional_changes or [])    # [{"section": 3, "change": "make it funnier"}]
    threshold = DEFAULT_SIMILARITY_THRESHOLD if state.similarity_threshold is None else state.similarity_threshold
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
            update = {
                "next_step": "push",
                "current_node": "router",
                "progress_context": reply.content.strip(),
                "sections_completed": saved if changes else saved + 1,   # a user rewrite replaces a saved section
                "user_prompted_sectional_changes": changes[1:],          # this change is now applied
                "rewrite_attempts": 0,
            }
            await save_state(state, update)
            return update

    # ── 3. nothing waiting and everything saved: finished ─────────────────────
    elif state.total_sections and saved >= state.total_sections and not changes:
        update = {"next_step": "done", "current_node": "router"}
        await save_state(state, update)
        return update

    # ── 4. otherwise write a brief: next section, user rewrite, or retry with corrections ──
    if changes:
        number = changes[0]["section"]
        task = f"Rewrite section {number}. The user asked: {changes[0]['change']}"
    else:
        number = saved + 1
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