"""Pure dependency resolution over PlanTask/SessionState. Reads only — no
commit-gate or executor imports, no caching. Fingerprints identify a unit of
work by the resolved values it reads, not by the slot names it depends on.
"""

from __future__ import annotations

from typing import Any

from replan.hashing import h
from replan.schemas import ExecutionPlan, PlanTask, SessionState


def _ref_path(value: Any) -> str | None:
    if isinstance(value, dict) and set(value) == {"$ref"}:
        return value["$ref"]
    return None


def resolve(arg_spec: dict[str, Any], state: SessionState) -> dict[str, Any]:
    """Replace every {"$ref": path} with state.read(path); literals pass through."""
    resolved = {}
    for key, value in arg_spec.items():
        ref = _ref_path(value)
        resolved[key] = state.read(ref) if ref is not None else value
    return resolved


def deps(task: PlanTask) -> set[str]:
    return {path for value in task.arg_spec.values() if (path := _ref_path(value))}


def fingerprint(task: PlanTask, state: SessionState) -> str:
    return h(task.tool, resolve(task.arg_spec, state))


def blast_radius(plan: ExecutionPlan, changed_paths: set[str]) -> set[str]:
    """Task ids whose deps() intersect changed_paths. Cheap and
    over-approximate by design — a direct lookup, no re-fingerprinting."""
    return {task_id for task_id, task in plan.tasks.items() if deps(task) & changed_paths}


def transitive_radius(plan: ExecutionPlan, changed_paths: set[str]) -> set[str]:
    """Extend blast_radius along task.after edges to a fixed point: a task
    that runs after an affected task is affected too, since its precondition
    changed. O(n^2) worst case over the plan's tasks.
    # ponytail: fixed-point scan, fine for plan sizes this project uses (<50 tasks);
    # switch to a reverse-adjacency index if plans ever get large.
    """
    radius = blast_radius(plan, changed_paths)
    grew = True
    while grew:
        grew = False
        for task_id, task in plan.tasks.items():
            if task_id not in radius and set(task.after) & radius:
                radius.add(task_id)
                grew = True
    return radius
