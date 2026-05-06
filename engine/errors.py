"""Shared exception classes for the Pro-Match orchestration layer."""
from __future__ import annotations


class FatalOrchestrationError(Exception):
    """Raised when the orchestrator encounters an unrecoverable pre-flight failure.

    Attributes:
        user_file_path: Path to the anchor KYC file that triggered the failure.
        cause: The original exception, if any.
    """

    def __init__(self, message: str, user_file_path: str, cause: Exception | None = None) -> None:
        self.user_file_path = user_file_path
        self.cause = cause
        super().__init__(message)
