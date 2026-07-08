"""Offline test for the UI's one pure function. The page itself is checked by
eye per the testing strategy — Streamlit rendering isn't pytest territory.
(app.py's script body is guarded behind main(), so importing it is side-effect
free.)
"""
from app import _plan_markdown


def test_plan_markdown_statuses_and_cursor_spinner():
    subs = [
        {"id": 1, "question": "q1", "rationale": "r", "status": "answered"},
        {"id": 2, "question": "q2", "rationale": "r", "status": "pending"},
        {"id": 3, "question": "q3", "rationale": "r", "status": "thin"},
    ]
    md = _plan_markdown(subs, cursor=1)
    assert "`[x]` **1.**" in md
    assert "`[>]` **2.**" in md  # the row under research gets the marker while pending
    assert "`[!]` **3.**" in md


def test_plan_markdown_no_marker_when_run_is_over():
    subs = [{"id": 1, "question": "q", "rationale": "r", "status": "answered"}]
    assert "[>]" not in _plan_markdown(subs, cursor=-1)
