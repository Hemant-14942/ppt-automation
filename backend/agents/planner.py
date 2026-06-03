import json
import re
from google.genai import types
from agents.gemini_client import client
from schemas.extracted_page import ExtractedPage
from schemas.slide_plan import FullSlidePlan
from schemas.request import PDFContext
from config import PLANNING_MODEL, MIN_SLIDES
from pipeline.token_tracker import record_usage


# ── Annotation-driven "include" detection ────────────────────────────────────
#
# When the instructor configures an annotation type in the frontend with a
# reason like "include this question" / "mark important" / "do this on a
# slide", the extractor copies that reason into Annotation.instruction.
#
# We detect those "include"-style instructions so the planner knows that EVERY
# annotated item with such an instruction must get its own dedicated slide.

_INCLUDE_HINTS = (
    "include", "dedicated slide", "own slide", "must appear",
    "emphasize", "highlight as", "mark important", "key point",
    "important", "tick", "do this", "instructor wants",
)

def _is_include_instruction(instr: str | None) -> bool:
    """True if the instruction looks like 'include this on a slide'."""
    if not instr:
        return False
    low = instr.lower()
    return any(h in low for h in _INCLUDE_HINTS)


def _strategy_block(strategy) -> str:
    """Inject the Profiler's DeckStrategy as structural guidance (if available)."""
    if strategy is None:
        return ""
    one_per = (
        "Because this is a question-style document, EVERY question/problem MUST "
        "get its own slide (one_item_per_slide)."
        if strategy.one_item_per_slide else
        "Group related theory together; do not force one-item-per-slide."
    )
    return f"""
═════════════════════════════════════════════════════════════════════════════
DECK STRATEGY (from the Profiler — high-level shape for THIS document)
═════════════════════════════════════════════════════════════════════════════
  Profile : {strategy.profile.value}
  Density : {strategy.density.value}
  {one_per}
  • Prefer theory_slide for explanatory passages: {strategy.prefer_theory_for_concepts}
  • Target ~{strategy.target_bullets_per_theory_slide} points per theory slide
    (the system will paginate longer ones automatically — do NOT drop content).
  Rationale: {strategy.rationale}
"""


