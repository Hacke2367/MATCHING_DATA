"""Extraction Engine — Asymmetry Bridge (Spec 02c).

Transforms raw Source A (KYC JSON) and Source B (ComplyAdvantage candidate JSON)
into the canonical CandidateIdentity for the scoring engine.

  Source A → extract_user(file_path)               → CandidateIdentity  (no LLM)
  Source B → extract_candidate(user, file_path, …)  → CandidateIdentity | None

Snippet extraction is parallelised via ThreadPoolExecutor; the concurrency cap
and rate-limit guard in llm_service.py ensure Gemini quota is respected.
"""
import datetime
import json
import logging
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydantic import ValidationError

from config.schema import (
    SCHEMA_VERSION as _SCHEMA_VERSION,
    CANONICAL_IDENTIFIER_KEYS,
    CandidateIdentity,
    GeoLocation,
    SnippetIdentity,
)
from engine.llm_service import ExtractionError, call_gemini
from engine.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_user_message

# Fail-fast on schema version mismatch (Spec 02c §4)
assert _SCHEMA_VERSION == "1.2.0", (
    f"Schema version mismatch: expected 1.2.0, got {_SCHEMA_VERSION}"
)

logger = logging.getLogger(__name__)

_DEFAULT_SNIPPET_N: int = 5
_MAX_WORKERS: int = int(os.getenv("GEMINI_MAX_CONCURRENCY", "8"))

_COUNTRY_CODES: dict[str, str] = {
    "India": "IN",
    "United Kingdom": "GB",
    "United States": "US",
    "Singapore": "SG",
    "Australia": "AU",
    "Canada": "CA",
    "Germany": "DE",
    "France": "FR",
    "United Arab Emirates": "AE",
}

# Pydantic class passed to Gemini as structured output schema (SDK converts natively)
SNIPPET_RESPONSE_SCHEMA = SnippetIdentity


# ─────────────────────────────────────────────────────────────────────────────
# Source A: User KYC JSON → CandidateIdentity (no LLM call)
# ─────────────────────────────────────────────────────────────────────────────

