# RePlan: Pitch Deck (12-Slide Presentation)
**Track 5: Interruptible Real-Time Agents · Samsung PRISM GenAI Hackathon 2026**

---

## Slide 1: Title & Team Details
* **Project Title:** RePlan — Transactional Runtime for Interruptible AI Agents
* **One-Line Pitch:** RePlan lets an AI agent speculate and work ahead, but only commits results that remain valid after the user changes their mind.
* **Theme Track:** Track 5: Real-Time / Full-Duplex Interruptible Multimodal Agents
* **Submission Tag:** `PRISM_GENAI_HACKATHON_Y2026`

---

## Slide 2: The Problem — The Brittle Real-Time Agent
* **The Promise:** Voice agents must speculate ahead to feel instantaneous (< 200 ms).
* **The Reality:** Real-world conversations are fluid. Users interrupt, change slots, refine constraints, and pivot mid-sentence.
* **The Two Catastrophic Failure Modes:**
  1. **Wasteful Cancellation:** The agent wipes out all partial progress and restarts from scratch, wasting compute and increasing latency.
  2. **Silent State Corruption (Race Conditions):** In-flight background tool calls return late and blindly overwrite the new state (e.g. late Delhi hotel overwrites active Mumbai trip).

---

## Slide 3: Core Thesis & Signature Behavior
* **The RePlan Philosophy:** Do not treat interruptions as errors. Treat agent execution as **speculative, versioned, dependency-aware transactions**.
* **The Core Invariant (I2):** *A tool result may affect the current task only if its dispatch fingerprint equals the task's fingerprint under current state.*
* **Signature Behavior:**  
  `Speculate Early` $\to$ `Trace Dependencies` $\to$ `Predictively Freeze` $\to$ `Selectively Invalidate` $\to$ `Adopt Valid Work` $\to$ `Reject Stale Results`.

---

## Slide 4: Related Work & Positioning
*The "Does Not Address" positioning that sets RePlan apart from existing agent frameworks:*

| Framework / Paradigm | Primary Focus | What It Does Not Address (The RePlan Gap) |
|---|---|---|
| **LangGraph / AutoGen** | Graph-based DAG orchestration | Static execution graphs; lacks real-time interruption handling and in-flight selective invalidation. |
| **OpenAI Realtime API** | Low-latency voice streaming | Interruption simply cancels output; lacks state versioning and allows out-of-order tool writes. |
| **Temporal / Step Functions** | Durable workflow execution | Heavyweight persistent workflows; lacks sub-100ms speculative execution and microsecond blast-radius pruning. |
| **RePlan (Our Approach)** | **Transactional Deterministic Coordinator** | **Solves all: Sub-50ms barge-in, predictive freeze, fingerprint commit gate, zero wrong actions.** |

---

## Slide 5: System Architecture & The 5 Invariants
* **Invariants:**
  1. *Single Writer:* Only `CommitGate` mutates committed state.
  2. *Fingerprint Validity:* Stale results discarded with cryptographic proof.
  3. *Effect Safety:* `IRREVERSIBLE` tools require explicit confirmation (`may_confirm`).
  4. *Total Order:* Gapless monotonic sequence numbers and SHA-256 hash chains.
  5. *Causal Completeness:* Every state version links back to the originating event.

```
[User Speech] -> [FastPath Intent] -> [Versioned Store] -> [Plan DAG] -> [Executor] -> [Commit Gate] -> [Flight Recorder]
```

---

## Slide 6: Differentiators 1 & 2 — Content Fingerprints & Fast Freeze
* **Content-Addressed Dependency Fingerprinting:**
  * Tasks are fingerprinted by *resolved argument values*, not slot names:  
    `fp = SHA256(tool_name | resolved_args)`.
  * Allows instantaneous cross-plan task adoption and memoization without re-running tools.
* **Predictive Pre-Invalidation (Freeze Not Kill):**
  * T1 Fast-Path classifies pivot cues in < 150 ms (*"Actually..."*).
  * Computes dependency blast radius and freezes affected tasks with a **900 ms lead time** before the user finishes speaking.

---

## Slide 7: Differentiators 3 & 4 — The Stale Firewall & Two-Phase Safety
* **The Stale-Result Firewall:**
  * When an obsolete tool result arrives, the commit gate executes pure adjudication:  
    `result.dispatch_fp != current_fp` $\to$ **`STALE`** (Discarded).
  * State remains 100% byte-identical before and after.
