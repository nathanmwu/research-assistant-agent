"""Dev runner: .venv/bin/python cli.py "your research question"

Streams two channels from one graph run (stream_mode=["updates", "messages"]):
- updates:  {node_name: partial_state} after each node -> timeline lines
- messages: (token_chunk, metadata) live from LLM calls inside nodes -> we
  print only the synthesize node's tokens, so the briefing types itself out.
"""
import sys
from datetime import datetime
from pathlib import Path

from agent.graph import build_graph
from agent.llm import text_of
from agent.state import initial_state


class _Tee:
    """Mirror writes to the console and the run log — every run (including
    its crashes) leaves a complete, inspectable artifact in runs/."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('usage: python cli.py "your research question"')
    question = " ".join(sys.argv[1:])

    Path("runs").mkdir(exist_ok=True)
    log_path = Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}.log"
    log = log_path.open("w")
    sys.stdout = _Tee(sys.__stdout__, log)
    sys.stderr = _Tee(sys.__stderr__, log)  # tracebacks land in the log too
    print(f"❓ {question}")

    graph = build_graph()
    n_sources = 0          # how many sources we've already announced
    briefing_started = False
    revised = False        # a gap round happened; next briefing is v2

    # recursion_limit: LangGraph's default budget is 25 node executions; the
    # Phase-2 retry loops can legitimately exceed that, so raise it once here.
    stream = graph.stream(initial_state(question),
                          config={"recursion_limit": 100},
                          stream_mode=["updates", "messages"])

    for mode, chunk in stream:
        if mode == "messages":
            msg, meta = chunk
            if meta.get("langgraph_node") != "synthesize":
                continue  # skip token noise from plan/read structured calls
            text = text_of(msg.content)
            if text:
                if not briefing_started:
                    title = "📝 briefing (revised)" if revised else "📝 briefing"
                    print(f"\n{title}\n" + "─" * 60)
                    briefing_started = True
                print(text, end="", flush=True)
            continue

        for node, delta in chunk.items():
            if node == "plan":
                print("🧭 plan")
                for sq in delta["sub_questions"]:
                    print(f"   {sq['id']}. {sq['question']}\n      why: {sq['rationale']}")
            elif node == "search":
                print(f"🔍 search #{delta['attempts']}: \"{delta['last_query']}\" "
                      f"→ {len(delta['results'])} results")
            elif node == "read":
                for src in delta["sources"][n_sources:]:
                    print(f"📄 read [S{src['id']}] {src['title']} ({src['url']}) · {src['via']}")
                n_sources = len(delta["sources"])
            elif node == "evaluate":
                if delta.get("next_query"):
                    print(f"🔁 not enough yet — refining: \"{delta['next_query']}\"")
                else:
                    sq = delta["sub_questions"][delta["cursor"] - 1]
                    mark = "✅" if sq["status"] == "answered" else "⚠️"
                    print(f"{mark} sub-question {sq['id']}/{len(delta['sub_questions'])} "
                          f"{sq['status']}")
            elif node == "synthesize":
                print()  # close the briefing's token stream
            elif node == "reflect":
                if "sub_questions" in delta:
                    gaps = [sq for sq in delta["sub_questions"] if sq["status"] == "pending"]
                    print("🪞 reflection: material gaps — extending research")
                    for sq in gaps:
                        print(f"   +{sq['id']}. {sq['question']}")
                    briefing_started, revised = False, True
                elif delta.get("open_gaps"):
                    print("🪞 reflection: gaps remain but budget spent — will disclose:")
                    for g in delta["open_gaps"]:
                        print(f"   ? {g}")
                else:
                    print("🪞 reflection: the briefing answers the question")

    print("─" * 60)
    print(f"✅ done — {n_sources} sources read")
    print(f"📁 full log: {log_path}")


if __name__ == "__main__":
    main()
