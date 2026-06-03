import asyncio
import base64
from google.genai import types
from agents.gemini_client import client
from schemas.extracted_page import ExtractedPage
from schemas.request import PDFContext
from config import EXTRACTION_MODEL, MAX_CONCURRENT_AGENTS
from pipeline.token_tracker import record_usage


def build_extraction_prompt(context: PDFContext) -> str:
    """Build extraction prompt. Annotation meanings from the instructor are injected here."""

    annotation_rules = []
    for ann in context.annotations:
        if ann.selected:
            name = ann.customName if ann.type == "other" and ann.customName else ann.label
            reason = ann.reason if ann.reason else "emphasize this on the slide"
            annotation_rules.append(f"- {ann.type} ({name}) means: {reason}")

    if not annotation_rules:
        annotation_rules = [
            "- circle / highlight = emphasize this on the slide",
            "- tick = include this as a key point",
            "- handwritten = treat as an instructor note",
        ]

    annotations_text = "\n".join(annotation_rules)

    return f"""
You are analysing ONE page of a teaching document. A downstream planner will
turn your output into PowerPoint slides, so your output must be COMPLETE and
PRECISE — not a summary.

Subject     : {context.subject}
Purpose     : {context.purpose}
Class level : {context.class_level}
Language    : {context.language}

═════════════════════════════════════════════════════════════════════════════
TASK 1 — Extract ALL textual content into `main_text`
═════════════════════════════════════════════════════════════════════════════

• Preserve EVERY question, every option, every definition, every formula,
  every paragraph of theory verbatim. Do NOT paraphrase, do NOT summarise,
  do NOT drop anything.
• Keep the natural READING ORDER. If the page is in two columns, read the
  LEFT column top-to-bottom first, then the RIGHT column top-to-bottom.
  Do not interleave columns.
• For MCQ-style content, keep the question stem, the exam tag (if any),
  and all four options together as a single chunk in the order they appear.
  Use clean newlines between question number, stem, exam tag, and options
  so the planner can split them later. Example shape:

      Q.661. A large number of fish swimming together
      SSC CPO Tier-II (27/09/2019)
      (a) herd  (b) shoal  (c) brood  (d) cache

• If the page has solutions / explanations / answer keys, include them too
  but clearly after a `Solutions:-` marker so the planner can identify them.
• Ignore obvious noise: page numbers, app-promo footers ("Download …"),
  watermarks, and any text that's clearly bleed-through from an adjacent
  page or column.

═════════════════════════════════════════════════════════════════════════════
TASK 2 — Identify EVERY SINGLE visual annotation (CRITICAL — DO NOT MISS ANY)
═════════════════════════════════════════════════════════════════════════════

Annotation interpretation rules provided by the instructor:
{annotations_text}

Rules for the `annotations` list you return:
• For EACH visible mark on the page produce ONE annotation entry.
• `target` must precisely identify WHAT is marked:
    - If a question number is circled / boxed, set target to that number
      with its prefix, e.g. "Q.661" or "30" or "Q.6". Be exact.
    - If an option is underlined (likely the correct answer), set target to
      "option (b) of Q.661" or similar.
    - If an exam tag is struck-through, set target to the exam tag text.
• `instruction` is the meaning of the mark in this context. Use the
  instructor's reason VERBATIM when it applies (e.g. copy "INCLUDE this
  question on a dedicated slide" exactly so the planner can pattern-match).
• Do NOT invent annotations that aren't visible.
• Do NOT skip annotations because they are repetitive — if 16 question
  numbers are circled, return 16 annotation entries (one per circle).
• COMMON MISTAKE: returning only 5-8 annotations when there are actually
  15-20+ marks on the page. Carefully scan the ENTIRE page from top to
  bottom. Count every circle, every tick, every highlight. If you see a
  pattern (e.g. many question numbers circled), make sure you catch ALL
  of them, not just the first few.
• When in doubt, include it. Missing an annotation is worse than including
  a borderline one.

═════════════════════════════════════════════════════════════════════════════
Skip rule
═════════════════════════════════════════════════════════════════════════════

Set `should_skip = true` ONLY when the page is genuinely useless:
a blank page, a pure cover/title page, an advert, or a table of contents
with no teaching content. A page with even ONE MCQ or ONE definition is
NOT skippable.
"""


