"""
Token & cost tracker for one pipeline run.

All Gemini calls across the pipeline (extractor, planner, writer, critics)
call `record_usage()` after every response. The orchestrator calls `summary()`
at the end to print a detailed breakdown to the terminal.

Usage pattern (in any agent — no import of the tracker needed):
    from pipeline.token_tracker import record_usage
    response = client.models.generate_content(...)
    record_usage("writing", response.usage_metadata)

Gemini 2.5 Flash pricing (paid tier, May 2026):
  Input  : $0.30  / 1M tokens
  Output : $2.50  / 1M tokens
  (thinking tokens billed at output rate)
"""

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

# ── Pricing constants (USD per token) ────────────────────────────────────────
_INPUT_COST_PER_TOKEN  = 0.30  / 1_000_000   # $0.30 / 1M
_OUTPUT_COST_PER_TOKEN = 2.50  / 1_000_000   # $2.50 / 1M


@dataclass
class _StageUsage:
    name:            str
    prompt_tokens:   int = 0
    output_tokens:   int = 0
    thinking_tokens: int = 0
    calls:           int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens + self.thinking_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.prompt_tokens   * _INPUT_COST_PER_TOKEN
            + self.output_tokens * _OUTPUT_COST_PER_TOKEN
            + self.thinking_tokens * _OUTPUT_COST_PER_TOKEN  # billed as output
        )


@dataclass
class _Totals:
    prompt_tokens:   int
    output_tokens:   int
    thinking_tokens: int
    calls:           int
    cost_usd:        float


# ── Module-level context variable ────────────────────────────────────────────
# Set by the orchestrator at the start of each pipeline run via `activate()`.
# Any agent in the same async context can call `record_usage()` directly
# without receiving the tracker as a parameter.
_current_tracker: ContextVar[Optional["TokenTracker"]] = ContextVar(
    "_current_tracker", default=None
)


def record_usage(stage: str, usage_metadata) -> None:
    """
    Convenience function — record usage into the active tracker for this run.
    Call this in any agent right after a `generate_content` call.
    No-op if no tracker is active (e.g. during tests).
    """
    tracker = _current_tracker.get()
    if tracker is not None:
        tracker.record(stage, usage_metadata)


