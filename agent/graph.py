"""Graph wiring — nothing else. The shape IS the demo:

    plan → (search → read → evaluate)* → synthesize → reflect
              ↑__________________________________________|   (gap round)

LangGraph concepts:
- add_edge: unconditional hop after a node completes.
- add_conditional_edges: the router picks the next node by name; the dict
  maps router return values to node names (or END).
- compile() turns the builder into a runnable graph (.invoke / .stream).
"""
from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import ResearchState


def build_graph():
    g = StateGraph(ResearchState)
    g.add_node("plan", nodes.plan)
    g.add_node("search", nodes.search)
    g.add_node("read", nodes.read)
    g.add_node("evaluate", nodes.evaluate)
    g.add_node("synthesize", nodes.synthesize)
    g.add_node("reflect", nodes.reflect)

    g.add_edge(START, "plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "read")
    g.add_edge("read", "evaluate")
    g.add_conditional_edges("evaluate", nodes.route_after_evaluate,
                            {"search": "search", "synthesize": "synthesize"})
    g.add_edge("synthesize", "reflect")
    g.add_conditional_edges("reflect", nodes.route_after_reflect,
                            {"search": "search", "done": END})  # Phase 4: "done" -> verify
    return g.compile()
