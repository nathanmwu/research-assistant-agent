"""All knobs in one place: keys via .env, model id, loop caps."""
import os

from dotenv import load_dotenv

load_dotenv()  # GOOGLE_API_KEY, TAVILY_API_KEY

# ponytail: lite tier — full flash's free quota (20 req/day) can't cover one
# ~20-call run. For demo-day prose quality: GEMINI_MODEL=gemini-2.5-flash (paid).
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# Loop caps. Worst case is knowable before a run: ~21 searches, ~25 LLM calls.
MAX_SUB_QUESTIONS = 5
MAX_ATTEMPTS_PER_SUB_Q = 3  # 1 initial + 2 refined searches
RESULTS_PER_SEARCH = 5
READS_PER_SUB_Q = 2
MAX_REFLECTION_ROUNDS = 1
MAX_GAP_QUESTIONS = 2
SOURCE_CHAR_LIMIT = 8000
PAGE_TIMEOUT_S = 15