def build_planning_prompt(context: PDFContext, strategy=None) -> str:
    """
    Build the planning prompt using form context.
    Purpose and class level change how slides are structured, but content
    (especially explicit instructor annotations) ALWAYS wins over heuristics.
    The optional DeckStrategy (Phase 2) adds document-level shape guidance.
    """

    # purpose-specific rules — these are SOFT guidance, not hard caps
    purpose_rules = {
        "Lecture notes": """
- Full detailed coverage — every concept and example gets its own slide
- Include all diagrams and examples
- Use theory_slide for explanations, content_image for diagram pages
- There is NO limit on slide count — create as many slides as the content needs
""",
        "Revision": """
- Default style: concise bullets, no long explanations, skip non-essential examples
- BUT if the PDF is a QUESTION BANK (many MCQs / PYQs / numbered problems),
  every annotated/important question MUST get its own dedicated slide —
  do NOT sample, do NOT pick "representative" questions, do NOT cap at any number.
- If the PDF is a CONCEPT-revision sheet (definitions, formulas, key points
  with no questions), keep the deck short (5-10 slides) using theory_slide.
- There is NO limit on slide count — create as many slides as the content needs.
  If there are 30 annotated questions, create 30+ slides.
""",
        "DPP": """
- Each problem in the PDF gets exactly ONE slide (question + hints, no full solution)
- Group by difficulty if visible
- There is NO limit on slide count — one slide per problem, however many there are
""",
        "Assignment": """
- Each question in the PDF gets exactly ONE slide — questions only, no answers
- There is NO limit on slide count — one slide per question
""",
        "Test paper": """
- Format like an exam paper — each question on its own slide
- Questions grouped by section
- Include marks allocation if visible
- There is NO limit on slide count — one slide per question
""",
        "Formula sheet": """
- One formula or concept per slide
- Large text, minimal clutter
- Use theory_slide for visual formulas
- There is NO limit on slide count
""",
        "Chapter summary": """
- Overview of the full chapter — one topic per slide
- There is NO limit on slide count
""",
        "Mind map / overview": """
- Show topic connections — one major topic per slide
- Use theory_slide where possible
- There is NO limit on slide count
""",
        "Quick recap": """
- Maximum 5-6 slides — only the most critical points (exception: if the PDF
  is a question bank, every annotated question still gets its own slide)
- Very concise bullets — max 3 per slide
""",
    }

    rules = purpose_rules.get(context.purpose, f"""
- Total slide count is content-driven — NO upper cap. Min {MIN_SLIDES}.
- Create as many slides as the content demands.
- Balance detail and brevity per slide, but never skip content.
""")

    # tell the planner what the instructor configured per annotation TYPE
    annotation_meanings_block = ""
    if context.annotations:
        lines = []
        for ann in context.annotations:
            if not ann.selected:
                continue
            name = ann.customName if ann.type == "other" and ann.customName else ann.label
            reason = (ann.reason or "").strip() or "emphasize this on the slide"
            include_flag = " [INCLUDE-ON-DEDICATED-SLIDE]" if _is_include_instruction(reason) else ""
            lines.append(f"  - {ann.type} ({name}){include_flag}: {reason}")
        if lines:
            annotation_meanings_block = (
                "\nInstructor-defined annotation meanings (from the frontend form):\n"
                + "\n".join(lines)
                + "\n"
            )

    return f"""
You are an expert teacher and presentation designer.

Subject: {context.subject}
Purpose: {context.purpose}
Class level: {context.class_level}
Language: {context.language}
Batch: {context.batch}
{f"Extra context: {context.extra_context}" if context.extra_context else ""}
{annotation_meanings_block}
{_strategy_block(strategy)}
You are given the FULL extracted content from a teaching PDF — one object per page.
Each page object has the complete main_text PLUS a list of annotations the
extractor found on that page (e.g. a circle on "Q.631", a square on
"Question number 30"). The annotations carry the instructor's intent.

Your job is to design a slide deck whose LENGTH is driven by content, not a
fixed count. There is ABSOLUTELY NO CAP on the number of slides you can create.
If the content needs 50 slides, create 50. If it needs 100, create 100.

═════════════════════════════════════════════════════════════════════════════
TOP-PRIORITY RULE — ANNOTATIONS ARE INSTRUCTIONS, NOT DECORATIONS
═════════════════════════════════════════════════════════════════════════════

If an annotation's instruction matches the instructor's "include" intent
(e.g. "INCLUDE this question on a dedicated slide", "emphasize on the slide",
"mark important", "key point"), then:

  • EVERY such annotated item MUST appear on its own dedicated slide.
  • The "annotation_count_with_include_intent" field on each page tells you
    EXACTLY how many such items live on that page. You MUST emit at LEAST
    that many body slides for that page.
  • Look at "annotated_targets_that_need_their_own_slide" — it lists the
    exact question numbers / labels that each need a slide. Walk through
    that list IN ORDER and emit one slide per target. Do not skip any
    target just because it looks similar to a neighbour.
  • Do NOT sample. Do NOT pick "representative" examples. Do NOT merge
    multiple annotated items into one slide. Do NOT skip any.
  • There is NO maximum slide limit. If a page has 20 circled question
    numbers, create 20 slides. If across all pages there are 50 annotated
    items, you MUST produce at least 50 body slides.
  • If a page has 16 circled question numbers (e.g. Q.660-Q.676), the deck
    MUST have 16 slides for those 16 questions — one per number, even if
    the questions look topically similar. The instructor circled all 16
    because they want all 16 reviewed.
  • Self-check before finalising: for every page p, count how many slides
    in your plan have p in source_pages. That count MUST be ≥
    annotation_count_with_include_intent for p. If it isn't, add the
    missing slides BEFORE returning.
  • COMMON FAILURE MODE: producing only 8-12 slides when there are 20+
    annotated items. This is WRONG. Check your total against the required
    minimum BEFORE returning.

Annotations that just describe formatting (underline marking a correct
answer, a struck-out exam tag, a handwritten 'o' next to options) are
INFORMATIONAL — use them when filling slides, but they do NOT each create
a new slide on their own.

═════════════════════════════════════════════════════════════════════════════
Purpose-specific guidance for "{context.purpose}"
═════════════════════════════════════════════════════════════════════════════
{rules}

═════════════════════════════════════════════════════════════════════════════
Available slide templates (pick the BEST fit for each piece of content)
═════════════════════════════════════════════════════════════════════════════

  STRUCTURAL
  - title_slide        → very first slide: auto compose from subject + purpose
  - recap_slide        → only when the PDF references a "previous lecture / last class"
  - topics_slide       → only when the PDF lists the agenda / topics to be covered
  - section_heading    → use SPARINGLY between major topic shifts; NEVER between
                         consecutive MCQs of the same set

  BODY
  - theory_slide       → definitions, explanations, formulas, key rules — 3-4 points
                         If a theory passage has more than 4 points, split it into
                         multiple theory_slide entries (same title, 3-4 points each).
  - table_slide        → a page whose primary content is a TABLE (rows × columns of
                         numbers, factors, comparison data, schedules). Pick this
                         WHENEVER the source shows tabular data that loses meaning if
                         prosified into bullets — discount-factor tables, comparison
                         charts, score grids, periodicity tables, etc. The writer
                         will preserve the table structure (headers + rows).
  - theory_table_slide → a page where a SHORT theory explanation directly accompanies
                         a SMALL reference table (≤ ~6 rows × ~5 columns) and the two
                         belong together. Use this only when both fit comfortably on
                         one slide. If the theory is long OR the table is large,
                         split into separate theory_slide + table_slide entries.
                         Decision recipe:
                           - theory ≤ 3 short bullets AND table ≤ 6 rows × 5 cols
                             → theory_table_slide
                           - otherwise → theory_slide(s) + table_slide
  - passage_slide      → a CLOZE / reading-comprehension PASSAGE shown VERBATIM with
                         its blanks intact (e.g. "__X__", "__Y__", ".....(1).....").
                         Use this — NOT theory_slide — whenever the source has a
                         "Directions (Q. n-m): Cloze Test / Comprehension – Passage k"
                         block. The passage is reproduced word-for-word so students
                         can read the gaps; the actual fill-in questions become
                         separate mcq_slide/question_only slides AFTER it.
  - mcq_slide          → MCQ with long options (full sentences / phrases)
  - mcq_grid_slide     → MCQ with short options (1-3 words, e.g. single-word substitutions)
  - question_only      → long-answer / subjective question without 4 options
  - pyq_slide          → MCQ marked as "PYQ" / "past year" / has exam-year info (long options)
  - pyq_grid_slide     → PYQ MCQ with short options
  - pyq_question_only  → PYQ subjective question

  CLOSING
  - summary            → 4-6 key takeaways from the whole deck
  - homework_slide     → only when PDF has practice tasks / "do at home" / assignment
  - thank_you_slide    → always the final slide

═════════════════════════════════════════════════════════════════════════════
Structural rules
═════════════════════════════════════════════════════════════════════════════

1. Slide 1 MUST be title_slide.
2. The deck MUST end with thank_you_slide.
3. Put summary right before thank_you (or before homework if present).
4. homework_slide is OPTIONAL — include only if the PDF actually lists practice tasks.
5. recap_slide and topics_slide are OPTIONAL — include only if such content exists.
6. section_heading is used to separate major topics. Do NOT insert one between
   two consecutive MCQs from the same exercise.
7. Choose mcq_slide vs mcq_grid_slide by option length:
     - all four options ≤ 3 words   → mcq_grid_slide
     - otherwise                    → mcq_slide
8. Mark a question as pyq_* if it carries year info (e.g., "SSC CGL 11/09/2019",
   "JEE 2022", "NEET 2021"). Otherwise use the plain mcq_* variant.
9. Every question goes on its own slide — never merge multiple questions.
10. If the PDF contains BOTH theory passages AND annotated questions, include
    both kinds of slides: theory_slides for the theory passages, mcq/pyq
    slides for every annotated question.
11. The slide TITLE for an mcq/pyq slide should be the question stem itself
    (e.g. "A large number of fish swimming together"), NOT a number like
    "Q.661". This makes the deck student-friendly.
12. TABLE coverage (CRITICAL — do not prosify tables):
    If the source page shows a rendered TABLE (a row × column grid of
    values — discount factors, comparison data, schedules, score grids,
    multi-row formulas with named columns), DO NOT cram its cells into
    theory bullets. Tables turn into unreadable prose ("For year 1 the
    factors are 0.869, 0.877, 0.885..."). Instead:
      (a) If the page is mostly that table → ONE table_slide.
      (b) If the page has a short paragraph PLUS a small table that explain
          each other → ONE theory_table_slide (bullets above, table below).
      (c) If the table is referenced by later questions, keep the table on
          ITS OWN slide (table_slide) — the question slides that follow do
          NOT re-render the table; they just refer to it.
      (d) Never split one logical table across multiple slides; if the
          table is very large, use table_slide and let the renderer
          auto-shrink the font.
    The writer will extract headers + rows from the source; the planner's
    job is just to pick the right layout.
13. CLOZE / READING-COMPREHENSION coverage (CRITICAL — do not under-cover):
    If the PDF contains cloze/comprehension passages (a paragraph with numbered
    or lettered blanks like "__X__", "__Y__", ".....(1).....", followed by
    answer options), then for EVERY passage in the document you MUST emit:
      (a) ONE passage_slide reproducing that passage VERBATIM with its blanks
          intact (title = a short label like "Passage 1"; the planner does NOT
          fill the text — the writer copies it word-for-word from the source).
      (b) ONE question slide (mcq_slide / mcq_grid_slide / question_only) for
          EACH blank in that passage, in order, carrying that blank's options.
    Do NOT collapse multiple passages into one slide. Do NOT keep only the first
    passage. If the source has Passage 1, Passage 2, Passage 3 … each one gets
    its own passage_slide plus its own set of per-blank question slides. The
    blanks must stay as blanks on the passage_slide — never fill them in.

═════════════════════════════════════════════════════════════════════════════
What to fill for each slide
═════════════════════════════════════════════════════════════════════════════

- slide_number    → 1-indexed
- title           → see rule 11 (question stem for MCQs; topic for theory)
- template        → from the list above
- source_pages    → list of page numbers from the PDF that this slide draws from
- key_points      → 3-5 short phrases describing what the slide carries
                    (for MCQs: the 4 options; for theory: the bullet points;
                    for pyq: also include the exam tag)
- emphasis        → list of instructor-marked items relevant to this slide
                    (e.g. ["circle on Q.661 — include this question"])
- include_diagram → true if the source page had a diagram worth showing

Create the slide plan now. Do NOT pad with filler. Do NOT skip annotated items.
"""


