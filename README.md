# RePlan: Transactional Runtime for Interruptible AI Agents

> **Track 5: Interruptible Real-Time Agents** · Samsung PRISM GenAI Hackathon 2026  
> **Final Submission Tag:** `PRISM_GENAI_HACKATHON_Y2026`

---

## 1. Executive Summary

**RePlan** is a deterministic execution runtime for interruptible, real-time AI agents. While the LLM proposes actions and interprets multimodal intent, a deterministic coordination layer manages state versions, dependency graphs, speculative execution, selective invalidation, and transactional commits. 

When a user interrupts mid-sentence (*"Actually Mumbai, but keep everything else"*), RePlan predictively freezes affected in-flight tasks before the utterance completes, preserves unaffected context (budget, dates, breakfast) with zero wasted compute, releases held reservations via idempotent compensators, and strictly rejects late-arriving stale results at a mathematically proven commit gate.

---

## 2. 5-Minute Quickstart (Zero API Key Required)

RePlan runs 100% deterministically out-of-the-box using recorded response caches and discrete-event simulation, requiring **no API keys** and **no network connectivity**.

### Prerequisites
* Python 3.11+
* Node.js 18+ and npm

### Quickstart Commands

```bash
# 1. Clone the repository
git clone https://github.com/LAKSHYA2517/Replan.git
cd Replan

# 2. Verify repository integrity and banned patterns (CI check)
make check

# 3. Start the Web Execution Console (Role D)
cd web
npm install
npm run dev
```

Open your browser at `http://localhost:5173` to explore the **Dual-Pane Showdown**, **Execution Timeline**, and **3-Column Console**. Click the big red **"⚡ Inject Late Result"** button to watch the runtime defend itself against out-of-order race conditions in real time!

---

## 3. Makefile Targets

| Target | Command | Purpose |
|---|---|---|
| `make check` | `bash -c ...` | Enforces repo constraints (no bare `time.time()`, no threads, no bypass flags). |
| `make test` | `pytest -q` | Runs acceptance tests against the frozen contract schemas. |
| `make demo` | `python -m replan.runtime` | Runs the signature scenario in deterministic replay mode. |
| `make replay` | `python -m replan.replay` | Verifies bit-for-bit SHA-256 chain hash replay equivalence. |
| `make bench` | `python -m bench.run` | Executes factorial benchmark sweeps over chaos levels and latency profiles. |

---

## 4. Architecture Overview

```
USER AUDIO / SPEECH
  ↓
STREAM INPUT → FAST-PATH VAD & HYPOTHESIS (T0 < 50ms, T1 < 150ms)
  ↓
INTENT & PROPOSAL ENGINE (Validated Structured Proposals Only)
  ↓
VERSIONED STATE STORE (Append-Only Immutable State Versions)
  ↓
DEPENDENCY-AWARE PLAN GRAPH (Content-Addressed Fingerprints)
  ↓
SPECULATIVE ASYNC EXECUTOR (Safe Async Tool Dispatches & Freezes)
  ↓
TRANSACTIONAL COMMIT GATE (The Single State Writer)
  ├── COMMIT     → State Version Incremented (v1 → v2)
  ├── STALE      → DISCARDED (Fingerprint Mismatch v1 ≠ v2)
  ├── DUPLICATE  → SUPPRESSED (Already Adjudicated)
  └── INVALID    → REJECTED (Tool Execution Failure)
  ↓
FLIGHT RECORDER (Monotonic SHA-256 Hash Chained Event Ledger)
  ↓
WEB CONSOLE & DUAL-PANE SHOWDOWN
```

---

## 5. What to Look at First (Judge's Guide)

1. **The Commit Gate ([`replan/commit.py`](file:///c:/Users/mehta/OneDrive/Desktop/Replan/replan/commit.py)):** The heart of the project. Under 60 lines of code. Proves why an arriving result is only committed if `dispatch_fp == current_fp`.
2. **The Shared Contract Pack ([`replan/schemas.py`](file:///c:/Users/mehta/OneDrive/Desktop/Replan/replan/schemas.py) & [`web/src/contract.ts`](file:///c:/Users/mehta/OneDrive/Desktop/Replan/web/src/contract.ts)):** Strict Pydantic v2 and TypeScript type definitions frozen at Hour Zero.
3. **The Dual-Pane Console ([`web/src/views/DualPane.tsx`](file:///c:/Users/mehta/OneDrive/Desktop/Replan/web/src/views/DualPane.tsx)):** Live side-by-side comparison proving conventional agents suffer state corruption (`WRONG ACTIONS: 1`) while RePlan guarantees `WRONG ACTIONS: 0`.
4. **The Acceptance Test Suite ([`tests/test_acceptance.py`](file:///c:/Users/mehta/OneDrive/Desktop/Replan/tests/)):** 20 independent contract-driven acceptance tests.
5. **The 5-Minute Video Storyboard ([`docs/DEMO_SCRIPT.md`](file:///c:/Users/mehta/OneDrive/Desktop/Replan/docs/DEMO_SCRIPT.md)):** Word-for-word timed demonstration narrative.