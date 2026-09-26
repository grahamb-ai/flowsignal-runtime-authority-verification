from datetime import timezone
from pathlib import Path

import pytest

from app.engines.authority_resolution import (
    AuthorityResolutionError,
    resolve_payment_authority,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def _request():
    return load_scenario(SCENARIO, rebase_to_now=False)


def test_slice_c_builds_one_coherent_resolution_context():
    req = _request()
    semantics, evidence, graph, scope, context = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    assert semantics.protected_operation_class == "treasury.payment"
    assert context.semantics_set_id == semantics.semantics_set_id
    assert context.derivation_graph_id == graph.graph_id
    assert scope.derivation_graph_id == graph.graph_id
    assert set(context.evidence_member_ids) == {item.evidence_id for item in evidence}
    assert scope.authority_subject_id == req.actor_id
    assert scope.max_amount >= req.amount


def test_request_side_authentication_cannot_manufacture_unknown_actor():
    req = _request()
    req.actor_id = "attacker-controlled-agent"
    req.actor_authenticated = True
    req.kya_status = "VERIFIED"
    with pytest.raises(AuthorityResolutionError, match="unresolved"):
        resolve_payment_authority(req, resolved_at=req.requested_execution_time)


def test_presented_mandate_limit_cannot_expand_authoritative_limit():
    req = _request()
    req.mandate_max_amount = req.amount * 100
    req.amount = req.mandate_max_amount
    with pytest.raises(AuthorityResolutionError, match="amount outside"):
        resolve_payment_authority(req, resolved_at=req.requested_execution_time)


def test_unknown_beneficiary_cannot_self_supply_operational_standing():
    req = _request()
    req.beneficiary = "ATTACKER-SUPPLIER"
    req.counterparty_status = "APPROVED"
    req.account_status = "ACTIVE"
    req.risk_state = "NORMAL"
    with pytest.raises(AuthorityResolutionError, match="unresolved"):
        resolve_payment_authority(req, resolved_at=req.requested_execution_time)


def test_context_identity_changes_when_authority_cut_changes():
    req = _request()
    _, _, _, _, before = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    from app.engines.institutional_authority import (
        advance_authority_fence,
        issue_authority_fence_transition_capability_for_test,
    )
    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        ),
    )
    _, _, _, _, after = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    assert before.context_id != after.context_id
    assert before.authority_cut_id != after.authority_cut_id


def test_known_approved_beneficiary_still_requires_mandate_scope():
    from dataclasses import replace
    from app.engines.authority_evidence_adapters import register_operational_standing_for_test

    req = _request()
    alternate = "SUPPLIER-Y"
    register_operational_standing_for_test(
        alternate,
        counterparty_status="APPROVED",
        account_status="ACTIVE",
        risk_state="NORMAL",
        source_version="1",
    )
    req = replace(req, beneficiary=alternate)

    with pytest.raises(AuthorityResolutionError, match="beneficiary|mandate|scope|authoritative"):
        resolve_payment_authority(req, resolved_at=req.requested_execution_time)


def test_authorised_beneficiary_cannot_substitute_unapproved_account_reference():
    """MV-003 / NORM-PAY-001: beneficiary identity does not authorise any account."""
    from dataclasses import replace

    req = _request()
    assert req.beneficiary == "SUPPLIER-X"
    req = replace(
        req,
        beneficiary_account_reference="ACCT-SUPPLIER-X-ATTACKER",
    )

    with pytest.raises(
        AuthorityResolutionError,
        match="beneficiary account does not correspond to authorised beneficiary",
    ):
        resolve_payment_authority(req, resolved_at=req.requested_execution_time)


