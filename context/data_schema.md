# Data Schema: Symmetric Identity Model

## 1. Schema Philosophy
This schema acts as the **Translation Layer**. Its purpose is to force the LLM to extract specific, structured metadata from messy snippets so they can be compared against the clean User Object.

---

## 2. Core Identity Fields

| Field Name | Data Type | Constraints | Extraction Logic |
| :--- | :--- | :--- | :--- |
| `full_name` | `String` | Min 2 words; Lowercased | Regex stripping + LLM verification |
| `age` | `Integer` | Range: 18 - 100 | Calculated: $Current\_Year - Birth\_Year$ |
| `locations` | `List[String]` | Standardized City names | Geo-Hierarchy mapping (Sub-district level) |
| `identifiers` | `Dict` | Key: ID Type, Value: Alphanumeric | Regex patterns for DIN, PAN, Passport |
| `industry` | `String` | Sector-specific (e.g., Tech, Finance) | Semantic classification via LLM |
| `identity_summary`| `String` | Max 150 characters | **LLM-Generated:** One-line summary of the record. |

---

## 3. The Extraction Step (LLM Role)
During the **Refinement Phase**, the LLM must process every messy snippet and output a JSON object. 
*   **Cleaning Task:** Remove noise (Court names, legal jargon, irrelevant dates).
*   **Summarization Task:** Create the `identity_summary`. 
    *   *Example:* "Director at X Corp involved in a 2018 financial non-compliance case in Mumbai."
*   **Normalization:** Convert all extracted text to a standard format (e.g., "Sandeep" instead of "Mr. Sandeep").

---

## 4. Normalization Rules (Checkpoint 1)
*   **Names:** Strip whitespace, convert to lowercase, remove honorifics.
*   **Identifiers:** Remove non-alphanumeric characters (e.g., "DIN: 12-34-56" -> "123456").
*   **Locations:** Standardize aliases (e.g., "Neral Station" -> "Neral, Maharashtra").

---

## 5. Failure-Mode Fallbacks (Checkpoint 2)
*   **Missing Age:** If the age cannot be extracted, the LLM must look for a "Timeline Trigger" (e.g., "Graduated in 2020") to estimate a probable age range.
*   **Ambiguous Summary:** If the snippet is too messy for a specific summary, the `identity_summary` should be marked as `[LOW_CONFIDENCE_DATA]` to alert the Scoring Engine.

---

## 6. Symmetric Pipeline (Checkpoint 3)
1.  **Source A (User):** Data is already structured.
2.  **Source B (Snippet):** LLM extracts fields defined in Section 2 + creates the `identity_summary`.
3.  **Validation:** Both objects must now share the exact same JSON keys before moving to `scoring_logic.py`.