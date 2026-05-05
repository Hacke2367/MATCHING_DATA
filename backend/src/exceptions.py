class MatchingEngineError(Exception):
    """Base class for all engine errors."""


class ExtractionError(MatchingEngineError):
    """Raised when LLM extraction of a snippet or user KYC fails."""


class ScoringError(MatchingEngineError):
    """Raised when the scoring layer encounters an unrecoverable state."""


class HardRejectError(MatchingEngineError):
    """Raised when a hard-reject gate fires (gender mismatch, age conflict, etc.).

    Carry the penalty reason so the caller can populate penalties_applied.
    """

    def __init__(self, reason: str, candidate_id: str = "") -> None:
        self.reason = reason
        self.candidate_id = candidate_id
        super().__init__(f"Hard reject [{candidate_id}]: {reason}")


class SchemaValidationError(MatchingEngineError):
    """Raised when a CandidateIdentity or MatchCard fails Pydantic validation."""