def test_compatibility_cut_must_correspond_to_current_mandate_generation():
    """IC-FAIL-004: an explicit actor/operational cut cannot bless a new mandate cut by itself."""
    from app.engines.institutional_authority import (
        advance_mandate_source_generation_without_compatibility_for_test,
        restore_current_reference_compatibility_for_test,
    )

    req = _request()
    _, _, _, _, before = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )

    # Advance only the authoritative mandate source generation. Actor and operational
    # source generations remain unchanged and retain only their old explicit cut.
    advance_mandate_source_generation_without_compatibility_for_test()

    try:
        with pytest.raises(
            AuthorityResolutionError,
            match="compatible multi-source authority cut not established",
        ):
            resolve_payment_authority(req, resolved_at=req.requested_execution_time)
    finally:
        # The hostile mutation is process-global reference state. Restore only the
        # canonical test cut so this test cannot poison unrelated later tests.
        restore_current_reference_compatibility_for_test()


def test_semantic_definition_provenance_change_must_change_resolution_identity():
    """IC-FAIL-007: semantic definition provenance must be authority-material.

    A competent semantics-source change must not leave the resolved authority
    context/scope identity unchanged merely because proposition values are equal.
    """
    from app.engines.institutional_authority import (
        advance_authority_semantics_source_for_test,
        restore_authority_semantics_for_test,
    )

    req = _request()
    semantics_before, _, _, scope_before, context_before = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )

    previous = advance_authority_semantics_source_for_test()
    try:
        semantics_after, _, _, scope_after, context_after = resolve_payment_authority(
            req, resolved_at=req.requested_execution_time
        )
        assert semantics_after.semantics_set_id != semantics_before.semantics_set_id
        assert semantics_after.authoritative_source_id != semantics_before.authoritative_source_id
        assert context_after.context_id != context_before.context_id
        assert scope_after.scope_id != scope_before.scope_id
    finally:
        restore_authority_semantics_for_test(previous)


def test_caller_cannot_advance_authority_fence_without_transition_provenance():
    """IC-FAIL-008 failure-first: knowing the next fence is not authority to create it.

    The generic fence transition is authority-material because it changes the
    authoritative snapshot/context and invalidates prior execution authority.
    An ordinary caller must not be able to establish that transition merely by
    invoking a reachable helper with no competent transition provenance.
    """
    from app.engines.institutional_authority import (
        advance_authority_fence,
        get_authority_snapshot,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    # Hostile caller reaches the current generic transition helper directly.
    # The required architecture property is that this cannot establish a new
    # authoritative state without explicit competent transition provenance.
    try:
        advance_authority_fence()
    except (PermissionError, ValueError):
        pass

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.authority_fence == before.authority_fence, (
        "IC-FAIL-008: an unproven caller advanced authority-material fence "
        "state merely by invoking the generic transition helper"
    )
    assert after.snapshot_id == before.snapshot_id, (
        "IC-FAIL-008: unproven fence movement established a new authoritative "
        "snapshot without competent transition provenance"
    )


def test_competent_bounded_transition_can_advance_authority_fence():
    """IC-FAIL-008 positive control: remediation must not make state immutable."""
    from app.engines.institutional_authority import (
        advance_authority_fence,
        issue_authority_fence_transition_capability_for_test,
        get_authority_snapshot,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    advanced = advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        ),
    )

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert advanced == before.authority_fence + 1
    assert after.authority_fence == before.authority_fence + 1
    assert after.snapshot_id != before.snapshot_id


