"""
Apply faithfulness verdicts to a list of SlideContent.

Two-step process:
  1. For slides whose fix_action == "strip_bullets":
        deterministically remove the bullets flagged
        unsupported / contradicts (no LLM call needed).
  2. For slides whose fix_action == "rewrite":
        return a dict of {slide_number: fix_hint} so the orchestrator can
        send them through writer.rewrite_slides_with_hints().
"""

from copy import deepcopy
from schemas.slide_content   import SlideContent
from schemas.faithfulness    import FaithfulnessReport


def apply_strips(
    contents: list[SlideContent],
    reports:  list[FaithfulnessReport],
) -> tuple[list[SlideContent], list[str]]:
    """
    Strip unsupported / contradicting bullets in place.

    Returns the new contents list and a human-readable change log
    (one line per slide affected).
    """
    by_num = {r.slide_number: r for r in reports}
    out: list[SlideContent] = []
    log: list[str] = []

    for c in contents:
        r = by_num.get(c.slide_number)
        if r is None or r.fix_action != "strip_bullets":
            out.append(c)
            continue

        drop_idx = {
            v.bullet_index for v in r.bullet_verdicts
            if v.status in ("unsupported", "contradicts")
        }
        if not drop_idx:
            out.append(c)
            continue

        new_bullets = [
            b for i, b in enumerate(c.bullets) if i not in drop_idx
        ]
        new_c = deepcopy(c)
        new_c.bullets = new_bullets
        out.append(new_c)
        log.append(
            f"slide {c.slide_number}: stripped {len(drop_idx)} unsupported "
            f"bullet(s) (kept {len(new_bullets)})"
        )

    return out, log


def collect_rewrite_hints(
    reports: list[FaithfulnessReport],
) -> dict[int, dict]:
    """
    Build the fixes dict that writer.rewrite_slides_with_hints expects.

    The hint is prefaced with a strong anti-hallucination instruction so
    the writer's retry attempt is grounded in source content only.
    """
    fixes: dict[int, dict] = {}
    for r in reports:
        if r.fix_action != "rewrite":
            continue
        hint = (
            "Use ONLY information from the source pages provided in the "
            "AGENT PAYLOAD. Do not introduce new facts, examples, or "
            "details that are not in the source."
        )
        if r.fix_hint:
            hint += " " + r.fix_hint
        fixes[r.slide_number] = {"hint": hint, "new_layout": None}
    return fixes
