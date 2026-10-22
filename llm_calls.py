from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from BaseState import BaseState
import json

schema = {
    "type": "object",
    "properties": {
        "next_step": {"type": "string", "enum": ["write", "push", "done"]},
        "router_prompt": {"type": "string"},
        "progress_context": {"type": "string"},
    },
    "required": ["next_step", "router_prompt", "progress_context"],
    "additionalProperties": False,
}

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.2).bind(
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "decision", "strict": True, "schema": schema},
    }
)


def format_change(c):
    if isinstance(c, dict) and "section" in c:
        return f"- section {c['section']}: {c.get('change', '')}"
    return f"- {c}"


async def router_node(state: BaseState) -> dict:
    done = state.sections_completed or 0
    threshold = 0.85 if state.similarity_threshold is None else state.similarity_threshold
    total_words = round(state.estimated_duration_in_hours * 60 * state.words_per_minute)

    if state.total_sections:
        count_rule = f"FIXED at {state.total_sections} sections. Do not finish before it is reached."
        length_target = f"about {total_words // state.total_sections} words per section"
        next_new = (
            f"number {done + 1}" if done < state.total_sections
            else "none, the fixed count has been reached"
        )
    else:
        count_rule = (
            "NOT set. If the request names a number (like 100 facts or 8 chapters), that number is binding. "
            "Otherwise you decide how many sections are needed and when the script is complete."
        )
        length_target = f"about {total_words} words across the whole script"
        next_new = f"number {done + 1}"

    changes = "\n".join(format_change(c) for c in (state.user_prompted_sectional_changes or [])) or "none"

    if state.generator_response:
        score = state.similarity_score if state.similarity_score is not None else "no earlier section matched"
        waiting = (
            f"Title: {state.generated_response_title or 'untitled'}\n"
            f"{state.generator_response}\n"
            f"Word count: {state.generated_response_word_count}\n"
            f"Similarity to earlier sections: {score}"
        )
    else:
        waiting = "none, no section is waiting"

    system_prompt = f"""<role>
You are the manager of a YouTube video script generator. A separate writer LLM writes the script one section at a time. You never write a section yourself. You decide what happens next and brief the writer.
</role>

<request>
{state.user_prompt}
</request>

<video_types>
First work out which kind of video the request is.
- FACTS (a list of separate facts, tips, myths, rankings or anything similar). Every section is exactly ONE fact, titled "Fact 01", "Fact 02" and so on. A fact section tells that one fact fully: the fact itself, the specific detail that makes it surprising, and the context that makes it land, at the target length. Never put a second fact in a section to fill the length. Sections do not depend on each other.
- STORY (a narrative). Every section is one CHAPTER, titled "Chapter 01", "Chapter 02" and so on. Each chapter advances the plot with its own beat, picks up where the previous chapter left off, and does not recap.
If the request is something else, use whichever of the two fits better.
</video_types>

<progress>
Sections saved so far: {done}
Next new section: {next_new}
Section count: {count_rule}
Length: {length_target}. This is a guide, not a limit.
Saved so far:
{state.progress_context or "nothing yet"}
</progress>

<waiting_section>
{waiting}
</waiting_section>

<pending_user_changes>
{changes}
</pending_user_changes>

<decide>
Pick exactly one route:
- "push": a section is waiting and is fine to save. It is fine when no earlier section matched, or its similarity is below {threshold}. router_prompt is empty.
- "write": no section is waiting, or the waiting section is too similar (similarity {threshold} or above), or a user change is pending. router_prompt is the brief for the writer.
- "done": the script is complete, nothing is waiting, no user change is pending, and the section count rule allows it. router_prompt is empty.

Brief exactly ONE section per turn. Never plan or brief several sections at once.
Start router_prompt with a title line, for example "Title: Fact 04" or "Title: Chapter 04", using the number of the section being written. Then write the brief. The brief is self-contained, because the writer remembers nothing else. It states the one fact or the one chapter beat this section covers, the angle, the tone, the target length in words, the names and facts from earlier sections it must stay consistent with, and what is already covered so it is not repeated.
If the waiting section was too similar, brief the same section again with a clearly different fact or beat. If a user change is pending, brief a rewrite of that section under its existing title, carrying the user's instruction faithfully.
If waiting sections keep coming in short or long of the target, change the length you ask for. Writers usually undershoot. Do not reject a section only for its length.
</decide>

<output>
JSON only:
- next_step: "write", "push" or "done"
- router_prompt: the title line and brief for the writer, or an empty string
- progress_context: one line per saved section, labeled with its title, like "Fact 03: ..." or "Chapter 03: ...". Keep earlier lines exactly as they were. If you chose push, add the line for the waiting section, or replace its line if it was a rewrite. Finish with one line on what comes next.
</output>"""

    reply = await llm.ainvoke([
        ("system", system_prompt),
        ("user", "Decide the next step."),
    ])
    data = json.loads(reply.content)

    # the router only decides; the push node saves and increments sections_completed
    return {
        "next_step": data["next_step"],
        "router_prompt": data["router_prompt"],
        "progress_context": data["progress_context"],
    }



