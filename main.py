import asyncio
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from BaseState import BaseState
from database import init_db
from edges import build_graph


async def pending_review(graph, config):
    """The payload the review node paused with, or None if the graph has finished."""
    snapshot = await graph.aget_state(config)
    return snapshot.tasks[0].interrupts[0].value if snapshot.next else None


async def main():
    await init_db()
    graph = build_graph(InMemorySaver())      # see the notes for the Postgres checkpointer

    state = BaseState(
        user_prompt="10 surprising facts about octopuses",
        estimated_duration_in_hours=0.05,
        words_per_minute=150,
        total_sections=10,
    )
    config = {"configurable": {"thread_id": str(state.id)}, "recursion_limit": 1000}

    await graph.ainvoke(state, config)                    # runs until the review pause
    review = await pending_review(graph, config)
    for section in review["sections"]:
        print(section["title"], section["words"], "words | image idea:", section["image_prompt"])

    # the user answers: changes by section number, images by section number
    await graph.ainvoke(Command(resume={
        "changes": {2: "make it funnier", 5: "shorter, end on one punchy line"},
        "images": {1: "images/octopus.jpg"},
    }), config)                                           # only sections 2 and 5 are rewritten
    review = await pending_review(graph, config)          # paused again with the new versions

    await graph.ainvoke(Command(resume={"approve": True}), config)   # audio, then video
    final = (await graph.aget_state(config)).values
    print(final["audio_path"], final["video_path"])


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)