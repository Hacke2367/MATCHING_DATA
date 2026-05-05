
---

# Project Blueprint: Pro-Match Identity Engine

## 1. Executive Summary & Philosophy
Pro-Match Engine is a high-precision **Entity Resolution (ER)** framework[cite: 1].
*   **Core Goal:** Match unstructured "Adverse Media" snippets to structured User KYC data[cite: 1].
*   **Philosophy:** **Precision over Recall.** We prefer missing a match over identifying the wrong person[cite: 1].

---

## 2. Technical Architecture

### Phase I: Symmetric Normalization
Convert both the "Giant User JSON" and the "Messy Web Snippets" into the **Shared Identity Schema**[cite: 1].

### Phase II: Multi-Article Extraction (The Refiner)
Extract metadata from each snippet separately[cite: 1].
*   **Key Task:** Identify the `reference_date` of each article to anchor the age calculation[cite: 1].

### Phase III: The Heuristic Scoring Engine
Calculate scores for each snippet[cite: 1].
*   **Alias Logic:** Check user’s middle/last names against snippet aliases[cite: 1].
*   **Geo-Hierarchy:** Validate if "Jogeshwari" matches "Mumbai" records[cite: 1].

### Phase IV: Entity Consensus (The Judge)
If 5 potential matches are found for "Ankit Dubey," the LLM Judge reviews all 5 `identity_summaries`[cite: 1].
*   **Consensus:** Does the "Software Engineer" profile in the User Data match the "Technology Lead" profile in the Adverse Media?[cite: 1]

---

## 3. Failure-Mode Foresight (Edge Cases)

| Scenario | Logic / Fallback |
| :--- | :--- |
| **Gender Mismatch** | Immediate **Hard-Reject** to prevent cross-gender false positives[cite: 1]. |
| **Old News (2005)** | Project age forward to 2026 using `reference_date`[cite: 1]. |
| **Fragmented Name** | Use **Jaro-Winkler** on aliases array[cite: 1]. |
| **Conflict in Records** | Use the **"Consensus Rule"**: Trust the majority of articles/identifiers[cite: 1]. |

---

## 4. Resource & Latency Optimization
*   **Asynchronous Extraction:** Process all snippets in parallel[cite: 1].
*   **Tiered Scoring:** Use Python for math; call **Gemini** only for high-stakes final reasoning[cite: 1].

---

## 5. Logical Auditability
Every result must be explainable[cite: 1]. The `audit_log` will show exactly how the **Projected Age** and **Gender Match** influenced the final **0.0-1.0 score**[cite: 1].

---