class TokenTracker:
    """
    Thread-safe accumulator. One instance per pipeline run.
    Stages: extraction, planning, writing, critics.
    """

    _STAGES = ("extraction", "planning", "writing", "critics")

    def __init__(self):
        self._lock   = threading.Lock()
        self._stages: dict[str, _StageUsage] = {
            s: _StageUsage(name=s) for s in self._STAGES
        }
        self._other  = _StageUsage(name="other")

    def activate(self) -> None:
        """Register this tracker as the active one for the current async context."""
        _current_tracker.set(self)

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, stage: str, usage_metadata) -> None:
        """
        Record token counts from one Gemini response.

        `usage_metadata` is the `response.usage_metadata` object from the
        google-genai SDK. Missing fields default to 0.
        """
        if usage_metadata is None:
            return

        prompt   = getattr(usage_metadata, "prompt_token_count",      0) or 0
        output   = getattr(usage_metadata, "candidates_token_count",  0) or 0
        thinking = getattr(usage_metadata, "thoughts_token_count",    0) or 0

        bucket = self._stages.get(stage, self._other)
        with self._lock:
            bucket.prompt_tokens   += prompt
            bucket.output_tokens   += output
            bucket.thinking_tokens += thinking
            bucket.calls           += 1

    def summary(self, elapsed_seconds: float) -> str:
        """Return a formatted multi-line summary string."""
        with self._lock:
            all_stages = list(self._stages.values())
            if self._other.calls:
                all_stages.append(self._other)

        totals = self._collect_totals(all_stages)

        mins, secs = divmod(int(elapsed_seconds), 60)
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"

        lines = [
            "",
            "╔══════════════════════════════════════════════════════╗",
            "║          Token Usage & Cost Report                   ║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  Total time        : {time_str:<33}║",
            f"║  Total API calls   : {totals.calls:<33}║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  {'Stage':<14}  {'Calls':>5}  {'Input':>8}  {'Output':>8}  {'Think':>7}  {'Cost':>8} ║",
            f"║  {'-'*14}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8} ║",
        ]

        for s in all_stages:
            if s.calls == 0:
                continue
            cost_str = f"${s.cost_usd:.4f}"
            lines.append(
                f"║  {s.name:<14}  {s.calls:>5}  "
                f"{s.prompt_tokens:>8,}  {s.output_tokens:>8,}  "
                f"{s.thinking_tokens:>7,}  {cost_str:>8} ║"
            )

        lines += [
            f"╠══════════════════════════════════════════════════════╣",
            f"║  {'TOTAL':<14}  {totals.calls:>5}  "
            f"{totals.prompt_tokens:>8,}  {totals.output_tokens:>8,}  "
            f"{totals.thinking_tokens:>7,}  ${totals.cost_usd:>7.4f} ║",
            f"║                                                      ║",
            f"║  Input  {totals.prompt_tokens:>10,} × $0.30/1M = ${totals.prompt_tokens  * _INPUT_COST_PER_TOKEN :.4f}{'':>14}║",
            f"║  Output {totals.output_tokens:>10,} × $2.50/1M = ${totals.output_tokens * _OUTPUT_COST_PER_TOKEN:.4f}{'':>14}║",
        ]

        if totals.thinking_tokens:
            lines.append(
                f"║  Think  {totals.thinking_tokens:>10,} × $2.50/1M = ${totals.thinking_tokens * _OUTPUT_COST_PER_TOKEN:.4f}{'':>14}║"
            )

        lines += [
            f"║  ─────────────────────────────────────────────────── ║",
            f"║  TOTAL COST for this PPT  :  ${totals.cost_usd:.4f} USD{'':>17}║",
            f"╚══════════════════════════════════════════════════════╝",
            "",
        ]
        return "\n".join(lines)

    def snapshot(self) -> _Totals:
        """Return a totals snapshot for delta comparisons."""
        with self._lock:
            all_stages = list(self._stages.values())
            if self._other.calls:
                all_stages.append(self._other)
        return self._collect_totals(all_stages)

    def summary_delta(self, before: _Totals, elapsed_seconds: float) -> str:
        """Return a compact summary string for usage since a snapshot."""
        with self._lock:
            all_stages = list(self._stages.values())
            if self._other.calls:
                all_stages.append(self._other)
        after = self._collect_totals(all_stages)

        delta_prompt = max(after.prompt_tokens - before.prompt_tokens, 0)
        delta_output = max(after.output_tokens - before.output_tokens, 0)
        delta_think  = max(after.thinking_tokens - before.thinking_tokens, 0)
        delta_calls  = max(after.calls - before.calls, 0)
        delta_cost   = max(after.cost_usd - before.cost_usd, 0.0)

        mins, secs = divmod(int(elapsed_seconds), 60)
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"

        lines = [
            "",
            "╔══════════════════════════════════════════════════════╗",
            "║      Background LLM Usage (telemetry)                ║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  Total time        : {time_str:<33}║",
            f"║  Total API calls   : {delta_calls:<33}║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  Input  {delta_prompt:>10,} | Output {delta_output:>10,} | Think {delta_think:>8,} ║",
            f"║  Cost  ${delta_cost:>10.4f} USD{'':>20}║",
            "╚══════════════════════════════════════════════════════╝",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _collect_totals(stages: list[_StageUsage]) -> _Totals:
        total_prompt   = sum(s.prompt_tokens   for s in stages)
        total_output   = sum(s.output_tokens   for s in stages)
        total_thinking = sum(s.thinking_tokens for s in stages)
        total_calls    = sum(s.calls           for s in stages)
        total_cost     = sum(s.cost_usd        for s in stages)
        return _Totals(
            prompt_tokens=total_prompt,
            output_tokens=total_output,
            thinking_tokens=total_thinking,
            calls=total_calls,
            cost_usd=total_cost,
        )