# Testing
if __name__ == "__main__":
    import asyncio

    async def show(label, state):
        out = await router_node(state)
        print(f"{label}\n  next_step: {out['next_step']}\n  router_prompt: {out['router_prompt']}\n"
              f"  progress_context: {out['progress_context']}\n")

    async def main():
        facts = BaseState(
            user_prompt="10 surprising facts about octopuses",
            estimated_duration_in_hours=0.05,   # 450 words total, so 45 per fact
            words_per_minute=150,
            total_sections=10,
            sections_completed=0,
            similarity_threshold=0.85,
        )
        await show("1. FACTS, FRESH START (expect write, Title: Fact 01)", facts)

        text = (
            "An octopus can squeeze through any opening larger than its beak, the only hard part of its body. "
            "With no bones to stop it, one can slip through a gap the size of a coin, which is why aquarium "
            "keepers tie down every lid. Escape artists like this have been caught wandering across lab floors at night."
        )
        waiting = facts.model_copy(update={
            "sections_completed": 3,
            "progress_context": "Fact 01: Octopuses have three hearts.\nFact 02: They have blue blood.\nFact 03: Each arm has its own neurons.",
            "generated_response_title": "Fact 04",
            "generator_response": text,
            "generated_response_word_count": len(text.split()),
            "similarity_score": 0.31,
        })
        await show("2. FACT BACK, NOT SIMILAR (expect push, empty router_prompt)", waiting)

        await show("3. FACT BACK, NEAR-DUPLICATE (expect write, a different Fact 04)",
                   waiting.model_copy(update={"similarity_score": 0.93}))

        await show("4. ALL 10 SAVED (expect done)", facts.model_copy(update={
            "sections_completed": 10,
            "progress_context": "Fact 01 to Fact 10 saved: hearts, blood, arms, beak, camouflage, ink, lifespan, intelligence, venom, tool use.",
        }))

        await show("5. USER CHANGE PENDING (expect write, rewrite of Fact 02)", facts.model_copy(update={
            "sections_completed": 3,
            "progress_context": "Fact 01: Octopuses have three hearts.\nFact 02: They have blue blood.\nFact 03: Each arm has its own neurons.",
            "user_prompted_sectional_changes": [{"section": 2, "change": "make it funnier"}],
        }))

        story = BaseState(
            user_prompt="A short story about the last lighthouse keeper on a stormy coast",
            estimated_duration_in_hours=0.1,
            words_per_minute=150,
            total_sections=5,
            sections_completed=0,
            similarity_threshold=0.85,
        )
        await show("6. STORY, FRESH START (expect write, Title: Chapter 01)", story)

    asyncio.run(main())