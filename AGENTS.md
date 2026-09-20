# RePlan — rules for AI coding agents

This repository implements a deterministic runtime for interruptible AI agents. Its
correctness properties depend on constraints that are unusual. Read all of this
before writing code.

## Frozen files — never modify

`replan/schemas.py` · `replan/tools/registry.py` · `web/src/contract.ts` · `AGENTS.md` · `Makefile` ·
`.github/**`

If you need a type that is not in `schemas.py`, stop and say so. Do not define it locally.
Do not define a similar one. Do not work around its absence.

## Banned patterns — CI rejects these

- `time.time()`, `time.monotonic()`, `datetime.now()` anywhere under `replan/` — use the injected clock.
- `asyncio.sleep(` anywhere except inside `replan/clock.py` — use `clock.sleep()`.
- `random.` at module level, or any unseeded RNG — use the injected `random.Random`.
- `threading`, `multiprocessing`, or `concurrent.futures` anywhere in the core.
- Any network call inside `replan/tools/` other than in `vision.py` live mode.
- Any write to `StateStore` from outside `replan/commit.py`.
- Any `force=` or `override=` parameter on the commit gate.

## Architectural invariants

1. **Single writer.** Only `CommitGate` mutates committed state.
2. **Fingerprint validity.** A result commits only if its dispatch fingerprint equals the
   task's fingerprint under current state. No exceptions.
3. **Effect safety.** `IRREVERSIBLE` tools are never dispatched speculatively.
4. **Total order.** Every event carries a monotonic gapless sequence number. Never
   order by wall clock.
5. **Causal completeness.** Every committed state version names the event and
   result that produced it.

## Conventions

- State references in a task's `arg_spec` use the dict form `{"$ref": "slots.city"}`. Never
  a custom class.
- Async only. One event loop. No threads in the core.
- Tools return results; tools never decide validity.
- LLM output produces `Proposal` objects; it never becomes a state change directly.
- Re-raise `asyncio.CancelledError` before any general exception handler.

## Scope discipline

Implement exactly what the brief asks. Do not add retry logic, caching, fallbacks,
logging frameworks, or configuration systems that were not requested. Do not
refactor files you were not asked to change. Do not write tests unless the brief
explicitly asks for them — tests are written independently by a different team
member.

If the brief seems to be missing something necessary, say so rather than inventing
it.

## File ownership

| Path | Owner |
|---|---|
| `replan/schemas.py`, `replan/tools/registry.py`, `web/src/contract.ts`, `AGENTS.md`, `Makefile`, CI | FROZEN |
| `replan/clock.py`, `hashing.py`, `state.py`, `depgraph.py`, `reconcile.py`, `commit.py`, `executor.py`, `recorder.py`, `replay.py`, `runtime.py` | A |
| `replan/freeze.py`, `hypothesis.py`, `fastpath.py`, `agents/**` | B |
| `replan/tools/**` (except registry), `replan/policies.py`, `bench/**`, `tests/**` | C |
| `web/**` (except contract.ts) | D |

Two agents never edit one file. `replan/runtime.py` is owned exclusively by A — everyone
else asks A for a wiring line rather than editing it.
