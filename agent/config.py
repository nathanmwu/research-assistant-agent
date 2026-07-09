"""All knobs in one place: keys via .env, model id, loop caps."""
import os

from dotenv import load_dotenv

load_dotenv()  # GOOGLE_API_KEY, TAVILY_API_KEY

# Two-tier models. Plumbing calls (plan/read/evaluate/reflect) run on the lite
# tier, whose free quota covers a ~20-40 call run. synthesize — the 1-2 calls
# per run the reader actually sees — runs on premium flash: its small free
# daily quota (20 req/day on this key) still covers 10+ runs at that rate.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
SMART_MODEL = os.getenv("GEMINI_SMART_MODEL", "gemini-2.5-flash")

# HEADLESS=0 pops a visible Chromium window per source read (demo/debug mode).
HEADLESS = os.getenv("HEADLESS", "1") != "0"

# Source credibility (Phase 7). UGC/social never enters a briefing; academic
# domains are a factual label — the per-sub-question *preference* between
# academic and general web is the planner's call, not a fixed policy here.
UGC_DOMAINS = (
    "linkedin.com", "facebook.com", "reddit.com", "x.com", "twitter.com",
    "quora.com", "medium.com", "instagram.com", "tiktok.com", "pinterest.com",
)
ACADEMIC_DOMAINS = (
    ".edu", ".gov", ".ac.uk", "doi.org", "ncbi.nlm.nih.gov", "arxiv.org",
    "nature.com", "science.org", "sciencedirect.com", "springer.com",
    "wiley.com", "tandfonline.com", "sagepub.com", "jstor.org",
    "frontiersin.org", "mdpi.com", "plos.org", "ieee.org", "acm.org",
    "cambridge.org", "academic.oup.com",
)

# Loop caps. Worst case is knowable before a run: ~21 searches, ~25 LLM calls.
MAX_SUB_QUESTIONS = 5
MAX_ATTEMPTS_PER_SUB_Q = 3  # 1 initial + 2 refined searches
RESULTS_PER_SEARCH = 5
READS_PER_SUB_Q = 2
MAX_REFLECTION_ROUNDS = 1
MAX_GAP_QUESTIONS = 2
SOURCE_CHAR_LIMIT = 8000
PAGE_TIMEOUT_S = 15