# A cloze / comprehension passage is introduced by a "Directions (Q n-m): …"
# header. Each DISTINCT question-range = one passage that needs its own slide.
_PASSAGE_DIR_RE = re.compile(
    r'directions?\s*\(\s*(?:q\.?\s*(?:no\.?)?\s*)?(\d+)\s*[-–—]\s*(\d+)\s*\)',
    re.IGNORECASE,
)


def _source_passage_ranges(extracted_pages: list[ExtractedPage]) -> list[str]:
    """Distinct question-ranges of cloze/comprehension passages found in the source."""
    ranges: list[str] = []
    seen: set[str] = set()
    for p in extracted_pages:
        for m in _PASSAGE_DIR_RE.finditer(p.main_text or ""):
            key = f"{m.group(1)}-{m.group(2)}"
            if key not in seen:
                seen.add(key)
                ranges.append(key)
    return ranges


def _count_source_passages(extracted_pages: list[ExtractedPage]) -> int:
    return len(_source_passage_ranges(extracted_pages))


def _count_plan_passages(plan: FullSlidePlan) -> int:
    return sum(1 for s in plan.slides if s.template.value == "passage_slide")


def _count_include_annotations(page: ExtractedPage) -> int:
    """How many annotations on this page carry an 'include on its own slide' intent."""
    return sum(1 for a in page.annotations if _is_include_instruction(a.instruction))