* **Two-Phase Commit & Idempotent Compensation:**
  * Speculative hotel holds use `reserve_room` (`REVERSIBLE`) with an automatic `release_room` compensator.
  * When a user pivots to Mumbai, RePlan automatically fires compensators—zero dangling reservations.

---

## Slide 8: The Signature Demonstrations
1. **Travel & Hospitality Scenario:**
   * User: *"Find a hotel in Delhi under ₹5,000 with breakfast."*
   * Interruption: *"Actually Mumbai, but keep everything else."*
   * Result: Delhi searches frozen; budget/dates/breakfast preserved; late Delhi result rejected; Mumbai plan completed with 40% work reuse.
2. **Samsung Smart Home Scenario:**
   * User: *"Set bedroom AC to 18 and start washer."*
   * Interruption: *"No, living room, and make it 24."*
   * Conventional agent leaves empty bedroom freezing at 18°C. RePlan blocks late bedroom command.

---

## Slide 9: Dual-Pane Head-to-Head Showdown (Beat 5)
*Side-by-side execution driven by a single event stream:*

```
┌────────────────────────────────────────┬────────────────────────────────────────┐
│   CONVENTIONAL AGENT (NAIVE LOOP)      │        REPLAN RUNTIME ENGINE           │
├────────────────────────────────────────┼────────────────────────────────────────┤
│ • Locality: DELPHI (Corrupted!)        │ • Locality: MUMBAI (Preserved)         │
│ • Recommendation: Imperial Delhi       │ • Recommendation: Sea Princess Juhu    │
│ • State: ⚠ OVERWRITTEN BY STALE RESULT │ • State: ✓ PROTECTED BY COMMIT GATE    │
│                                        │                                        │
│         WRONG ACTIONS: 1               │            WRONG ACTIONS: 0            │
└────────────────────────────────────────┴────────────────────────────────────────┘
```
*Both panes update within the same frame; counters visibly diverge on camera.*

---

## Slide 10: Empirical Results & Benchmark Evidence
*Factorial evaluation sweep across 4 scenarios, 6 interrupt offsets, 5 latency profiles, 3 chaos levels, and 8 seeds (from `bench/results.jsonl`):*

| Metric | Conventional Baseline | Cancel-All Baseline | **RePlan Runtime** |
|---|:---:|:---:|:---:|
| **Stale State Commits** | 100% in late episodes | 0% | **0.0% (Zero)** |
| **Wrong Actions Rate** | High (> 45%) | 0% | **0.0% (Zero)** |
| **Work Reuse Ratio** | 0.0% (No reuse) | 0.0% (Discards all) | **38% – 100% (Staircase)** |
| **Wasted Tool Seconds** | 14.2 s / session | 8.6 s / session | **1.8 s / session (-79%)** |
| **Deterministic Replay Fidelity** | N/A (Unreproducible) | N/A | **100.0% Bit-for-Bit** |

*Honest Caveat: RePlan does not make individual tools faster; it eliminates waste and prevents state corruption.*

---

## Slide 11: Multimodal Integration & Causal Auditability
* **Multimodal Blast Radius:**
  * User uploads a competitor hotel flyer image $\to$ Vision tool extracts price $\to$ Patches `constraints.budget`.
  * Dependency graph selectively invalidates `search_hotels` (reads budget) while preserving `availability` (reads dates only).
* **Auditable "Why Did You Pick This?" (Invariant I5):**
  * Reads the backward chain of the Flight Recorder event log:  
    *"Because you said Juhu at v7, under ₹5,000 at v3, and breakfast at v3. I discarded two Bandra results that arrived after your pivot."*

---

## Slide 12: Summary & Submission Verification
* **Core Novelties Delivered:**
  1. Speculative async execution with content-addressed fingerprints.
  2. Predictive freeze with sub-150ms lead time.
  3. Mathematical commit gate rejecting stale out-of-order results.
  4. Immutable state versioning and gapless cryptographic Flight Recorder.
  5. Live Dual-Pane console demonstrating zero wrong actions.
* **Code Repository:** All artifacts, tests, schemas, and UI committed under git tag:  
  `PRISM_GENAI_HACKATHON_Y2026`
