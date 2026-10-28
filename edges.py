from langgraph.graph import StateGraph, START, END
from BaseState import BaseState


def route_after_router(state: BaseState) -> str:
    return {"write": "writer", "push": "push_section", "review": "review"}[state.next_step]


def route_after_review(state: BaseState) -> str:
    return {"rewrite": "router", "render": "render", "review": "review"}[state.next_step]


def build_graph(checkpointer):
    """A checkpointer is required: it is what lets the graph pause at the review and continue later."""
    from nodes import router_node, writer_node, push_section_node, review_node, render_node

    graph = StateGraph(BaseState)
    graph.add_node("router", router_node)
    graph.add_node("writer", writer_node)
    graph.add_node("push_section", push_section_node)
    graph.add_node("review", review_node)
    graph.add_node("render", render_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_after_router, ["writer", "push_section", "review"])
    graph.add_edge("writer", "router")            # the draft arrives already scored
    graph.add_edge("push_section", "router")      # after saving: next brief, next rewrite, or the review
    graph.add_conditional_edges("review", route_after_review, ["router", "render", "review"])
    graph.add_edge("render", END)
    return graph.compile(checkpointer=checkpointer)