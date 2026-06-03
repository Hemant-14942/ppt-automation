import os
from dotenv import load_dotenv

load_dotenv()

# API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Models
EXTRACTION_MODEL   = "gemini-2.5-flash"
PLANNING_MODEL     = "gemini-2.5-pro"
WRITING_MODEL      = "gemini-2.5-flash"
CRITIC_MODEL       = "gemini-2.5-pro"
ORCHESTRATOR_MODEL = "gemini-2.5-flash"
PROFILER_MODEL     = "gemini-2.5-flash"  

# PDF
PDF_DPI = 110

# PPT
OUTPUT_DIR  = "outputs"
UPLOAD_DIR  = "uploads"

# Reference template — every slide is cloned from this file so the look matches.
# Path is relative to repo root (one level up from backend/).
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT   = os.path.dirname(_BACKEND_DIR)
TEMPLATE_PPTX = os.path.join(
    _REPO_ROOT, "assets", "reference_ppts", "Common Template.pptx"
)

# Agent settings
# MAX_SLIDES is effectively NO limit — the deck size is purely content-driven.
# If the PDF has 50 annotated questions, we produce 50+ slides. No artificial cap.
MAX_SLIDES            = 500
MIN_SLIDES            = 3
MAX_BULLETS           = 5
MAX_BULLET_WORDS      = 12          # bullets longer than this get trimmed by QC
MAX_CONCURRENT_AGENTS = 20          # max parallel Gemini calls — stays within rate limits

# Visual critic — max CONTENT-REWRITE rounds after the initial full-deck pass
# (Phase 3: raised from 1 so the loop can actually converge on hard slides).
MAX_VISUAL_RETRIES = 2

# Visual critic — max PAGINATION rounds. When the critic confirms a free-body
# slide still overflows, we re-split it (more aggressively) instead of asking
# the writer to delete content. Each round bumps the overflow "pressure".
MAX_PAGINATION_ROUNDS = 2

# Skip visual critic entirely (saves many API calls)
# Set VISUAL_CRITIC_SKIP=true in .env to skip
VISUAL_CRITIC_SKIP = os.getenv("VISUAL_CRITIC_SKIP", "false").lower() == "true"

# Style memory
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory")
STYLE_YAML = os.path.join(MEMORY_DIR, "style.yaml")