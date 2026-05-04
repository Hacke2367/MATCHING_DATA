# Scoring Logic: Weighted Identity Resolution Engine

## 1. Scoring Philosophy
The engine calculates a **Confidence Score ($S$)** between 0.0 and 1.0. This score represents the probability that the User (Source A) and the Candidate (Source B) are the same entity. 

*   **Auditability (Checkpoint 5):** Every match must output a detailed breakdown of points awarded per field.
*   **Precision (Checkpoint 1):** We use a 100-point base system before applying penalties.

---

## 2. The Weightage Matrix (Base 100)

Weights are assigned based on the uniqueness and reliability of the data field.

| Field | Weight ($w_i$) | Algorithm / Logic |
| :--- | :--- | :--- |
| **Unique Identifiers (DIN/PAN)** | 60 Points | **Exact Match:** Alphanumeric comparison after normalization. |
| **Full Name** | 20 Points | **Jaro-Winkler Distance:** Similarity score $\times 20$. |
| **Location History** | 10 Points | **Intersection Check:** Is any user city present in the candidate's list? |
| **Age / DOB** | 10 Points | **Variance Check:** Full points for $\pm2$ years; 0 points for $>3$ years. |

---

## 3. Mathematical Formula
The final score is calculated as follows:

$$S = \left( \frac{\sum (Weight_i \cdot Similarity_i)}{\sum Weight_i} \right) - Penalties$$

Where $Similarity_i$ is a value between 0.0 (No Match) and 1.0 (Perfect Match).

---

## 4. Hard Rejection & Penalties (Checkpoint 2)
To eliminate "False Positives," certain contradictions trigger an automatic disqualification (Hard Reject).

*   **Age Mismatch Penalty:** If $|User\_Age - Candidate\_Age| > 5$ years, apply a penalty of **-100 points**. 
*   **Identity Summary Contradiction:** If the `identity_summary` (LLM-generated) describes a profession or life stage impossible for the User (e.g., User is 21, Summary says "Retired in 2010"), trigger **Hard Reject**.
*   **Location Impossibility:** If the User was employed in Mumbai while the Record shows the Candidate was incarcerated in Delhi during the same year.

---

## 5. Tiered Execution & Optimization (Checkpoint 4)

To minimize latency and API costs, the scoring engine runs in three tiers:

1.  **Tier 0 (The Shortcut):** If `identifiers` (DIN/PAN) match 100%, skip all heuristic scoring and mark as **VERIFIED MATCH**.
2.  **Tier 1 (Heuristics):** Run Python-based string and numerical matching (Name, Age, Location).
3.  **Tier 2 (Semantic Final Judge):** If Tier 1 score is between **0.65 and 0.85**, pass the `identity_summary` and `User_Profile` to the LLM for a context-based "Tie-Breaker" reasoning.

---

## 6. Confidence Thresholds & Outputs

| Score Range | Verdict | Action |
| :--- | :--- | :--- |
| **0.90 - 1.00** | **High Confidence** | Auto-Match. Generate final report. |
| **0.70 - 0.89** | **Likely Match** | Send to LLM for final reasoning/explanation. |
| **0.50 - 0.69** | **Possible Match** | Flag for Manual Review. |
| **< 0.50** | **No Match** | Discard candidate. |

---

## 7. Audit Log Requirement (Checkpoint 5)
Every comparison must generate a JSON log for the developer:
```json
{
  "candidate_id": "candidate_1",
  "base_score": 75.5,
  "breakdown": {
    "name_similarity": 0.92,
    "age_variance": 0.0,
    "id_match": false,
    "location_overlap": true
  },
  "penalties": 0,
  "llm_verdict": "Name and location overlap are high. Age is within threshold. Match confirmed.",
  "final_confidence": 0.755
}

---

## Final Checkpoint Compliance Verification:

1.  **Precision:** Uses Jaro-Winkler and a defined 60/20/10/10 weight system.
2.  **Failure-Mode:** Includes a -100 point penalty for age mismatch and summary contradictions.
3.  **Symmetry:** Pulls fields directly from the `data_schema.md` keys.
4.  **Optimization:** Implements Tier 0-2 processing to save API calls.
5.  **Auditability:** Standardizes a JSON log output for every decision.