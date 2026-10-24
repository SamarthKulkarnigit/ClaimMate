"""LangGraph supervisor graph: Coordinator routes to specialists; Auditor can send work back."""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agents import nodes
from backend.agents.state import ClaimState


def build_graph():
    g = StateGraph(ClaimState)
    g.add_node("intake", nodes.intake)
    g.add_node("coordinator", nodes.coordinator)
    g.add_node("damage", nodes.damage)
    g.add_node("policy", nodes.policy)
    g.add_node("cost", nodes.cost)
    g.add_node("auditor", nodes.auditor)
    g.add_node("human", nodes.human)
    g.add_node("finalize", nodes.finalize)
    g.add_node("escalate", nodes.escalate)

    g.add_edge(START, "intake")
    g.add_edge("intake", "coordinator")
    g.add_conditional_edges("coordinator", nodes.route,
                            {k: k for k in ("damage", "policy", "cost", "auditor", "human", "escalate")})
    for n in ("damage", "policy", "cost", "auditor"):
        g.add_edge(n, "coordinator")
    g.add_conditional_edges("human", nodes.after_human, {"finalize": "finalize", "end": END})
    g.add_edge("finalize", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=InMemorySaver())


GRAPH = build_graph()
