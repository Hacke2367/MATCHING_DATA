"""Layer 3 — LLM Tier-2 Judge & Narrative Storyteller.

Invoked by scoring.py for Amber-band cases (0.50–0.89 confidence) or CONSENSUS_CONFLICT.
Enforces the Precision over Recall principle: Tier-1 hard-rejects are immutable.

Public interface:
    evaluate(card: MatchCard) -> MatchCard
"""
from __future__ import annotations

import logging
import time

from pydantic import ValidationError

from config.schema import MatchCard, ReasoningOutput
from engine.llm_service import ExtractionError, call_gemini
from engine.prompts import REASONING_SYSTEM_PROMPT, build_reasoning_user_message

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2       # initial call + 1 retry
_RETRY_SLEEP_SECS = 2   # seconds between attempts


def _call_llm(user_message: str) -> ReasoningOutput | None:
    """Call Gemini and parse into ReasoningOutput. Returns None if all attempts exhausted."""
    schema = ReasoningOutput.model_json_schema()
    for attempt in range(_MAX_ATTEMPTS):
        try:
            raw = call_gemini(REASONING_SYSTEM_PROMPT, user_message, schema)
            return ReasoningOutput.model_validate(raw)
        except (ExtractionError, ValidationError) as exc:
            logger.warning(
                "Reasoning LLM attempt %d/%d failed [%s]: %s",
                attempt + 1, _MAX_ATTEMPTS,
                getattr(exc, "code", type(exc).__name__),
                exc,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_SLEEP_SECS * (attempt + 1))
    return None


def evaluate(card: MatchCard) -> MatchCard:
    """Tier-2 LLM judge entry point.

    Receives a Tier-1 MatchCard. Applies three execution gates, then calls Gemini
    to adjudicate and generate a narrative. Returns the card with llm_verdict set.

    Gate order:
      1. Hard-Reject Guard  — Tier-1 hard-rejects pass through unmodified.
      2. Confidence Window  — Only 0.50–0.89 or CONSENSUS_CONFLICT cases proceed.
      3. Snippet Floor      — Skips LLM when no supporting snippets exist.
    """
    # Gate 1: Never override a deterministic hard-reject (Precision over Recall)
    if card.tier_reached == "tier_1_hard_reject":
        return card

    # Gate 2: Only process Amber-band confidence or flagged conflicts
    if not (0.50 <= card.final_confidence <= 0.89 or "CONSENSUS_CONFLICT" in card.flags):
        return card

    # Gate 3: Require at least one snippet — no evidence means no LLM call
    if not card.candidate_summary.supporting_snippets:
        card.flags = list(card.flags) + ["REASONING_SKIPPED_NO_SNIPPETS"]
        return card

    # Preserve pre-LLM verdict for audit trail before any mutation (spec §5)
    card.pre_llm_verdict_label = card.verdict_label

    output = _call_llm(build_reasoning_user_message(card))

    if output is None:
        # Resiliency fallback: signal failure without changing the verdict
        card.llm_verdict = "System reasoning unavailable."
        card.flags = list(card.flags) + ["LLM_TIMEOUT"]
        return card

    # Length guard: hard truncate at 297 chars + ellipsis
    narrative = output.reasoning_narrative
    if len(narrative) > 300:
        narrative = narrative[:297] + "..."

    card.llm_verdict = narrative

    if output.adjudication == "MATCH":
        card.verdict_label = "Confirmed Match"
        card.verdict_color = "GREEN"
    else:
        card.verdict_label = "Review Required"
        card.verdict_color = "AMBER"

    # Set tier only after successful validated parse (spec §5)
    card.tier_reached = "tier_2_llm_judge"

    return card
