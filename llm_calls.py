from langchain_groq import ChatGroq
from BaseState import BaseState
from database import Base
import json

schema = {
    "type": "object",
    "properties": {
        "next_step": {"type": "string", "enum": ["write", "search", "done"]},
        "router_prompt": {"type": "string"},
        "progress_context": {"type": "string"},
    },
    "required": ["next_step", "router_prompt", "progress_context"],
    "additionalProperties": False,
}

llm = ChatGroq(model="openai/gpt-oss-120b").bind(
    response_format = {
        "type" : "json_schema",
        "json_schema": {"name": "decision", "strict": True, "schema": schema}
    }
)

async def router_node(BaseState):
    systen_prompt = f""" You are the manager router llm for a youtube video script generator, note that it can be a facts video or a story kindof video. Note that the generation process is happening in different sections by the generator llm.

    This is the information,
    user's main request : {BaseState.user_prompt}
    context so far : {BaseState.progress_context}
    
    This is the similarity score for a previously generated text : {BaseState.similarity_score}

    if the similarity score is above {BaseState.similarity_threshold}, route this to 'push_section' node, if it is empty focus on the prompting for the next {BaseState.sections_completed} section and increment it only if you are passing it for saving else return the same. 
    
    Note that each section must have around {int((BaseState.estimated_duration_in_hours * 60 * BaseState.words_per_minute)/BaseState.total_sections)} number of words mention that in router prompt,

    now respond with the updated progress_context,sections_completed, router_prompt,
    """

    reply = await llm.ainvoke([
        ("system", systen_prompt),
        ("user", "Decide the next step."),
    ])

    data = json.loads(reply.content)
    return {
        "next_step": data["next_step"],
        "router_prompt": data["router_prompt"],
        "progress_context": data["progress_context"],
    }

if __name__ == "__main__":
    import asyncio

    async def main():
        s = BaseState(
            user_prompt="10 surprising facts about octopuses",
            estimated_duration_in_hours=0.05,   # 450 words total, so 45 per section
            words_per_minute=150,
            total_sections=10,
            sections_completed=0,
            similarity_threshold=0.85,
        )
        print("1. FRESH START\n", await router_node(s), "\n")

        s2 = s.model_copy(update={
            "sections_completed": 3,
            "progress_context": "1. Octopuses have three hearts. 2. They have blue blood. 3. Each arm has its own neurons.",
            "generator_response": "An octopus can squeeze through any gap larger than its beak.",
            "similarity_score": 0.31,
        })
        print("2. SECTION BACK, NOT SIMILAR\n", await router_node(s2), "\n")

        s3 = s2.model_copy(update={"similarity_score": 0.93})
        print("3. SECTION BACK, NEAR-DUPLICATE\n", await router_node(s3))

    asyncio.run(main())
