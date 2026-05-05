# Schema definitions for data structures

from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    """Actual user profile"""
    id: str
    name: str

@dataclass
class Candidate:
    """Potential match candidate"""
    id: str
    name: str

@dataclass
class MatchResult:
    """Final matching result"""
    user_id: str
    candidate_id: str
    confidence_score: float
    reasoning: str
