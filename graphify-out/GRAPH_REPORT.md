# Graph Report - matching_engine  (2026-05-05)

## Corpus Check
- 19 files · ~14,352 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 148 nodes · 184 edges · 17 communities (14 shown, 3 thin omitted)
- Extraction: 76% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 45 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f85aad9a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]

## God Nodes (most connected - your core abstractions)
1. `extract_user()` - 14 edges
2. `extract_candidate()` - 13 edges
3. `CandidateIdentity` - 11 edges
4. `call_gemini()` - 11 edges
5. `MatchingEngineError` - 7 edges
6. `GeoLocation` - 7 edges
7. `SnippetIdentity` - 7 edges
8. `ExtractionError` - 5 edges
9. `build_extraction_user_message()` - 5 edges
10. `HardRejectError` - 4 edges

## Surprising Connections (you probably didn't know these)
- `extract_user()` --calls--> `GeoLocation`  [INFERRED]
  engine/extraction.py → config/schema.py
- `extract_candidate()` --calls--> `SnippetIdentity`  [INFERRED]
  engine/extraction.py → config/schema.py
- `extract_user()` --calls--> `CandidateIdentity`  [INFERRED]
  engine/extraction.py → config/schema.py
- `_aggregate()` --calls--> `CandidateIdentity`  [INFERRED]
  engine/extraction.py → config/schema.py
- `test_build_extraction_user_message_is_string()` --calls--> `build_extraction_user_message()`  [INFERRED]
  tests/test_prompts.py → engine/prompts.py

## Communities (17 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (31): BaseModel, CandidateIdentity, GeoLocation, Aggregated symmetric form used by the scoring engine.      Both Source A (User K, One instance per media[] article. LLM-extracted from Source B snippet text., SnippetIdentity, Acceptance criteria tests for config/schema.py (Feature Spec 01 v1.1.0).  Tests, SnippetIdentity must parse successfully from test_scenario_1 media article. (+23 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (25): extract_candidate(), extract_user(), Extract and aggregate a candidate's media snippets into CandidateIdentity., Map a KYC JSON file directly to CandidateIdentity without LLM involvement., Acceptance criteria tests for engine/extraction.py (Spec 02c §5 — mock-based)., A LLM response with a future article_date must fail Pydantic validation.     Whe, extract_user must correctly map test_scenario_1 KYC JSON to CandidateIdentity., extract_user must split full_name into name_tokens. (+17 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (21): call_gemini(), ExtractionError, LLM Connectivity Bridge — Gemini 1.5 Flash (google-genai SDK).  Handles connecti, Raised by the LLM service layer on connectivity or de-serialization failures., Call Gemini 1.5 Flash with temperature=0 and JSON output enforcement.      Args:, Exception, Tests for engine/llm_service.py (Spec 02b — mock-based, no live API calls)., call_gemini must return a dict when Gemini returns clean JSON. (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (15): build_extraction_user_message(), LLM Instruction Vault — Extraction Engine Prompts.  All prompt strings are centr, Format the per-call user turn (anchor + single snippet) as a JSON string., Structural tests for engine/prompts.py (Spec 02a — no LLM calls)., Every required SnippetIdentity field name must appear in the prompt text., All 11 canonical identifier key names must appear in the prompt., All 4 SnippetFlag literals must appear in the prompt., Prompt must explicitly forbid computing projected_current_age. (+7 more)

### Community 4 - "Community 4"
Cohesion: 0.23
Nodes (10): ExtractionError, HardRejectError, MatchingEngineError, Raised when the scoring layer encounters an unrecoverable state., Raised when a hard-reject gate fires (gender mismatch, age conflict, etc.)., Base class for all engine errors., Raised when a CandidateIdentity or MatchCard fails Pydantic validation., Raised when LLM extraction of a snippet or user KYC fails. (+2 more)

### Community 5 - "Community 5"
Cohesion: 0.22
Nodes (8): Candidate, MatchResult, no_future_dates(), Symmetric Identity Schema v1.1.0  Canonical Pydantic v2 data contracts for the P, Potential match candidate, Final matching result, User, _utc_today()

### Community 6 - "Community 6"
Cohesion: 0.33
Nodes (5): _aggregate(), extract_data(), Extraction Engine — Asymmetry Bridge (Spec 02c).  Transforms raw Source A (KYC J, Consolidate validated snippets into a single CandidateIdentity., Extract structured data from messy snippets

## Knowledge Gaps
- **61 isolated node(s):** `Base class for all engine errors.`, `Raised when LLM extraction of a snippet or user KYC fails.`, `Raised when the scoring layer encounters an unrecoverable state.`, `Raised when a hard-reject gate fires (gender mismatch, age conflict, etc.).`, `Raised when a CandidateIdentity or MatchCard fails Pydantic validation.` (+56 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `extract_candidate()` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 6`?**
  _High betweenness centrality (0.484) - this node is a cross-community bridge._
- **Why does `call_gemini()` connect `Community 2` to `Community 1`?**
  _High betweenness centrality (0.341) - this node is a cross-community bridge._
- **Why does `build_extraction_user_message()` connect `Community 3` to `Community 1`?**
  _High betweenness centrality (0.191) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `extract_user()` (e.g. with `GeoLocation` and `CandidateIdentity`) actually correct?**
  _`extract_user()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `extract_candidate()` (e.g. with `build_extraction_user_message()` and `call_gemini()`) actually correct?**
  _`extract_candidate()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `CandidateIdentity` (e.g. with `extract_user()` and `_aggregate()`) actually correct?**
  _`CandidateIdentity` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `call_gemini()` (e.g. with `extract_candidate()` and `test_raises_auth_failure_when_no_api_key()`) actually correct?**
  _`call_gemini()` has 8 INFERRED edges - model-reasoned connections that need verification._