"""Layer 2 — Heuristic Scoring Engine.

Stateless and purely functional. Accepts two CandidateIdentity objects,
returns a fully-populated MatchCard. No LLM calls in Tier 0 or Tier 1.
Tier 2 delegates to engine.reasoning when triggered.
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime, timezone

import jellyfish

from config.schema import (
    BatchScoreResult,
    CandidateIdentity,
    ComparisonRow,
    MatchCard,
)
from engine import reasoning

SCORING_VERSION = "1.0.0"

_TIER_0_IDS = frozenset({"PAN", "AADHAR", "PASSPORT", "SSN"})
_WEIGHTS = {"id": 0.60, "name": 0.20, "location": 0.10, "age": 0.10}
_TITLES = frozenset({"mr", "ms", "mrs", "dr", "shri", "smt"})


# ── Normalization ──────────────────────────────────────────────────────────────

def _norm_id(value: str) -> str:
    return value.upper().replace(" ", "").replace("-", "")


def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
    tokens = s.split()
    if tokens and tokens[0].rstrip(".") in _TITLES:
        tokens = tokens[1:]
    return " ".join(tokens)


# ── Age helpers ────────────────────────────────────────────────────────────────

def _anchor_age(anchor: CandidateIdentity) -> int | None:
    if anchor.dob_exact is None:
        return None
    today = date.today()
    age = today.year - anchor.dob_exact.year
    if (today.month, today.day) < (anchor.dob_exact.month, anchor.dob_exact.day):
        age -= 1
    return age


def _candidate_age(cand: CandidateIdentity) -> int | None:
    if cand.projected_current_age is not None:
        return cand.projected_current_age
    if cand.age_at_event is not None and cand.reference_date is not None:
        return (date.today().year - cand.reference_date.year) + cand.age_at_event
    return None


# ── Field scorers ──────────────────────────────────────────────────────────────

def _score_name(anchor: CandidateIdentity, cand: CandidateIdentity) -> tuple[float, str]:
    """Return (points_earned, match_status). First-match-wins, top to bottom."""
    a_names = [_norm_name(n) for n in ([anchor.full_name] + list(anchor.aliases)) if n]
    c_names = [_norm_name(n) for n in ([cand.full_name] + list(cand.aliases)) if n]

    best_jw = max(
        jellyfish.jaro_winkler_similarity(a, c)
        for a in a_names for c in c_names
    )

    if best_jw > 0.95:
        return 0.20, "match"

    a_tokens = set(a_names[0].split())
    c_tokens = set(c_names[0].split())
    if len(a_tokens) >= 2 and a_tokens == c_tokens:
        return 0.15, "partial"

    if best_jw > 0.88:
        return 0.10, "partial"

    return 0.0, "mismatch"


def _score_location(anchor: CandidateIdentity, cand: CandidateIdentity) -> tuple[float, str]:
    """Hierarchical subset check: user location ⊆ candidate locations."""
    if not anchor.locations or not cand.locations:
        return 0.0, "missing"

    user_loc = anchor.locations[0]
    best = 0.0
    for c_loc in cand.locations:
        if user_loc.sub_district and user_loc.sub_district.lower() == (c_loc.sub_district or "").lower():
            best = max(best, 0.06)
        if user_loc.city and user_loc.city.lower() == (c_loc.city or "").lower():
            best = max(best, 0.03)
        if user_loc.state and user_loc.state.lower() == (c_loc.state or "").lower():
            best = max(best, 0.01)

    if best >= 0.06:
        return best, "match"
    if best > 0:
        return best, "partial"
    return 0.0, "mismatch"


# ── Comparison rows ────────────────────────────────────────────────────────────

def _build_rows(
    anchor: CandidateIdentity,
    cand: CandidateIdentity,
    name_pts: float,
    name_status: str,
    age_pts: float,
    age_status: str,
    loc_pts: float,
    loc_status: str,
    id_pts: float,
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []

    rows.append(ComparisonRow(
        field_label="Name",
        user_value=anchor.full_name,
        candidate_value=cand.full_name,
        match_status=name_status,  # type: ignore[arg-type]
        contribution_pts=name_pts,
    ))

    a_age = _anchor_age(anchor)
    c_age = _candidate_age(cand)
    a_age_str = str(anchor.dob_exact) if anchor.dob_exact else (f"~{a_age} yrs" if a_age else None)
    c_age_str = str(cand.dob_exact) if cand.dob_exact else (f"~{c_age} yrs" if c_age else None)
    rows.append(ComparisonRow(
        field_label="DOB / Projected Age",
        user_value=a_age_str,
        candidate_value=c_age_str,
        match_status=age_status,  # type: ignore[arg-type]
        contribution_pts=age_pts if age_status != "missing" else None,
    ))

    if anchor.gender == cand.gender and anchor.gender != "unknown":
        g_status = "match"
    elif anchor.gender == "unknown" or cand.gender == "unknown":
        g_status = "missing"
    else:
        g_status = "mismatch"
    rows.append(ComparisonRow(
        field_label="Gender",
        user_value=anchor.gender,
        candidate_value=cand.gender,
        match_status=g_status,  # type: ignore[arg-type]
        contribution_pts=None,
    ))

    a_loc = anchor.locations[0].raw if anchor.locations else None
    c_loc = cand.locations[0].raw if cand.locations else None
    rows.append(ComparisonRow(
        field_label="Location",
        user_value=a_loc,
        candidate_value=c_loc,
        match_status=loc_status,  # type: ignore[arg-type]
        contribution_pts=loc_pts if loc_status != "missing" else None,
    ))

    rows.append(ComparisonRow(
        field_label="Profession",
        user_value=anchor.profession_raw,
        candidate_value=cand.profession_raw,
        match_status="missing" if not (anchor.profession_raw and cand.profession_raw) else "match",  # type: ignore[arg-type]
        contribution_pts=None,
    ))

    for k in sorted(set(anchor.identifiers) | set(cand.identifiers)):
        a_val = _norm_id(anchor.identifiers[k]) if k in anchor.identifiers else None
        c_val = _norm_id(cand.identifiers[k]) if k in cand.identifiers else None
        if a_val and c_val:
            id_row_status = "match" if a_val == c_val else "mismatch"
        else:
            id_row_status = "missing"
        rows.append(ComparisonRow(
            field_label=f"ID: {k}",
            user_value=a_val,
            candidate_value=c_val,
            match_status=id_row_status,  # type: ignore[arg-type]
            contribution_pts=id_pts if id_row_status == "match" else 0.0,
        ))

    return rows


# ── Public API ─────────────────────────────────────────────────────────────────

def score(anchor: CandidateIdentity, candidate: CandidateIdentity) -> MatchCard:
    """Score anchor vs candidate. Returns a fully populated MatchCard.

    Executes Tier 0 → Tier 1 → (conditionally) Tier 2.
    Inputs are never mutated.
    """
    penalties: list[str] = []
    hard_reject = False

    # ── Tier 0: Instant Match ─────────────────────────────────────────────────
    for k in _TIER_0_IDS:
        if k in anchor.identifiers and k in candidate.identifiers:
            if _norm_id(anchor.identifiers[k]) == _norm_id(candidate.identifiers[k]):
                t0_name_pts, t0_name_status = _score_name(anchor, candidate)
                t0_loc_pts, t0_loc_status = _score_location(anchor, candidate)
                t0_a_age, t0_c_age = _anchor_age(anchor), _candidate_age(candidate)
                t0_age_pts, t0_age_status = 0.0, "missing"
                if t0_a_age is not None and t0_c_age is not None:
                    gap = abs(t0_a_age - t0_c_age)
                    if gap <= 2:
                        t0_age_pts, t0_age_status = 0.10, "match"
                    elif gap <= 5:
                        t0_age_pts, t0_age_status = 0.05, "partial"
                    else:
                        t0_age_status = "mismatch"

                rows = _build_rows(
                    anchor, candidate,
                    t0_name_pts, t0_name_status,
                    t0_age_pts, t0_age_status,
                    t0_loc_pts, t0_loc_status,
                    0.60,
                )
                return MatchCard(
                    candidate_id=candidate.record_id,
                    candidate_summary=candidate,
                    verdict_color="GREEN",
                    verdict_label="Confirmed Match",
                    final_confidence=1.0,
                    tier_reached="tier_0_id_match",
                    comparison_rows=rows,
                    score_breakdown={"id": 0.60, "name": t0_name_pts, "age": t0_age_pts, "location": t0_loc_pts},
                    weights_used=dict(_WEIGHTS),
                    denominator=1.0,
                    penalties_applied=[],
                    identity_summary=candidate.identity_summary,
                    llm_verdict=None,
                    risk_types=list(candidate.risk_types),
                    source_provenance=list(candidate.source_provenance),
                    flags=list(candidate.flags),
                )

    # ── Tier 1: Heuristics ────────────────────────────────────────────────────

    # Gender gate
    if anchor.gender != "unknown" and candidate.gender != "unknown":
        if anchor.gender != candidate.gender:
            hard_reject = True
            penalties.append("GENDER_MISMATCH")

    # Name (always scoreable — full_name is required)
    name_pts, name_status = _score_name(anchor, candidate)
    earned: dict[str, float] = {"name": name_pts}
    denom: dict[str, float] = {"name": _WEIGHTS["name"]}

    # Identifiers (non-Tier-0 types only)
    id_pts = 0.0
    id_scoreable = False
    for k in set(anchor.identifiers) | set(candidate.identifiers):
        if k in _TIER_0_IDS:
            continue
        if k in anchor.identifiers and k in candidate.identifiers:
            id_scoreable = True
            if _norm_id(anchor.identifiers[k]) == _norm_id(candidate.identifiers[k]):
                id_pts = _WEIGHTS["id"]
                break
    if id_scoreable:
        earned["id"] = id_pts
        denom["id"] = _WEIGHTS["id"]

    # Location (only in denominator when at least one side has locations)
    loc_pts, loc_status = _score_location(anchor, candidate)
    if anchor.locations or candidate.locations:
        earned["location"] = loc_pts
        denom["location"] = _WEIGHTS["location"]

    # Age (only in denominator when both sides can produce a comparable age)
    a_age = _anchor_age(anchor)
    c_age = _candidate_age(candidate)
    age_pts = 0.0
    age_status = "missing"
    if a_age is not None and c_age is not None:
        gap = abs(a_age - c_age)
        denom["age"] = _WEIGHTS["age"]
        if gap <= 2:
            age_pts, age_status = 0.10, "match"
        elif gap <= 5:
            age_pts, age_status = 0.05, "partial"
        else:
            age_status = "mismatch"
            hard_reject = True
            if gap > 8:
                age_pts = -0.20
                penalties.append("TEMPORAL_AGE_CONFLICT")
        earned["age"] = age_pts

    # Null-tolerant raw score: sum(earned) / sum(denom)
    denominator = sum(denom.values()) or 1.0
    raw_score = sum(earned.values()) / denominator

    # Conflict penalties (post-normalization, pre-floor)
    if "CONSENSUS_CONFLICT" in candidate.flags:
        raw_score -= 0.15
        penalties.append("CONSENSUS_CONFLICT")
    if "NAME_AMBIGUOUS_IN_TEXT" in candidate.flags:
        raw_score -= 0.10
        penalties.append("NAME_AMBIGUOUS_IN_TEXT")

    # Verdict
    if hard_reject:
        final_confidence = 0.0
        tier: str = "tier_1_hard_reject"
        verdict_color: str = "RED"
        verdict_label: str = "No Match"
    else:
        final_confidence = max(0.0, raw_score)
        tier = "tier_1_heuristic"
        if final_confidence >= 0.90:
            verdict_color, verdict_label = "GREEN", "Confirmed Match"
        elif final_confidence >= 0.50:
            verdict_color, verdict_label = "AMBER", "Review Required"
        else:
            verdict_color, verdict_label = "RED", "No Match"

    rows = _build_rows(
        anchor, candidate,
        earned.get("name", 0.0), name_status,
        earned.get("age", 0.0), age_status,
        earned.get("location", 0.0), loc_status,
        earned.get("id", 0.0),
    )

    card = MatchCard(
        candidate_id=candidate.record_id,
        candidate_summary=candidate,
        verdict_color=verdict_color,  # type: ignore[arg-type]
        verdict_label=verdict_label,
        final_confidence=final_confidence,
        tier_reached=tier,  # type: ignore[arg-type]
        comparison_rows=rows,
        score_breakdown={k: earned.get(k, 0.0) for k in _WEIGHTS},
        weights_used=denom,
        denominator=denominator,
        penalties_applied=penalties,
        identity_summary=candidate.identity_summary,
        llm_verdict=None,
        risk_types=list(candidate.risk_types),
        source_provenance=list(candidate.source_provenance),
        flags=list(candidate.flags),
    )

    # ── Tier 2: LLM Handoff ───────────────────────────────────────────────────
    if not hard_reject and (0.50 <= final_confidence <= 0.89 or "CONSENSUS_CONFLICT" in candidate.flags):
        updated = reasoning.evaluate(card)
        if updated is not None:
            card = updated
        card.tier_reached = "tier_2_llm_judge"

    return card


def batch_score(anchor: CandidateIdentity, candidates: list[CandidateIdentity]) -> BatchScoreResult:
    """Score all candidates against anchor. Returns BatchScoreResult sorted desc by final_confidence."""
    started = datetime.now(timezone.utc).isoformat()

    results: list[MatchCard] = [score(anchor, c) for c in candidates]

    results.sort(
        key=lambda m: (
            m.final_confidence,
            m.candidate_summary.extraction_confidence or 0.0,
            len(m.candidate_summary.supporting_snippets),
        ),
        reverse=True,
    )

    non_rejects = [m for m in results if m.tier_reached != "tier_1_hard_reject"]

    return BatchScoreResult(
        user=anchor,
        best_match=non_rejects[0] if non_rejects else None,
        all_results=results,
        run_metadata={
            "engine_version": SCORING_VERSION,
            "run_started_utc": started,
            "run_finished_utc": datetime.now(timezone.utc).isoformat(),
            "candidate_count": str(len(candidates)),
        },
    )
