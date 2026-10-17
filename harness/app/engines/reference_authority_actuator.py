"""FS-OUTBOX-004: bounded in-process actuator-owned commitment boundary.

This is a deliberately separate reference actuator, not a network/payment API.
The only side effect (append to the in-memory actuator ledger) occurs while
holding the same two authority locks used by reference revocation transitions.
"""
from contextlib import ExitStack

from app.engines.authority_store import authority_state_guard, get_authority_state_version_unlocked
from app.engines.institutional_authority import (
    institutional_authority_commit_guard, get_authority_snapshot,
)


class ReferenceAuthorityActuator:
    def __init__(self):
        self.formed = set()
        self.calls = []

    def commit(self, permit, action_hash, *, before_formation_hook=None):
        # Acquire in canonical order, as the protected reference executor does.
        with authority_state_guard(), institutional_authority_commit_guard():
            if action_hash != permit.action_binding_hash:
                return "REFUSED_ACTION_MISMATCH"
            if permit.authority_state_version != get_authority_state_version_unlocked():
                return "REFUSED_GLOBAL_AUTHORITY_STALE"
            snapshot = get_authority_snapshot(permit.authority_subject_mandate_id)
            if snapshot is None or snapshot.mandate.status != "ACTIVE":
                return "REFUSED_INSTITUTIONAL_AUTHORITY"
            if (snapshot.snapshot_id != permit.authority_snapshot_id
                    or snapshot.authority_fence != permit.authority_fence
                    or snapshot.authority_epoch_id != permit.authority_epoch_id):
                return "REFUSED_INSTITUTIONAL_AUTHORITY"
            if before_formation_hook is not None:
                before_formation_hook()
            # Reentrant test hooks can change state while the same thread owns
            # an RLock; recheck before representing consequence formation.
            if permit.authority_state_version != get_authority_state_version_unlocked():
                return "REFUSED_GLOBAL_AUTHORITY_STALE"
            snapshot = get_authority_snapshot(permit.authority_subject_mandate_id)
            if (snapshot is None or snapshot.mandate.status != "ACTIVE"
                    or snapshot.snapshot_id != permit.authority_snapshot_id
                    or snapshot.authority_fence != permit.authority_fence
                    or snapshot.authority_epoch_id != permit.authority_epoch_id):
                return "REFUSED_INSTITUTIONAL_AUTHORITY"
            if permit.signature in self.formed:
                return "REFUSED_DUPLICATE"
            self.formed.add(permit.signature)
            self.calls.append(action_hash)
            return "ACTUATOR_CONSEQUENCE_FORMED"