def extract_user(file_path: str) -> CandidateIdentity:
    """Map a KYC JSON file directly to CandidateIdentity without LLM involvement."""
    with open(file_path, encoding="utf-8") as f:
        d = json.load(f)

    # Full name: join non-empty parts, strip titles, lowercase
    name_parts = [
        (d.get(k) or "").strip()
        for k in ("first_name", "middle_name", "last_name")
    ]
    full_name = " ".join(p for p in name_parts if p).lower()

    # Aliases: middle name, previous name, trading as
    aliases = [
        v.strip().lower()
        for v in [d.get("middle_name"), d.get("previous_name"), d.get("trading_as")]
        if v and v.strip()
    ]

    # Gender: normalise to schema literals
    gender_raw = (d.get("sex") or "").strip().lower()
    gender = gender_raw if gender_raw in ("male", "female") else "unknown"

    # DOB
    dob_exact: datetime.date | None = None
    if d.get("date_of_birth"):
        try:
            dob_exact = datetime.date.fromisoformat(str(d["date_of_birth"]))
        except ValueError:
            pass

    # Identifiers: only canonical keys, only non-null values
    id_field_map = {
        "PAN": "pan_number",
        "AADHAR": "aadhar_number",
        "SSN": "ssn_no",
        "VAT": "vat_no",
        "GST": "gst_no",
        "LEI": "legal_entity_number",
        "VOTER_ID": "voter_id_number",
        "DRIVING_LICENSE": "driving_license_number",
    }
    identifiers = {
        key: str(d[field]).strip()
        for key, field in id_field_map.items()
        if d.get(field)
    }

    # Geography
    country_name = (d.get("country_of_residency_name") or "").strip()
    country_code = _COUNTRY_CODES.get(country_name)
    locations: list[GeoLocation] = []
    if d.get("city") or d.get("state") or country_name:
        locations.append(
            GeoLocation(
                city=d.get("city") or None,
                state=d.get("state") or None,
                country=country_name or None,
                country_code=country_code,
                raw=d.get("address") or None,
            )
        )

    # Identity summary (constructed; max 200 chars)
    summary_parts = [p for p in [full_name.title(), d.get("profession"), d.get("city")] if p]
    identity_summary = (", ".join(summary_parts) + ".")[:200]

    return CandidateIdentity(
        source="user",
        record_id=str(d.get("oomero_id") or d.get("entity_id") or ""),
        full_name=full_name,
        aliases=aliases,
        name_tokens=full_name.split(),
        gender=gender,
        dob_exact=dob_exact,
        identifiers=identifiers,
        locations=locations,
        nationality_country=d.get("country_of_nationality_name") or None,
        residency_country=country_name or None,
        profession_raw=d.get("profession") or None,
        identity_summary=identity_summary,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Source B: Candidate JSON → CandidateIdentity (LLM per snippet, parallelised)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_snippet(
    doc_id: str,
    idx: int,
    media: dict,
    anchor_dict: dict,
    canonical_name: str,
    canonical_aka: list[str],
) -> tuple[int, SnippetIdentity | None]:
    """Extract a single media snippet via Gemini. Returns (idx, snippet_or_none)."""
    article_date_raw = media.get("date") or ""
    snippet_input: dict = {
        "candidate_id": doc_id,
        "candidate_canonical_name": canonical_name,
        "candidate_known_aliases": canonical_aka,
        "snippet_text": media.get("snippet", ""),
        "article_date": article_date_raw[:10] if article_date_raw else None,
        "snippet_url": media.get("url") or None,
        "snippet_title": media.get("title") or None,
    }
    user_msg = build_extraction_user_message(anchor_dict, snippet_input)

    try:
        raw = call_gemini(EXTRACTION_SYSTEM_PROMPT, user_msg, SNIPPET_RESPONSE_SCHEMA)
        snippet = SnippetIdentity(**raw)
        logger.info(
            "Candidate %s snippet[%d] validated OK (confidence=%.2f)",
            doc_id, idx, snippet.extraction_confidence,
        )
        return idx, snippet
    except ExtractionError as exc:
        logger.warning(
            "Candidate %s snippet[%d] — LLM error [%s]: %s", doc_id, idx, exc.code, exc
        )
        return idx, None
    except ValidationError as exc:
        logger.error(
            "Candidate %s snippet[%d] — Pydantic validation failed (%d error(s)):\n%s",
            doc_id, idx, exc.error_count(), exc
        )
        return idx, None


def extract_candidate(
    user: CandidateIdentity,
    file_path: str,
    snippet_indices: list[int] | None = None,
) -> CandidateIdentity | None:
    """Extract and aggregate a candidate's media snippets into CandidateIdentity.

    Args:
        user: Source A CandidateIdentity — used as LLM anchor.
        file_path: Path to the ComplyAdvantage candidate JSON.
        snippet_indices: Specific media[] indices to send to the LLM.
                         Defaults to first N=5. Out-of-bounds indices are silently dropped.

    Returns:
        Aggregated CandidateIdentity if ≥1 snippet passes validation, else None.
    """
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    doc = data["doc"]
    # Guard against null media field (some candidates have "media": null)
    media_list = doc.get("media") or []

    # Canonical identity from the registry feed — authoritative subject of every snippet.
    # Forwarded to the LLM so it never picks a different person's name out of the article text.
    canonical_name = (doc.get("name") or "").strip()
    canonical_aka = [
        (a.get("name") or "").strip()
        for a in (doc.get("aka") or [])
        if isinstance(a, dict) and a.get("name")
    ]

    # Bounds-checked index selection — snippet_indices filters LLM INPUT (Spec 02c §4)
    if snippet_indices is None:
        indices = list(range(min(_DEFAULT_SNIPPET_N, len(media_list))))
    else:
        indices = [i for i in snippet_indices if 0 <= i < len(media_list)]

    # Build anchor dict from user CandidateIdentity
    anchor_dict: dict = {
        "full_name": user.full_name,
        "dob_exact": user.dob_exact.isoformat() if user.dob_exact else None,
        "gender": user.gender,
        "identifiers": user.identifiers,
        "locations": [loc.model_dump(exclude_none=True) for loc in user.locations],
    }

    # Parallel per-snippet LLM extraction
    valid_snippets: list[SnippetIdentity] = []
    if not indices:
        logger.error("No valid snippet indices for candidate %s — returning None", doc["id"])
        return None

    n_workers = min(len(indices), _MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(
                _extract_snippet, doc["id"], idx, media_list[idx], anchor_dict,
                canonical_name, canonical_aka,
            ): idx
            for idx in indices
        }
        results: dict[int, SnippetIdentity | None] = {}
        for future in as_completed(futures):
            idx_result, snippet = future.result()
            results[idx_result] = snippet

    # Reassemble in original index order (preserves snippet sequence for aggregation)
    for idx in indices:
        snippet = results.get(idx)
        if snippet is not None:
            valid_snippets.append(snippet)

    if not valid_snippets:
        logger.error("All snippets discarded for candidate %s — returning None", doc["id"])
        return None

    return _aggregate(doc, valid_snippets)


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation: List[SnippetIdentity] → CandidateIdentity
# Per scoring_logic.md §6 aggregation rules
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate(doc: dict, snippets: list[SnippetIdentity]) -> CandidateIdentity:
    """Consolidate validated snippets into a single CandidateIdentity."""
    flags: list[str] = []

    # Canonical snippet for name/profession: highest extraction_confidence
    best = max(snippets, key=lambda s: s.extraction_confidence)

    # 1. Names
    full_name = best.full_name.lower()
    alias_set: set[str] = set()
    for s in snippets:
        alias_set.update(a.lower() for a in s.aliases)

    # 2. Locations — set-union, deduplicated by (city, country) key
    seen_loc_keys: set[tuple] = set()
    locations: list[GeoLocation] = []
    for s in snippets:
        for loc in s.locations:
            key = (loc.city, loc.country)
            if key not in seen_loc_keys:
                seen_loc_keys.add(key)
                locations.append(loc)

    countries = {loc.country for loc in locations if loc.country}
    if len(countries) > 2:
        flags.append("MULTI_COUNTRY_CANDIDATE")

    # 3. Gender — most-frequent non-null consensus
    gender_votes = [s.gender for s in snippets if s.gender != "unknown"]
    if gender_votes:
        counts = Counter(gender_votes)
        top_gender, top_count = counts.most_common(1)[0]
        tied = [v for v in counts.values() if v == top_count]
        gender = "unknown" if len(tied) > 1 else top_gender
        if gender == "unknown" and len(counts) > 1:
            flags.append("CONSENSUS_CONFLICT")
    else:
        gender = "unknown"

    # 4. Identifiers — union; flag same-key conflicting values
    identifiers: dict[str, str] = {}
    for s in snippets:
        for k, v in s.identifiers_in_text.items():
            if k in CANONICAL_IDENTIFIER_KEYS:
                if k in identifiers and identifiers[k] != v:
                    if "CONSENSUS_CONFLICT" not in flags:
                        flags.append("CONSENSUS_CONFLICT")
                else:
                    identifiers[k] = v

    # 5. Risk context — taken directly from the doc (structured, not LLM-extracted)
    risk_types: list[str] = doc.get("types", [])
    source_provenance: list[str] = doc.get("sources", [])

    # 6. DOB year from doc.fields[] (structured registry data)
    dob_year: int | None = None
    for field in doc.get("fields", []):
        if field.get("tag") == "date_of_birth" and field.get("value"):
            try:
                yr = int(str(field["value"])[:4])
                if 1900 <= yr <= 2030:
                    dob_year = yr
                    if "DOB_YEAR_ONLY" not in flags:
                        flags.append("DOB_YEAR_ONLY")
                    break
            except (ValueError, TypeError):
                pass

    # 7. Temporal: reference_date selection + Python-computed projected_current_age
    ref_snippet: SnippetIdentity | None = None
    snippets_with_event = [s for s in snippets if s.event_date is not None]
    if snippets_with_event:
        ref_snippet = max(snippets_with_event, key=lambda s: s.extraction_confidence)
        reference_date = ref_snippet.event_date
        age_at_event = ref_snippet.age_at_event
    else:
        snippets_with_article = [s for s in snippets if s.article_date is not None]
        if snippets_with_article:
            ref_snippet = max(snippets_with_article, key=lambda s: s.extraction_confidence)
            reference_date = ref_snippet.article_date
            age_at_event = ref_snippet.age_at_event
        else:
            reference_date = None
            age_at_event = None
            if "NO_REF_DATE" not in flags:
                flags.append("NO_REF_DATE")

    projected_current_age: int | None = None
    if reference_date and age_at_event:
        computed = (datetime.date.today().year - reference_date.year) + age_at_event
        if 1 <= computed <= 120:
            projected_current_age = computed
            if "AGE_PROJECTED" not in flags:
                flags.append("AGE_PROJECTED")

    # Multi-snippet age conflict (scoring_logic.md §5)
    projections: list[int] = []
    for s in snippets:
        s_ref = s.event_date or s.article_date
        if s_ref and s.age_at_event:
            p = (datetime.date.today().year - s_ref.year) + s.age_at_event
            if 1 <= p <= 120:
                projections.append(p)
    if len(projections) >= 2 and (max(projections) - min(projections)) > 5:
        if "CONSENSUS_CONFLICT" not in flags:
            flags.append("CONSENSUS_CONFLICT")

    # Latest article_date across snippets
    article_dates = [s.article_date for s in snippets if s.article_date]
    latest_article_date = max(article_dates) if article_dates else None

    # 8. Identity summary
    if len(snippets) == 1:
        identity_summary = snippets[0].identity_summary
    else:
        combined = " | ".join(s.identity_summary for s in snippets)
        identity_summary = combined[:200]

    # 9. Mean extraction confidence
    mean_confidence = sum(s.extraction_confidence for s in snippets) / len(snippets)

    return CandidateIdentity(
        source="candidate",
        record_id=doc["id"],
        full_name=full_name,
        aliases=list(alias_set),
        name_tokens=full_name.split(),
        gender=gender,
        dob_year=dob_year,
        age_at_event=age_at_event,
        article_date=latest_article_date,
        event_date=(ref_snippet.event_date if (ref_snippet and snippets_with_event) else None),
        reference_date=reference_date,
        projected_current_age=projected_current_age,
        locations=locations,
        identifiers=identifiers,
        risk_types=risk_types,
        source_provenance=source_provenance,
        supporting_snippets=list(snippets),
        profession_raw=best.profession_raw,
        identity_summary=identity_summary,
        flags=flags,
        extraction_confidence=mean_confidence,
    )
