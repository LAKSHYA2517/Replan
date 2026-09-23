# RePlan: Honest Limitations & System Boundaries

In accordance with rigorous engineering standards and hackathon guidelines, we explicitly document the boundaries, trade-offs, and failure modes of the RePlan runtime:

---

## 1. Declarative vs. Inferred Dependency Extraction
* **Current Boundary:** RePlan extracts task dependencies declaratively from structured argument specifications (e.g. `{"$ref": "slots.locality"}`).
* **Limitation:** The runtime does not automatically infer implicit or unstated dependencies hidden inside black-box tool execution logic. If a tool internally relies on a state parameter that was not declared in its `arg_spec`, the dependency graph cannot compute its blast radius.

---

## 2. Hypothesis Classifier Out-of-Distribution Calibration
* **Current Boundary:** The fast-path Tier 1 regex hypothesis classifier is calibrated on a curated set of approximately 200 conversational utterances across six interruption classes (`BACKCHANNEL`, `ABORT`, `POLICY`, `CLARIFY`, `PIVOT`, `REFINE`).
* **Limitation:** Confidence scores are tuned specifically for this domain distribution. Out-of-distribution speech patterns, heavy idioms, or ambiguous grammar may yield false freezes or missed freezes. However, RePlan is architecturally biased towards **over-freezing**, because a false freeze costs zero (it safely thaws and commits), whereas a missed freeze only sacrifices the latency lead time without corrupting state.

---

## 3. Stale State vs. Confidently Wrong Tool Data
* **Current Boundary:** The Commit Gate strictly prevents temporal race conditions, stale background writes, out-of-order responses, and uncoordinated mutations.
* **Limitation:** The commit gate protects against **stale state**, but it cannot detect if a third-party tool returned factually incorrect or corrupted data while operating under a valid fingerprint. Semantic data correctness remains the responsibility of the tool implementation.

---

## 4. Recovery Latency Trade-Off
* **Current Boundary:** RePlan optimizes for **correctness, zero wrong actions, and compute reuse**.
* **Limitation:** Recovery latency is not improved in the arbitrary general case where 100% of tasks must be completely re-run. When an interruption completely invalidates all previous work, the new plan must still execute its required tools. RePlan's latency advantage comes from **partial work preservation** (e.g., adopting 40% of in-flight work) and **early predictive freezing**, rather than making individual tool executions faster.
