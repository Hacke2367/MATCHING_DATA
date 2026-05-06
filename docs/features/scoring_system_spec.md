# Feature Spec 03: Scoring Engine (The Comparator)
**Version:** 1.0.0 | **Component:** `engine/scoring.py` | **Status:** FINAL
**Depends On:** `config/schema.py` (v1.0.0), `scoring_logic.md` (v1.0.0)
**Blocks:** `engine/reasoning.py`

## 1. The Objective (The "What")
Symmetric `CandidateIdentity` objects ko compare karke ek mathematical **MatchCard** produce karna. Ye engine Tier 0 (Instant Match) aur Tier 1 (Heuristic Scoring) ka owner hai.

## 2. Architectural Constraints
*   **Stateless Execution:** No global caching.
*   **Immutable Inputs:** Input objects ko mutate nahi karna hai.
*   **Scale:** Sabhi scores **0.0 to 1.0 (float)** ke beech honge.
*   **Normalization Ownership:** Name aur Identifier cleaning ki zimmedari `scoring.py` ki hai.

## 3. Normalization Contract (Pre-Score)
Comparison se pehle har field par ye transformation lagana mandatory hai:
*   **Identifiers:** Uppercase + Whitespace strip (e.g., "pan 123" -> "PAN123").
*   **Names:** Unicode NFKD normalization, lowercase, strip titles (`Mr., Ms., Dr., Shri, Smt.`), strip leading/trailing spaces.

## 4. The Weight Matrix (Aligned with `scoring_logic.md §2`)
Total Confidence ($C$) is calculated out of a **1.0 denominator**.

| Category | Weight | Logic / Rule |
| :--- | :--- | :--- |
| **Identifiers** | **0.60** | Tier 0 match (PAN, AADHAR, SSN, PASSPORT) = **1.0 Total Score**. |
| **Name** | **0.20** | `rapidfuzz.distance.JaroWinkler` similarity. |
| **Location** | **0.10** | Hierarchy: Sub-district (0.06), City (0.03), State (0.01). |
| **Age** | **0.10** | $|Anchor.age - Candidate.age| \le 2$ yrs. |

## 5. Scoring Tiers & Rule Exclusivity
**Rule:** Har Tier ke andar, sirf highest matching rule apply hoga (**First match wins**, top-to-bottom).

### Tier 0: The Instant Match
*   **Trigger:** `Anchor.identifiers[K] == Candidate.identifiers[K]` for $K \in \{PAN, AADHAR, PASSPORT, SSN\}$.
*   **Output:** `final_confidence = 1.0`, `verdict_label = "Confirmed Match"`, `verdict_color = "GREEN"`.

### Tier 1: Heuristic Calculations
1.  **Name (Max 0.20):**
    *   Jaro-Winkler > 0.95 $\rightarrow$ 0.20 pts.
    *   Token Intersection (First + Last) $\rightarrow$ 0.15 pts.
    *   Alias similarity > 0.88 $\rightarrow$ 0.10 pts.
2.  **Temporal (Max 0.10):**
    *   Anchor current age (calculated from `dob_exact` using `date.today()`) vs `Candidate.projected_current_age`.
    *   Gap $\le 2$ yrs $\rightarrow$ 0.10 pts.
    *   Gap $\le 5$ yrs $\rightarrow$ 0.05 pts.
    *   Gap $> 8$ yrs $\rightarrow$ **-0.20 penalty**.

## 6. Penalty & Floor Logic
*   **CONSENSUS_CONFLICT:** Deduct **0.15**.
*   **NAME_AMBIGUOUS_IN_TEXT:** Deduct **0.10**.
*   **Floor:** Final score kabhi bhi **0.0** se niche nahi jayega (`max(0.0, score)`).

## 7. Tier 2: LLM Handoff (The Amber Bridge)
`scoring.py` ko `engine/reasoning.py` call karna HOGA agar:
*   **Condition:** `final_confidence` is between **0.50 and 0.89** OR **CONSENSUS_CONFLICT** flag is True.
*   **Handoff:** `reasoning.evaluate(MatchCard) -> MatchCard` (updates `llm_verdict` and `verdict_label`).

## 8. Data Contract (Output: `MatchCard`)
Ye module `config/schema.py` ke `MatchCard` ko populate karega:
*   `final_confidence`: float (0.0 - 1.0).
*   `verdict_label`: "Confirmed Match" ($\ge 0.90$), "Review Required" ($0.50-0.89$), "No Match" ($< 0.50$).
*   `verdict_color`: "GREEN", "AMBER", "RED".
*   `score_breakdown`: `{"id": 0.6, "name": 0.2, ...}`.

## 9. Acceptance Criteria
1.  **Case Insensitive ID:** "pan123" vs "PAN123" must trigger Tier 0 (1.0 score).
2.  **Amber Trigger:** Name match (0.2) + Location match (0.1) = 0.3. Score is RED, no handoff.
3.  **Conflict Penalty:** Perfect match (1.0) but conflict flag (-0.15) = 0.85. Must trigger **AMBER** handoff.
4.  **Negative Guard:** Low score (0.1) with penalties must return 0.0, not -0.15.

---
