import os

# ============================================================
# Store reports & logs directory
# Recommended: Use a relative path (e.g., "./reports") for local testing;
#            for production, consider using an absolute or configurable path.
STORE_FOLDER: str = os.environ.get("STORE_FOLDER", "./reports")
os.makedirs(STORE_FOLDER, exist_ok=True)

# ============================================================
# LLM (Language Model) Configuration
# DEFAULT_MODEL: The primary model used for general query and insight generation.
#                     Recommended: "gemini/gemini-2.0-flash" or your preferred model.
DEFAULT_MODEL: str = os.environ.get("LLM_MODEL", "gemini/gemini-2.0-flash")

# THINKING_MODEL: A specialized model variant used for generating the final detailed report.
#                     Recommended: "gemini/gemini-2.0-flash-thinking-exp-01-21"
THINKING_MODEL: str = os.environ.get("THINKING_MODEL", "gemini/gemini-2.0-flash-thinking-exp-01-21")

# Token limits for LLM calls.
# MAX_INPUT_TOKEN: Maximum number of tokens accepted by the model.
#                     Default: 1_048_576 (depending on your LLM specifications).
MAX_INPUT_TOKEN: int = int(os.environ.get("MAX_INPUT_TOKEN", "1_048_576"))

# SAFE_MAX_INPUT_TOKEN: A safety threshold (70% of MAX_INPUT_TOKEN) to avoid exceeding the model’s context window.
#                     Recommended: 70% of MAX_INPUT_TOKEN.
SAFE_MAX_INPUT_TOKEN: int = int(MAX_INPUT_TOKEN * 0.7)

# Maximum tokens allowed for output responses.
# MAX_OUTPUT_TOKEN: For general responses (e.g., query generation).
#                     Default: 8_192 (depending on your LLM specifications).
MAX_OUTPUT_TOKEN: int = int(os.environ.get("MAX_OUTPUT_TOKEN", "8_192"))

# THINK_MAX_OUTPUT_TOKEN: For generating comprehensive outputs (e.g., final report).
#                     Default: 65_536 (depending on your LLM specifications).
THINK_MAX_OUTPUT_TOKEN: int = int(os.environ.get("THINK_MAX_OUTPUT_TOKEN", "65_536"))

# Temperature settings to control randomness.
# DEFAULT_TEMPERATURE: General default randomness.
DEFAULT_TEMPERATURE: float = float(os.environ.get("DEFAULT_TEMPERATURE", "0.3"))
# QUERY_TEMPERATURE: Higher randomness for generating creative and diverse queries.
QUERY_TEMPERATURE: float = float(os.environ.get("QUERY_TEMPERATURE", "0.7"))
# ANSWER_TEMPERATURE: Lower randomness for deterministic, fact-based answers (especially in final reports).
ANSWER_TEMPERATURE: float = float(os.environ.get("ANSWER_TEMPERATURE", "0.1"))

# ============================================================
# Retry and Delay Settings
# MAX_RETRIES: Number of times to retry an LLM call or web operation upon failure.
#                     Recommended: 3 retries.
MAX_RETRIES: int = int(os.environ.get("MAX_RETRIES", "3"))

# COOL_DOWN_DELAY: Seconds to wait between operations to avoid rate limits.
#                     Recommended: 4 seconds (adjust based on API limits).
COOL_DOWN_DELAY: int = int(os.environ.get("COOL_DOWN_DELAY", "4"))

# ============================================================
# GenerateInsights Configuration
# NUM_INSIGHTS: Number of key insights to extract from content.
#                     Recommended: 5 insights per content chunk.
NUM_INSIGHTS: int = int(os.environ.get("NUM_INSIGHTS", "5"))

# NUM_FOLLOWUP_QUESTIONS: Number of follow-up questions to generate from each content analysis.
#                     Recommended: 2 follow-up question.
NUM_FOLLOWUP_QUESTIONS: int = int(os.environ.get("NUM_FOLLOWUP_QUESTIONS", "2"))

# ============================================================
# QueryGenerator Configuration
# MAX_NUM_OF_QUERIES: Maximum number of search queries to generate in one call.
#                     Recommended: 3 queries.
MAX_NUM_OF_QUERIES: int = int(os.environ.get("MAX_NUM_OF_QUERIES", "3"))

# MAX_RESEARCH_GOALS: Maximum number of research goals to propose in one call.
#                     Recommended: 3 research goals.
MAX_RESEARCH_GOALS: int = int(os.environ.get("MAX_RESEARCH_GOALS", "3"))

# ============================================================
# WebSearch Configuration
# MAX_SEARCH_RESULTS: Maximum number of search results to retrieve per query.
#                     Recommended: 2 result per query to focus on high-quality matches.
MAX_SEARCH_RESULTS: int = int(os.environ.get("MAX_SEARCH_RESULTS", "2"))

# MAX_CONCURRENT_SEARCHES: Maximum number of concurrent web searches.
#                     Recommended: 3 concurrent searches to balance speed and resource usage.
MAX_CONCURRENT_SEARCHES: int = int(os.environ.get("MAX_CONCURRENT_SEARCHES", "3"))

# ============================================================
# SearchAgent Configuration
# RESEARCH_DEPTH: Number of iterations (or rounds) for follow-up question processing.
#                     Recommended: 2 rounds for iterative refinement.
RESEARCH_DEPTH: int = int(os.environ.get("RESEARCH_DEPTH", "2"))

# ============================================================
# SearxNG Configuration
# SearXNG_URL: The base URL of the SearXNG.
SEARXNG_URL: str = os.environ.get("SEARXNG_URL", "http://localhost:8080")
