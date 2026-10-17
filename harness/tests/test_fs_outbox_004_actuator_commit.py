"""FS-OUTBOX-004: controlled actuator-side revocation/commit schedules.

A bounded same-process test; no remote provider, distributed consensus or
network acknowledgement is represented.
"""
from threading import Event, Thread
import pytest

from app.engines.reference_authority_actuator import ReferenceAuthorityActuator
from app.engines.authority_store import advance_authority_state_version
from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)
from test_fs_outbox_002_post_commit_dispatch_race import _authorised_outbox_item


def revoke(kind, permit):
    if kind == "global":
        advance_authority_state_version()
    else:
        advance_authority_fence(
            transition_capability=issue_authority_fence_transition_capability_for_test(
                permit.authority_fence_scope_key,
            ),
            authority_fence_scope_key=permit.authority_fence_scope_key,
        )


@pytest.mark.parametrize("kind", ["global", "institutional"])
def test_revocation_effective_before_actuator_commit_refuses(kind):
    permit, h = _authorised_outbox_item()
    actuator = ReferenceAuthorityActuator()
    revoke(kind, permit)
    assert actuator.commit(permit, h).startswith("REFUSED_")
    assert actuator.calls == []


@pytest.mark.parametrize("kind", ["global", "institutional"])
def test_actuator_commit_serialises_with_concurrent_revocation(kind):
    permit, h = _authorised_outbox_item()
    actuator = ReferenceAuthorityActuator()
    started, finished = Event(), Event()
    errors, threads = [], []

    def transition():
        started.set()
        try:
            revoke(kind, permit)
        except BaseException as exc:
            errors.append(repr(exc))
        finally:
            finished.set()

    def hook():
        t = Thread(target=transition, daemon=True)
        threads.append(t)
        t.start()
        assert started.wait(2)
        assert not finished.wait(0.15), "Revocation completed inside actuator guard"

    outcome = actuator.commit(permit, h, before_formation_hook=hook)
    assert len(threads) == 1
    threads[0].join(timeout=3)
    assert not threads[0].is_alive(), "Deadlock in guarded actuator commit"
    assert finished.is_set() and not errors, errors
    assert outcome == "ACTUATOR_CONSEQUENCE_FORMED", outcome
    assert actuator.calls == [h]
    assert actuator.commit(permit, h) != "ACTUATOR_CONSEQUENCE_FORMED"
    assert actuator.calls == [h]


@pytest.mark.parametrize("kind", ["global", "institutional"])
def test_reentrant_revocation_inside_actuator_guard_refuses(kind):
    permit, h = _authorised_outbox_item()
    actuator = ReferenceAuthorityActuator()
    outcome = actuator.commit(
        permit, h, before_formation_hook=lambda: revoke(kind, permit),
    )
    assert outcome.startswith("REFUSED_"), outcome
    assert actuator.calls == []