# ── ASYNC — all pages in parallel ────────────────────────────────────────────

async def _extract_page_async(
    page_dict: dict,
    context: PDFContext,
    semaphore: asyncio.Semaphore,
) -> ExtractedPage | None:
    """
    Async: one page → Gemini Vision → ExtractedPage.
    Semaphore limits concurrent calls to stay within Gemini rate limits.
    """
    async with semaphore:
        prompt = build_extraction_prompt(context)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedPage
        )
        try:
            response = await client.aio.models.generate_content(
                model=EXTRACTION_MODEL,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=base64.b64decode(page_dict["base64"]),
                        mime_type=page_dict["mime_type"]
                    )
                ],
                config=config
            )
            record_usage("extraction", response.usage_metadata)
            extracted = response.parsed

        except Exception as e:
            print(f"  Page {page_dict['page_number']} — failed: {e}")
            return None

        # trust our page numbering, not Gemini's
        extracted.page_number = page_dict["page_number"]

        if extracted.should_skip:
            print(f"  Page {page_dict['page_number']} — skipped (blank/irrelevant)")
            return None

        print(f"  Page {page_dict['page_number']} — extracted OK")
        return extracted


async def extract_all_pages_async(
    pages: list[dict],
    context: PDFContext,
) -> list[ExtractedPage]:
    """
    Extract ALL pages in PARALLEL.

    Speed comparison on a 50-page PDF:
      Sequential (old): 50 × ~2s = ~100 seconds
      Parallel   (new): ceil(50/10) × ~2s = ~10 seconds

    Uses asyncio.Semaphore to cap concurrent calls at MAX_CONCURRENT_AGENTS.
    """
    sem = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
    print(f"  Extracting {len(pages)} pages in parallel (max {MAX_CONCURRENT_AGENTS} at once)...")

    tasks = [_extract_page_async(page, context, sem) for page in pages]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    extracted = []
    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            print(f"  Page {i + 1} — error: {result}")
        elif result is not None:
            extracted.append(result)

    # sort by page number — parallel calls return out of order
    extracted.sort(key=lambda p: p.page_number)
    print(f"\n  Extraction done — {len(extracted)} useful pages from {len(pages)} total")
    return extracted


# ── SYNC fallback ─────────────────────────────────────────────────────────────

def extract_page(page_dict: dict, context: PDFContext) -> ExtractedPage | None:
    """Sync single-page extraction — kept as fallback."""
    prompt = build_extraction_prompt(context)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ExtractedPage
    )
    try:
        response = client.models.generate_content(
            model=EXTRACTION_MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=base64.b64decode(page_dict["base64"]),
                    mime_type=page_dict["mime_type"]
                )
            ],
            config=config
        )
        extracted = response.parsed
    except Exception as e:
        print(f"  Page {page_dict['page_number']} — failed: {e}")
        return None

    extracted.page_number = page_dict["page_number"]
    if extracted.should_skip:
        print(f"  Page {page_dict['page_number']} — skipped")
        return None
    return extracted


def extract_all_pages(pages: list[dict], context: PDFContext) -> list[ExtractedPage]:
    """Sync sequential extraction — fallback only, not used in main pipeline."""
    extracted_pages = []
    for page in pages:
        print(f"  Extracting page {page['page_number']} of {len(pages)}...")
        result = extract_page(page, context)
        if result is not None:
            extracted_pages.append(result)
    print(f"\n  Extraction done — {len(extracted_pages)} useful pages from {len(pages)} total")
    return extracted_pages
