from langgraph.graph import StateGraph, START, END
from BaseState import BaseState


def route_after_router(state: BaseState) -> str:
    return {"write": "writer", "push": "push_section", "finish": END}[state.next_step]


def build_graph():
    """The graph only writes (or rewrites) sections. It stops when every section is saved and nothing is
    waiting to be rewritten. Everything about images, audio and video lives in the API, not here."""
    from nodes import router_node, writer_node, push_section_node

    graph = StateGraph(BaseState)
    graph.add_node("router", router_node)
    graph.add_node("writer", writer_node)
    graph.add_node("push_section", push_section_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_after_router, ["writer", "push_section", END])
    graph.add_edge("writer", "router")            # the draft arrives already scored
    graph.add_edge("push_section", "router")      # after saving: next brief, next rewrite, or finish
    return graph.compile()
