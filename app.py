"""Streamlit UI — the same dual stream the CLI consumes, rendered live.

Run:        .venv/bin/streamlit run app.py
Demo mode:  HEADLESS=0 .venv/bin/streamlit run app.py
            (pops a visible Chromium window for every source read, so you can
            watch the agent browse right next to the app)

Streamlit reruns this whole script on every interaction, so: the run is one
blocking loop over graph.stream within a single script run, placeholders are
updated in place as events arrive, and the finished run is pinned into
st.session_state so later reruns keep showing it. No threads, no async.
"""
import re
from pathlib import Path

import streamlit as st

from agent.graph import build_graph
from agent.llm import text_of
from agent.state import initial_state

_STATUS_ICON = {"pending": "[ ]", "answered": "[x]", "thin": "[!]"}


def _plan_markdown(subs: list[dict], cursor: int) -> str:
    """The plan as a live checklist; the row under research gets the [>] marker."""
    lines = ["#### Research plan"]
    for i, sq in enumerate(subs):
        icon = "[>]" if i == cursor and sq["status"] == "pending" else _STATUS_ICON[sq["status"]]
        marker = " *(academic)*" if sq.get("evidence") == "academic" else ""
        lines.append(f"`{icon}` **{sq['id']}.** {sq['question']}{marker}")
    return "\n\n".join(lines)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].rstrip("-")


def main() -> None:
    st.set_page_config(page_title="Research Assistant", layout="wide")
    st.title("Autonomous Research Assistant")
    st.caption("plan → search → read → evaluate → synthesize → reflect → verify · "
               "a LangGraph agent that shows its work · a run takes 2–5 minutes")

    question = st.chat_input("Ask a research question worth 20–30 minutes of human effort…")

    if not question:
        last = st.session_state.get("last")
        if last:  # rerun after completion — keep showing the finished briefing
            st.markdown(f"**{last['question']}**")
            col_main, col_feed = st.columns([3, 2])
            col_main.markdown(last["final"])
            with col_feed:
                st.markdown(_plan_markdown(last["subs"], cursor=-1))
                with st.expander(f"activity · {len(last['events'])} events"):
                    st.markdown("\n\n".join(last["events"]))
        return

    st.markdown(f"**{question}**")
    col_main, col_feed = st.columns([3, 2])
    plan_panel = col_feed.empty()
    feed = col_feed.status("researching…", expanded=True)
    briefing_panel = col_main.empty()

    subs: list[dict] = []
    cursor = 0
    events: list[str] = []  # mirrors the feed; written to runs/ at the end
    acc, revised, final = "", False, ""
    n_sources = 0
    n_searches = 0  # run-wide counter (state's attempts resets per sub-question)

    def log(line: str) -> None:
        events.append(line)
        feed.markdown(line)

    graph = build_graph()
    stream = graph.stream(initial_state(question),
                          config={"recursion_limit": 100},
                          stream_mode=["updates", "messages"])

    for mode, chunk in stream:
        if mode == "messages":
            msg, meta = chunk
            if meta.get("langgraph_node") != "synthesize":
                continue
            tok = text_of(msg.content)
            if tok:
                acc += tok
                head = "## Briefing (revised)\n\n" if revised else "## Briefing\n\n"
                briefing_panel.markdown(head + acc + " ▌")
            continue

        for node, delta in chunk.items():
            if node == "plan":
                subs, cursor = delta["sub_questions"], 0
                plan_panel.markdown(_plan_markdown(subs, cursor))
                log(f"Planned {len(subs)} sub-questions")
            elif node == "search":
                n_searches += 1
                log(f"Search #{n_searches}: \"{delta['last_query']}\" "
                    f"-> {len(delta['results'])} results")
            elif node == "read":
                for src in delta["sources"][n_sources:]:
                    kind = " [academic]" if src["kind"] == "academic" else ""
                    log(f"Read [S{src['id']}] [{src['title']}]({src['url']}) "
                        f"via {src['via']}{kind}")
                n_sources = len(delta["sources"])
            elif node == "evaluate":
                if delta.get("next_query"):
                    log(f"Insufficient, refining: \"{delta['next_query']}\"")
                else:
                    subs, cursor = delta["sub_questions"], delta["cursor"]
                    plan_panel.markdown(_plan_markdown(subs, cursor))
                    done = subs[delta["cursor"] - 1]
                    log(f"Sub-question {done['id']} {done['status']}")
                    log("---")  # divider: chapter closed
            elif node == "reflect":
                if "sub_questions" in delta:
                    subs = delta["sub_questions"]
                    plan_panel.markdown(_plan_markdown(subs, cursor))
                    gaps = [sq for sq in subs if sq["status"] == "pending"]
                    log("Reflection: material gaps, extending research: "
                        + " / ".join(sq["question"] for sq in gaps))
                    acc, revised = "", True  # next synthesize streams a fresh draft
                elif delta.get("open_gaps"):
                    log("Reflection: gaps remain, budget spent, disclosed in Limitations")
                else:
                    log("Reflection: the briefing answers the question")
            elif node == "verify":
                final = delta["final"]
                for f in delta["flagged"]:
                    log(f"! {f}")
                verdict = (f"{len(delta['flagged'])} issue(s) flagged"
                           if delta["flagged"] else "every claim checks out")
                log(f"Grounding: {verdict}")

    head = "## Briefing (revised)\n\n" if revised else "## Briefing\n\n"
    briefing_panel.markdown(head + (final or acc))  # final = draft + Limitations
    feed.update(label=f"Done: {n_sources} sources read", state="complete")

    # Transparency rule: every run leaves a full artifact in runs/.
    Path("runs").mkdir(exist_ok=True)
    (Path("runs") / f"ui-{_slug(question)}.log").write_text(
        f"Question: {question}\n" + "\n".join(events) + "\n\n" + (final or acc) + "\n")

    st.session_state.last = {"question": question, "final": final or acc,
                             "subs": subs, "events": events}


if __name__ == "__main__":
    main()
