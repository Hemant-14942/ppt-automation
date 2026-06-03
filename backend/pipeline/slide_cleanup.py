"""
Slide cleanup — drop empty / placeholder slides before generation.

When the planner mints a dedicated slide for an annotated target (e.g. a circled
"Q.32") that the extractor never actually captured, the writer has nothing real
to put on it and may emit placeholder text ("Content missing", "full text not
available", "this question was marked for inclusion …"). Such slides are never
acceptable output.

This deterministic pass removes any BODY/question slide whose real content is
empty or placeholder, then renumbers 1..N. Structural slides (title, section,
summary, thank-you, recap, topics, homework) are never touched, and a slide
that has a genuine title/question is kept even if its body is thin.
"""
import re
from schemas.slide_content import SlideContent
from schemas.slide_plan import TemplateType


# Substrings that mark fabricated "no content" text.
_PLACEHOLDER_SNIPPETS = (
    "content missing", "missing content", "content not found",
    "not available", "was not available", "no content",
    "marked for inclusion", "full text for this question",
    "could not be found", "not found in the source",
    "type option here", "type question here", "type heading here",
)

# Layouts allowed to carry little/no body content — never dropped here.
_STRUCTURAL = {
    TemplateType.title_slide, TemplateType.section_heading,
    TemplateType.summary, TemplateType.thank_you_slide,
    TemplateType.recap_slide, TemplateType.topics_slide,
    TemplateType.homework_slide,
}

# A title that carries no information of its own (e.g. "Question 34", "Q.32").
_GENERIC_TITLE_RE = re.compile(r'^(question|ques|q\.?|slide|passage)\s*\.?\s*\d*\s*$',
                               re.IGNORECASE)


def _is_placeholder(text) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return True
    return any(snip in s for snip in _PLACEHOLDER_SNIPPETS)


def _has_real_content(c: SlideContent) -> bool:
    real_bullets = [
        b for b in (c.bullets or [])
        if b and b.strip() and not _is_placeholder(b)
    ]
    passage = (getattr(c, "passage_text", None) or "").strip()
    has_passage = bool(passage) and not _is_placeholder(passage)
    table = getattr(c, "table_data", None)
    has_table = bool(table and table.headers and table.rows)
    return bool(real_bullets) or has_passage or has_table


def _is_droppable(c: SlideContent) -> bool:
    """A non-structural slide with no real body AND a weak/placeholder title."""
    if c.layout in _STRUCTURAL:
        return False
    if _has_real_content(c):
        return False
    title = (c.title or "").strip()
    title_is_weak = (
        not title
        or _is_placeholder(title)
        or bool(_GENERIC_TITLE_RE.match(title))
    )
    return title_is_weak


def drop_placeholder_slides(
    contents: list[SlideContent],
) -> tuple[list[SlideContent], list[str]]:
    """
    Remove empty/placeholder slides and renumber. Returns (kept, change_log).
    """
    kept: list[SlideContent] = []
    log: list[str] = []
    for c in contents:
        if _is_droppable(c):
            log.append(
                f"slide {c.slide_number} [{c.layout.value}] "
                f"'{(c.title or '').strip()[:40]}' — empty/placeholder, dropped"
            )
        else:
            kept.append(c)
    for i, c in enumerate(kept, start=1):
        c.slide_number = i
    return kept, log


def render_cleanup_report(log: list[str]) -> str:
    if not log:
        return "    No empty/placeholder slides found."
    return (f"    Dropped {len(log)} empty/placeholder slide(s):\n"
            + "\n".join(f"      • {line}" for line in log))