def _summarize_include_targets(page: ExtractedPage) -> list[str]:
    """Compact list of the annotation TARGETS that must each get a slide. No limit."""
    targets = []
    for a in page.annotations:
        if _is_include_instruction(a.instruction):
            t = (a.target or "").strip()
            if t:
                targets.append(t)
    return targets


def _global_summary(extracted_pages: list[ExtractedPage]) -> str:
    """Top-of-prompt summary the planner reads BEFORE the per-page JSON."""
    total_include = sum(_count_include_annotations(p) for p in extracted_pages)
    per_page = []
    for p in extracted_pages:
        n = _count_include_annotations(p)
        if n > 0:
            targets = _summarize_include_targets(p)
            targets_str = ", ".join(targets[:10])
            if len(targets) > 10:
                targets_str += f" ... and {len(targets) - 10} more"
            per_page.append(
                f"page {p.page_number}: {n} item(s) marked for inclusion "
                f"[{targets_str}]"
            )
    if total_include == 0:
        return (
            "DECK SHAPE — no annotated items detected. Plan based on the text "
            "content only, following the purpose-specific guidance above.\n"
            "Create as many slides as the content demands — there is no upper limit."
        )
    return (
        f"⚠️ HARD CONSTRAINT — DECK SHAPE ⚠️\n"
        f"The extractor found {total_include} item(s) the instructor "
        f"marked for inclusion on a dedicated slide:\n  - "
        + "\n  - ".join(per_page)
        + f"\n\n"
        f"MINIMUM body slides required: {total_include} "
        f"(one per annotated item). This is NON-NEGOTIABLE.\n"
        f"Plus: title_slide at start, summary + thank_you_slide at end.\n"
        f"You may add theory_slides for any non-question theory content, "
        f"and section_heading between major topic shifts.\n\n"
        f"YOUR PLAN WILL BE REJECTED if it has fewer than {total_include} "
        f"body slides. Do NOT approximate. Do NOT sample. Include ALL {total_include}."
    )


