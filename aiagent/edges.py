from langgraph.graph import END

from .BaseState import BaseState


def route_after_router(state: BaseState) -> str:
    routes = {"write": "writer", "push": "push_section", "finish": END}
    return routes[state.next_step]
