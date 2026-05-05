# Graph Report - matching_engine  (2026-05-05)

## Corpus Check
- 10 files · ~7,759 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 37 nodes · 31 edges · 14 communities (6 shown, 8 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `916f3cb0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]

## God Nodes (most connected - your core abstractions)
1. `MatchingEngineError` - 7 edges
2. `HardRejectError` - 4 edges
3. `ExtractionError` - 3 edges
4. `ScoringError` - 3 edges
5. `SchemaValidationError` - 3 edges
6. `Settings` - 2 edges
7. `Candidate` - 2 edges
8. `MatchResult` - 2 edges
9. `extract_data()` - 2 edges
10. `get_llm_judgment()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `ExtractionError` --inherits--> `MatchingEngineError`  [EXTRACTED]
  backend/src/exceptions.py → backend/src/exceptions.py  _Bridges community 3 → community 1_
- `ScoringError` --inherits--> `MatchingEngineError`  [EXTRACTED]
  backend/src/exceptions.py → backend/src/exceptions.py  _Bridges community 3 → community 10_
- `HardRejectError` --inherits--> `MatchingEngineError`  [EXTRACTED]
  backend/src/exceptions.py → backend/src/exceptions.py  _Bridges community 3 → community 2_
- `SchemaValidationError` --inherits--> `MatchingEngineError`  [EXTRACTED]
  backend/src/exceptions.py → backend/src/exceptions.py  _Bridges community 3 → community 9_

## Communities (14 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.33
Nodes (5): Candidate, MatchResult, Potential match candidate, Final matching result, User

### Community 3 - "Community 3"
Cohesion: 0.67
Nodes (3): Exception, MatchingEngineError, Base class for all engine errors.

## Knowledge Gaps
- **11 isolated node(s):** `Base class for all engine errors.`, `Raised when LLM extraction of a snippet or user KYC fails.`, `Raised when the scoring layer encounters an unrecoverable state.`, `Raised when a hard-reject gate fires (gender mismatch, age conflict, etc.).`, `Raised when a CandidateIdentity or MatchCard fails Pydantic validation.` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MatchingEngineError` connect `Community 3` to `Community 1`, `Community 10`, `Community 2`, `Community 9`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `HardRejectError` connect `Community 2` to `Community 1`, `Community 3`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `ExtractionError` connect `Community 1` to `Community 3`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **What connects `Base class for all engine errors.`, `Raised when LLM extraction of a snippet or user KYC fails.`, `Raised when the scoring layer encounters an unrecoverable state.` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._