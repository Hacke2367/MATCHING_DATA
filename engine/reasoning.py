# Layer 3: LLM Final Judge & Explanation
# Invoked by scoring.py for Tier-2 cases (score 0.50-0.89 OR CONSENSUS_CONFLICT).
# Returns the updated MatchCard with llm_verdict populated, or None if not yet implemented.

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.schema import MatchCard


def evaluate(card: "MatchCard") -> "MatchCard | None":
    """LLM judge entry point. Receives a Tier-1 MatchCard, returns it with llm_verdict set."""
    return None


def get_llm_judgment(scored_data):
    """Get LLM final judgment and reasoning"""
    pass