def test_fence_transition_authority_must_be_scoped_to_authority_domain():
    """IC-FAIL-008 second-order attack: a global transition key is not scoped authority.

    A transition authority valid for one institutional authority domain must not
    be sufficient to move a different domain merely because both share the same
    process-local fence mechanism.
    """
    from app.engines.institutional_authority import (
        advance_authority_fence,
        issue_authority_fence_transition_capability_for_test,
        get_authority_snapshot,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    # The current capability carries no principal/mandate/fence-scope identity.
    # Present it while explicitly claiming a different authority domain. A
    # conforming transition boundary must reject the mismatch rather than treat
    # possession of one global object as authority over every scope.
    foreign_scope = "institution-ATTACKER:MANDATE-ATTACKER"

    rejected_for_scope = False
    try:
        advance_authority_fence(
            transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        ),
            authority_fence_scope_key=foreign_scope,
        )
    except (PermissionError, ValueError):
        rejected_for_scope = True
    except TypeError as exc:
        pytest.fail(
            "IC-FAIL-008 unresolved: transition API has no authority-domain "
            f"scope semantics; Python rejected the probe before scope was evaluated: {exc}"
        )

    assert rejected_for_scope, (
        "IC-FAIL-008: foreign authority scope was not explicitly rejected"
    )

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.authority_fence == before.authority_fence, (
        "IC-FAIL-008: transition authority was not bound to the authority domain; "
        "a foreign-scope transition changed the canonical fence"
    )
    assert after.snapshot_id == before.snapshot_id


def test_scope_bound_fence_transition_authority_advances_its_own_domain():
    """IC-FAIL-008 positive control: correct scope remains transition-capable."""
    from app.engines.institutional_authority import (
        advance_authority_fence,
        issue_authority_fence_transition_capability_for_test,
        get_authority_snapshot,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    advanced = advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        ),
        authority_fence_scope_key=before.authority_fence_scope_key,
    )

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert advanced == before.authority_fence + 1
    assert after.authority_fence == before.authority_fence + 1
    assert after.snapshot_id != before.snapshot_id


def test_fence_transition_capability_cannot_be_replayed_across_successive_states():
    """IC-FAIL-008 third-order attack: scope alone must not create perpetual transition authority.

    A capability valid to move the canonical authority domain from its current
    state must not automatically remain valid to move the newly established
    authoritative state again. Otherwise one captured capability is an
    indefinite licence to manufacture future authority-state generations.
    """
    from app.engines.institutional_authority import (
        advance_authority_fence,
        issue_authority_fence_transition_capability_for_test,
        get_authority_snapshot,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    transition_authority = issue_authority_fence_transition_capability_for_test(
        before.authority_fence_scope_key
    )
    advance_authority_fence(
        transition_capability=transition_authority,
        authority_fence_scope_key=before.authority_fence_scope_key,
    )
    once = get_authority_snapshot("MANDATE-TREASURY-001")
    assert once is not None
    assert once.authority_fence == before.authority_fence + 1

    # Replay the exact same transition authority after the state it was used
    # against has already been superseded.
    try:
        advance_authority_fence(
            transition_capability=transition_authority,
            authority_fence_scope_key=once.authority_fence_scope_key,
        )
    except (PermissionError, ValueError):
        pass

    after_replay = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after_replay is not None
    assert after_replay.authority_fence == once.authority_fence, (
        "IC-FAIL-008: the same scope-bound transition capability was replayed "
        "to manufacture another authoritative fence generation"
    )
    assert after_replay.snapshot_id == once.snapshot_id


def test_fresh_transition_authority_for_new_state_can_advance_again():
    """IC-FAIL-008 positive control: stale rejection must not prevent lawful continuation."""
    from app.engines.institutional_authority import (
        advance_authority_fence,
        get_authority_snapshot,
        issue_authority_fence_transition_capability_for_test,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    first = issue_authority_fence_transition_capability_for_test(
        before.authority_fence_scope_key
    )
    advance_authority_fence(
        transition_capability=first,
        authority_fence_scope_key=before.authority_fence_scope_key,
    )

    middle = get_authority_snapshot("MANDATE-TREASURY-001")
    assert middle is not None
    assert middle.authority_fence == before.authority_fence + 1

    fresh = issue_authority_fence_transition_capability_for_test(
        middle.authority_fence_scope_key
    )
    advance_authority_fence(
        transition_capability=fresh,
        authority_fence_scope_key=middle.authority_fence_scope_key,
    )

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.authority_fence == middle.authority_fence + 1
    assert after.snapshot_id != middle.snapshot_id
