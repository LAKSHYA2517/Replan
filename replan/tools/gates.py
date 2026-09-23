"""Checks required before an irreversible room confirmation."""


def may_confirm(task, store, user_confirmed: bool) -> tuple[bool, str]:
    if store.current.policy.get("booking_enabled") is not True:
        return False, "booking is disabled"
    if user_confirmed is not True:
        return False, "explicit user confirmation is required"

    from replan.depgraph import fingerprint

    if fingerprint(task, store.current) != task.dispatch_fp:
        return False, "reservation fingerprint is stale"
    return True, "booking enabled, user confirmed, fingerprint current"
