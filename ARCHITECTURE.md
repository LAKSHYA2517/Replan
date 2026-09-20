# RePlan Architecture & System Invariants

## The Five Architectural Invariants

Every design decision in RePlan flows from five foundational invariants that guarantee safety and determinism:

| # | Invariant | Description & Enforcement |
|:---:|---|---|
| **I1** | **Single Writer** | Only `CommitGate` is permitted to mutate committed `StateStore` state. Parallel async executors and LLM agents cannot directly alter session state. |
| **I2** | **Fingerprint Validity** | A tool result commits if and only if its dispatch fingerprint matches the task's fingerprint under current state: `result.dispatch_fp == fingerprint(task, store.current)`. No exceptions. |
| **I3** | **Effect Safety** | Tools with `IRREVERSIBLE` effect classes (e.g. `confirm_room`) are never dispatched speculatively and require explicit confirmation (`may_confirm`). |
| **I4** | **Total Order** | Every system event carries a gapless monotonic sequence number and an append-only SHA-256 hash chained to its predecessor. The runtime never orders by wall clock. |
| **I5** | **Causal Completeness** | Every committed state version explicitly references the event and result that produced it, enabling bit-for-bit counterfactual replay and causal explanation ("Why did you pick this?"). |

---

## Component Topology & File Ownership

```
[replan/]
  ├── schemas.py          <- FROZEN: Boundary contracts (Pydantic v2)
  ├── clock.py            <- VirtualClock & discrete-event time injection (Owner: A)
  ├── hashing.py          <- Canonical JSON hashing & truncated SHA-256 (Owner: A)
  ├── state.py            <- Append-only versioned StateStore (Owner: A)
  ├── depgraph.py         <- Blast radius & fingerprint calculation (Owner: A)
  ├── commit.py           <- The Commit Gate (Single writer) (Owner: A)
  ├── executor.py         <- Async executor with freeze, thaw, cancel (Owner: A)
  ├── reconcile.py        <- Selective invalidation & task adoption (Owner: A)
  ├── recorder.py         <- Gapless monotonic hash-chained Flight Recorder (Owner: A)
  ├── replay.py           <- Bit-for-bit deterministic replay engine (Owner: A)
  ├── runtime.py          <- The central orchestrator (Owner: A exclusively)
  ├── server.py           <- Async WebSocket & REST bridge (Owner: D)
  ├── freeze.py           <- FreezeController & lead time tracking (Owner: B)
  ├── fastpath.py         <- T0/T1 latency responders & filler generator (Owner: B)
  ├── hypothesis.py       <- Regex & model intent classifier (Owner: B)
  ├── agents/             <- Audio I/O, Gemini Live, & Local Stack (Owner: B)
  └── tools/              <- Deterministic mocks, reservations, vision (Owner: C)

[web/] (Owner: D)
  ├── src/contract.ts     <- FROZEN: TypeScript types mirroring schemas.py
  ├── src/useEventStream  <- Pure useReducer state projection engine
  ├── src/views/
  │   ├── Timeline.tsx    <- SVG + d3-scale swimlane visualization
  │   ├── Console.tsx     <- 3-column live execution inspector
  │   ├── DualPane.tsx    <- Head-to-head comparison showdown mode
  │   ├── Controls.tsx    <- 6-button control deck + confirm chip
  │   └── Scrubber.tsx    <- Interactive replay slider & chain hash display
  └── src/fixtures/       <- Deterministic signature scenario replay stream
```

---

## The Three-Tier Latency Hierarchy

```
T0: Barge-In Signal Processing (< 50 ms)
  • Immediate audio playback stoppage on voiced frame detection.
  • Signal only; no classification or state changes.

T1: Fast-Path Intent & Freeze (< 150 ms)
  • Microsecond regex classifier identifies backchannels, pivots, or aborts.
  • On pivot cue: Freezes blast radius immediately & emits brief conversational filler.

T2: Full Model Proposal & Reconcile (1 – 2 s)
  • Structured output LLM extracts validated state patch proposals.
  • Reconciler computes task diff, preserves valid in-flight work, and dispatches new tasks.
```
