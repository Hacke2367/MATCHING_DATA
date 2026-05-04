# Project Blueprint: Pro-Match Identity Engine

## 1. Executive Summary & Philosophy
**Pro-Match Engine** ek high-precision **Entity Resolution (ER)** framework hai. Iska primary objective unstructured, noise-heavy legal snippets aur structured user onboarding data ke beech mathematical aur semantic similarity establish karna hai.

* **Guiding Principle:** *Precision over Recall.* System ka design "False Positives" ko eliminate karne ke liye optimized hai. Ek galat match (False Positive) system failure mana jayega, jabki "No Match Found" ek valid successful exit hai.
* **Hybrid Methodology:** Computationally cheap heuristic filtering (Python/Regex) aur computationally expensive semantic reasoning (LLM) ka **80/20 split**.

---

## 2. Technical Architecture (The Pipeline)

### Phase I: Symmetric Data Normalization
* Source A (Onboarding) aur Source B (Raw Snippets) ko ek **Common Pydantic Schema** mein map kiya jayega.
* **Normalization Logic:** Har snippet ko LLM-powered extraction se guzar kar "Clean JSON" mein convert kiya jayega.
* **Checkpoint Match:** Dono side ke data points (Name, Age, Locations, IDs) ko $O(1)$ lookup efficiency ke liye key-value pairs mein sanitize kiya jayega.

### Phase II: The Retrieval Layer (Vector DB)
* **Semantic Indexing:** Har candidate profile ki "Semantic Summary" ko embedding mein badal kar Vector DB (e.g., ChromaDB) mein index kiya jayega.
* **Metadata Injection:** Original structured JSON ko embedding ke sath as metadata attach kiya jayega taaki search ke baad logic-based processing turant shuru ho sake.

### Phase III: The Heuristic Scoring Engine
Retrieval ke baad mile top-K candidates par niche diye gaye logic apply honge:
1.  **Deterministic Filtering:** Agar `User_Age` aur `Candidate_Age` mein variance $> \pm3$ years hai, toh record automatically **Hard-Rejected** hoga.
2.  **Fuzzy String Matching:** Names ke liye **Jaro-Winkler** algorithm ka use hoga (prefix sensitivity handle karne ke liye).
3.  **Geo-Spatial Context:** Locations ko sirf string match nahi, balki hierarchical check (e.g., "Neral" $\subset$ "Mumbai Metropolitan Region") se analyze kiya jayega.

### Phase IV: Contextual Reasoning (The LLM Judge)
High-confidence candidates (>70 score) ko Gemini API ke pas bheja jayega final verdict ke liye.
* **Logic:** LLM timeline consistency (e.g., "2015 mein student tha toh 2016 mein Director kaise?") aur career-path logic ko analyze karega.

---

## 3. Failure-Mode Foresight (The Edge Case DNA)

| Scenario | Fallback / Logic |
| :--- | :--- |
| **Missing DOB** | Age filter bypass karke industry aur location history par weightage $1.5x$ shift kar dena. |
| **Common Name** | Name score ko ignore karke Unique IDs (DIN/PAN) aur behavior patterns ko primary match trigger banana. |
| **Location Drift** | User ki "Current City" ko snippet ki "Historical Locations" ke sath cross-verify karna (Sequential validation). |

---

## 4. Resource & Latency Optimization
* **Tiered Processing:** Pehle Regex-based NER (Named Entity Recognition) se IDs aur Dates nikalna. LLM ko sirf tab call karna jab unique IDs missing hon.
* **Batch Extraction:** 150 records ko clean karne ke liye asynchronous batch processing ka use karna taaki latency $< 15$ seconds rahe.

---

## 5. Logical Auditability (The Paper Trail)
Har final output ek `audit_log` ke sath aayega:
* **Scoring Breakdown:** Kis field ne kitne points contribute kiye ($S = \sum w_i m_i$).
* **Decision Reason:** LLM ka direct statement ki "Kyu ye match hai ya kyu ye reject hua."
* **Confidence Interval:** Ek numerical value (0.0 to 1.0) jo final certainty batati hai.

---

## 6. Technical Stack
* **Core:** Python 3.10+
* **Validation:** Pydantic V2
* **Similarity Logic:** RapidFuzz (for Jaro-Winkler), Sentence-Transformers (for local embeddings).
* **Intelligence:** Gemini 2.5 Flash (Optimized for Extraction Speed).
