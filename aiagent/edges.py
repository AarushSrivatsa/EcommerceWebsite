from langgraph.graph import END
from .BaseState import BaseState
from .nodes import router_node, writer_node, push_section_node

def route_after_router(state: BaseState) -> str:
    return {"write": "writer", "push": "push_section", "finish": END}[state.next_step]
