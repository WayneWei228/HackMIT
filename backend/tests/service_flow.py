"""Shared helpers for tests that drive the service one case at a time.

Time is per case: an owner's reply and a January invoice are actions on a case, not on the close.
"""

from __future__ import annotations

ACTIONS = {
    "DELIVER_REPLY": "deliver-reply",
    "EXPIRE_OUTREACH": "expire-outreach",
    "BRING_IN_INVOICE": "bring-in-invoice",
    "DELIVER_VENDOR_REPLY": "deliver-vendor-reply",
}


def rest(api, obligation_id):
    """Step a case until its agents have nothing more to do."""
    for _ in range(60):
        step = api.post(f"/api/obligations/{obligation_id}/advance")
        assert step.status_code == 200, step.text
        if step.json()["done"]:
            return step.json()
    raise AssertionError(f"{obligation_id} never rested")


def next_action(api, obligation_id):
    return api.get(f"/api/obligations/{obligation_id}").json()["next_time_action"]


def take(api, obligation_id, *, only=None):
    """Take the case's next time action and let its agents finish; None when there is none."""
    action = next_action(api, obligation_id)
    if action is None or (only is not None and action["kind"] not in only):
        return None
    moved = api.post(f"/api/obligations/{obligation_id}/{ACTIONS[action['kind']]}")
    assert moved.status_code == 200, moved.text
    rest(api, obligation_id)
    return action["kind"]


def january(api, obligation_ids=None):
    """Start every case, then let each one's reply and January invoice arrive in turn."""
    assert api.post("/api/close/run").status_code == 200
    ids = obligation_ids or [c["obligation_id"] for c in api.get("/api/close").json()["cases"]]
    for oid in ids:
        while take(api, oid, only={"DELIVER_REPLY", "BRING_IN_INVOICE"}):
            pass
    return api


def cases(api):
    return {c["vendor_name"]: c for c in api.get("/api/close").json()["cases"]}
