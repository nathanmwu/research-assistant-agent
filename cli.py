"""Dev runner: .venv/bin/python cli.py "your research question"

Streams two channels from one graph run (stream_mode=["updates", "messages"]):
- updates:  {node_name: partial_state} after each node -> timeline lines
- messages: (token_chunk, metadata) live from LLM calls inside nodes -> we
  print only the synthesize node's tokens, so the briefing types itself out.
"""
import os
import re
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
            try:
                st.write(s)
            except BrokenPipeError:
                pass  # console pipe died (e.g. `| head`) — the run and log go on

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except BrokenPipeError:
                pass


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('usage: python cli.py "your research question"')
    question = " ".join(sys.argv[1:])

    # Log naming convention: RUN_LABEL wins (e.g. RUN_LABEL=phase4-dyscalculia),
    # else a slug of the question. Reused labels get a time suffix, never clobbered.
    Path("runs").mkdir(exist_ok=True)
    label = os.getenv("RUN_LABEL") or re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:40].rstrip("-")
    log_path = Path("runs") / f"{label}.log"
    if log_path.exists():
        log_path = Path("runs") / f"{label}-{datetime.now():%H%M%S}.log"
    log = log_path.open("w")
    sys.stdout = _Tee(sys.__stdout__, log)
    sys.stderr = _Tee(sys.__stderr__, log)  # tracebacks land in the log too
    print(f"Question: {question}")

    graph = build_graph()
    n_sources = 0          # how many sources we've already announced
    n_searches = 0         # run-wide search counter (attempts reset per sub-question)
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
                    title = "Briefing (revised)" if revised else "Briefing"
                    print(f"\n{title}\n" + "-" * 60)
                    briefing_started = True
                print(text, end="", flush=True)
            continue

        for node, delta in chunk.items():
            if node == "plan":
                print(f"Planned {len(delta['sub_questions'])} sub-questions:")
                for sq in delta["sub_questions"]:
                    print(f"   {sq['id']}. {sq['question']}\n      why: {sq['rationale']}")
            elif node == "search":
                n_searches += 1
                print(f"Search #{n_searches}: \"{delta['last_query']}\" "
                      f"-> {len(delta['results'])} results")
            elif node == "read":
                for src in delta["sources"][n_sources:]:
                    print(f"Read [S{src['id']}] {src['title']} ({src['url']}) via {src['via']}")
                n_sources = len(delta["sources"])
            elif node == "evaluate":
                if delta.get("next_query"):
                    print(f"Insufficient, refining: \"{delta['next_query']}\"")
                else:
                    sq = delta["sub_questions"][delta["cursor"] - 1]
                    print(f"Sub-question {sq['id']}/{len(delta['sub_questions'])} "
                          f"{sq['status']}")
                    print("-" * 30)  # divider: this sub-question's chapter is closed
            elif node == "synthesize":
                print()  # close the briefing's token stream
            elif node == "reflect":
                if "sub_questions" in delta:
                    gaps = [sq for sq in delta["sub_questions"] if sq["status"] == "pending"]
                    print("Reflection: material gaps, extending research:")
                    for sq in gaps:
                        print(f"   + {sq['id']}. {sq['question']}")
                    briefing_started, revised = False, True
                elif delta.get("open_gaps"):
                    print("Reflection: gaps remain, budget spent, disclosing:")
                    for g in delta["open_gaps"]:
                        print(f"   ? {g}")
                else:
                    print("Reflection: the briefing answers the question")
            elif node == "verify":
                if delta["flagged"]:
                    print(f"Grounding: {len(delta['flagged'])} issue(s) flagged in Limitations")
                    for f in delta["flagged"]:
                        print(f"   ! {f}")
                else:
                    print("Grounding: every claim checks out")
                # the briefing streamed as the draft; the Limitations section is
                # the only part of `final` the reader hasn't seen yet
                parts = delta["final"].split("## Limitations")
                if len(parts) == 2:
                    print("\n## Limitations" + parts[1])

    print("-" * 60)
    print(f"Done: {n_sources} sources read")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
