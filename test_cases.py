import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langgraph.graph import END
import nodes
from nodes import router_node
from edges import route_after_router
from BaseState import BaseState


async def test_router():
    # The LLMs are replaced, so no API calls are made.
    nodes.brief_llm = AsyncMock()
    nodes.brief_llm.ainvoke.return_value = SimpleNamespace(
        content=json.dumps({"video_type": "facts", "brief": "STUB BRIEF", "total_sections": 12}))
    nodes.summary_llm = AsyncMock()
    nodes.summary_llm.ainvoke.return_value = SimpleNamespace(content="STUB SUMMARY")
    nodes.save_state = AsyncMock()      # no database in tests

    # 0.05 h * 60 * 150 wpm = 450 words / 10 sections = 45 per section (allowed 40.5 to 49.5)
    text = ("An octopus can squeeze through any opening larger than its beak, the only hard part of its body. "
            "With no bones to stop it, one can slip through a gap the size of a coin, which is why aquarium "
            "keepers tie down every lid.")
    start = BaseState(user_prompt="10 surprising facts about octopuses", estimated_duration_in_hours=0.05,
                      words_per_minute=150, total_sections=10, sections_completed=0, similarity_threshold=0.85)
    waiting = start.model_copy(update={
        "sections_completed": 3, "progress_context": "Fact 01: hearts\nFact 02: blood\nFact 03: arms",
        "generated_response_title": "Fact 04", "generator_response": text,
        "generated_response_word_count": len(text.split()), "similarity_score": 0.31})

    def sent_to_brief_llm():
        return nodes.brief_llm.ainvoke.call_args[0][0][1][1]

    # nothing waiting, first section -> write
    out = await router_node(start)
    assert out["next_step"] == "write" and out["current_section"] == 1
    assert out["router_prompt"].startswith("Title: Fact 01\n") and out["rewrite_attempts"] == 0
    assert out["current_node"] == "router"
    assert out["video_type"] == "facts"                         # the router decided the type
    assert "Decide the video type" in sent_to_brief_llm()
    nodes.save_state.assert_awaited_once_with(start, out)       # the router saved what it returned

    # good section -> push, count goes 3 -> 4, summary updated
    out = await router_node(waiting)
    assert out["next_step"] == "push" and out["sections_completed"] == 4
    assert out["progress_context"] == "STUB SUMMARY" and out["rewrite_attempts"] == 0

    # too similar -> write the same section again with the correction
    out = await router_node(waiting.model_copy(update={"similarity_score": 0.93}))
    assert out["next_step"] == "write" and out["current_section"] == 4 and out["rewrite_attempts"] == 1
    assert "sections_completed" not in out
    assert "93% similar" in sent_to_brief_llm() and "<rejected_section>" in sent_to_brief_llm()

    # too short / too long -> write with a word correction
    await router_node(waiting.model_copy(update={"generated_response_word_count": 20}))
    assert "25 more words" in sent_to_brief_llm()
    await router_node(waiting.model_copy(update={"generated_response_word_count": 70}))
    assert "25 fewer words" in sent_to_brief_llm()

    # inside the 10% margin -> push
    out = await router_node(waiting.model_copy(update={"generated_response_word_count": 49}))
    assert out["next_step"] == "push"

    # no similarity score -> push
    out = await router_node(waiting.model_copy(update={"similarity_score": None}))
    assert out["next_step"] == "push"

    # still bad after 3 rewrites -> push anyway
    out = await router_node(waiting.model_copy(update={"similarity_score": 0.99, "rewrite_attempts": 3}))
    assert out["next_step"] == "push"

    # all sections saved -> done
    out = await router_node(start.model_copy(update={"sections_completed": 10}))
    assert out["next_step"] == "done"

    # section count unknown -> the LLM picks it and it is stored
    out = await router_node(start.model_copy(update={"total_sections": None}))
    assert out["total_sections"] == 12

    # user change pending, nothing waiting -> rewrite of that section
    change = [{"section": 2, "change": "make it funnier"}]
    out = await router_node(start.model_copy(update={"sections_completed": 3, "user_prompted_sectional_changes": change}))
    assert out["current_section"] == 2 and out["router_prompt"].startswith("Title: Fact 02\n")
    assert "make it funnier" in sent_to_brief_llm()

    # all saved but a change is pending -> not done
    out = await router_node(start.model_copy(update={"sections_completed": 10, "user_prompted_sectional_changes": change}))
    assert out["next_step"] == "write"

    # good user rewrite -> push, count unchanged, change removed
    out = await router_node(waiting.model_copy(update={"user_prompted_sectional_changes": change}))
    assert out["next_step"] == "push" and out["sections_completed"] == 3
    assert out["user_prompted_sectional_changes"] == []

    # video type already set -> kept, not decided again (Chapter titles for a story)
    out = await router_node(start.model_copy(update={"video_type": "story"}))
    assert out["video_type"] == "story" and out["router_prompt"].startswith("Title: Chapter 01\n")
    assert "already decided: story" in sent_to_brief_llm()

    # routing edge
    assert route_after_router(waiting.model_copy(update={"next_step": "write"})) == "writer"
    assert route_after_router(waiting.model_copy(update={"next_step": "push"})) == "push_section"
    assert route_after_router(waiting.model_copy(update={"next_step": "done"})) == END

    print("all router tests passed")


asyncio.run(test_router())