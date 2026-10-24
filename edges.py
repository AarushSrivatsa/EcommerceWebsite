from langgraph.graph import END
from BaseState import BaseState

def route_after_router(state: BaseState) -> str:
    return {"write": "writer", "push": "push_section", "done": END}[state.next_step]
