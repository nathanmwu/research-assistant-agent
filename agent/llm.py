"""The single model seam: swap MODEL in config and nothing else changes."""
from google.genai.errors import ServerError
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.config import MODEL, SMART_MODEL

# A 20-call research run must survive one transient 5xx; retry only server
# errors (4xx bugs should fail loudly), with exponential backoff + jitter.
_RETRY = dict(retry_if_exception_type=(ServerError,),
              wait_exponential_jitter=True, stop_after_attempt=3)

_model = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
llm = _model.with_retry(**_RETRY)

# The premium tier, reserved for the prose the user actually reads (synthesize).
smart_llm = ChatGoogleGenerativeAI(model=SMART_MODEL, temperature=0).with_retry(**_RETRY)


def structured(schema: type):
    """The model, constrained to return instances of `schema` (a TypedDict)."""
    return _model.with_structured_output(schema).with_retry(**_RETRY)


def text_of(content) -> str:
    """Normalize AIMessage.content to plain text.

    Older Gemini models return a str; newer ones return a list of content-part
    dicts like {"type": "text", "text": ...} (plus signature-only parts with no
    text). Every consumer of message content goes through here.
    """
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p)
                   for p in content)


if __name__ == "__main__":  # smoke test (both tiers): python -m agent.llm
    from typing import TypedDict

    class Capital(TypedDict):
        country: str
        capital: str

    out = structured(Capital).invoke("What is the capital of France?")
    assert out["capital"].strip().lower().startswith("paris"), out
    streamed = "".join(text_of(c.content)
                       for c in smart_llm.stream("Reply with exactly: smart ok"))
    assert "smart ok" in streamed.lower(), streamed
    print(f"smoke ok: fast={MODEL} {out} | smart={SMART_MODEL} {streamed!r}")
