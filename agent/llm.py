"""The single model seam: swap MODEL in config and nothing else changes."""
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.config import MODEL

llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)


def structured(schema: type):
    """The model, constrained to return instances of `schema` (a TypedDict)."""
    return llm.with_structured_output(schema)


if __name__ == "__main__":  # smoke test: python -m agent.llm
    from typing import TypedDict

    class Capital(TypedDict):
        country: str
        capital: str

    out = structured(Capital).invoke("What is the capital of France?")
    assert out["capital"].strip().lower().startswith("paris"), out
    print(f"smoke ok: {out}")