MAX_PLAN_RETRIES = 2


def plan_slides(
    extracted_pages: list[ExtractedPage],
    context: PDFContext,
    strategy=None,
) -> FullSlidePlan:
    """
    Takes all extracted pages + context.
    Returns a FullSlidePlan object.

    Key design choices:
      • main_text is sent IN FULL — no truncation. The planner cannot make
        good decisions if it can't see most of the source content.
      • Each page carries an 'annotation_count_with_include_intent' field so
        the planner knows exactly how many dedicated slides each page needs.
      • A global DECK SHAPE summary sits at the top of the prompt so the
        planner sees the required slide count BEFORE reading page details.
      • If the planner returns fewer body slides than annotated items demand,
        we RETRY with explicit feedback about the shortfall.
    """

    pages_data = []
    for page in extracted_pages:
        include_n = _count_include_annotations(page)
        include_targets = _summarize_include_targets(page)
        pages_data.append({
            "page_number":        page.page_number,
            "content_type":       page.content_type,
            "main_text":          page.main_text,
            "diagrams_described": page.diagrams_described,
            "instructor_notes":   page.instructor_notes,
            "annotation_count_with_include_intent": include_n,
            "annotated_targets_that_need_their_own_slide": include_targets,
            "annotations": [
                {
                    "type":        ann.type,
                    "target":      ann.target,
                    "instruction": ann.instruction,
                    "is_include_intent": _is_include_instruction(ann.instruction),
                }
                for ann in page.annotations
            ]
        })

    prompt = build_planning_prompt(context, strategy)
    summary = _global_summary(extracted_pages)

    # Detect cloze/comprehension passages so we can REQUIRE one passage_slide each.
    passage_ranges = _source_passage_ranges(extracted_pages)
    expected_passages = len(passage_ranges)
    passage_block = ""
    if expected_passages:
        passage_block = (
            f"\n\n⚠️ PASSAGE COVERAGE — HARD CONSTRAINT ⚠️\n"
            f"The source contains {expected_passages} distinct cloze/comprehension "
            f"passage(s), identified by these Directions ranges: "
            f"{', '.join(passage_ranges)}.\n"
            f"You MUST emit EXACTLY ONE passage_slide for EACH of these "
            f"{expected_passages} passages (reproduce the passage verbatim, blanks "
            f"intact), PLUS one question slide per blank. Do NOT drop, merge, or "
            f"skip any passage. Your plan will be REJECTED if it has fewer than "
            f"{expected_passages} passage_slides.\n"
        )

    full_prompt = (
        f"{prompt}\n\n"
        f"{summary}"
        f"{passage_block}\n\n"
        f"Here is the extracted page data (full text — do not skip any):\n"
        f"{json.dumps(pages_data, indent=2, ensure_ascii=False)}"
    )

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=FullSlidePlan
    )

    expected_min_body = sum(_count_include_annotations(p) for p in extracted_pages)

    plan = None
    for attempt in range(1, MAX_PLAN_RETRIES + 2):
        current_prompt = full_prompt

        if attempt > 1 and plan is not None:
            actual_body = sum(
                1 for s in plan.slides
                if s.template.value in {
                    "theory_slide", "mcq_slide", "mcq_grid_slide", "question_only",
                    "pyq_slide", "pyq_grid_slide", "pyq_question_only",
                }
            )
            actual_passages = _count_plan_passages(plan)
            shortfall_lines = ["\n\n⚠️ RETRY — YOUR PREVIOUS PLAN WAS REJECTED."]
            if actual_body < expected_min_body:
                shortfall_lines.append(
                    f"• You produced only {actual_body} body slides but the instructor "
                    f"annotated {expected_min_body} items that each need their own slide "
                    f"(short by {expected_min_body - actual_body}). Walk EVERY page's "
                    f"'annotated_targets_that_need_their_own_slide' list and emit one "
                    f"slide per target. Do NOT sample."
                )
            if actual_passages < expected_passages:
                shortfall_lines.append(
                    f"• You produced only {actual_passages} passage_slides but the source "
                    f"has {expected_passages} passages ({', '.join(passage_ranges)}) — "
                    f"short by {expected_passages - actual_passages}. Emit ONE "
                    f"passage_slide for EVERY passage range, plus its per-blank question "
                    f"slides. Do NOT drop or merge any passage."
                )
            current_prompt = full_prompt + "\n".join(shortfall_lines) + "\n"
            print(f"    Retry {attempt - 1}: body={actual_body}/{expected_min_body}, "
                  f"passages={actual_passages}/{expected_passages}. Re-planning...")

        response = client.models.generate_content(
            model=PLANNING_MODEL,
            contents=current_prompt,
            config=config
        )
        record_usage("planning", response.usage_metadata)

        try:
            plan = response.parsed
        except Exception as e:
            raise ValueError(f"Planner agent failed: {e}")

        actual_body = sum(
            1 for s in plan.slides
            if s.template.value in {
                "theory_slide", "mcq_slide", "mcq_grid_slide", "question_only",
                "pyq_slide", "pyq_grid_slide", "pyq_question_only",
            }
        )
        actual_passages = _count_plan_passages(plan)

        body_ok = expected_min_body == 0 or actual_body >= expected_min_body
        passages_ok = actual_passages >= expected_passages
        if body_ok and passages_ok:
            break

    print(f"  Slide plan created — {plan.total_slides} slides "
          f"(body={actual_body}/≥{expected_min_body} annotated, "
          f"passages={actual_passages}/{expected_passages})")
    if expected_min_body > 0 and actual_body < expected_min_body:
        print(f"  ⚠️  WARNING: planner still short by {expected_min_body - actual_body} "
              f"body slides after {MAX_PLAN_RETRIES} retries")
    if actual_passages < expected_passages:
        print(f"  ⚠️  WARNING: planner still short by {expected_passages - actual_passages} "
              f"passage slides after {MAX_PLAN_RETRIES} retries")
    return plan