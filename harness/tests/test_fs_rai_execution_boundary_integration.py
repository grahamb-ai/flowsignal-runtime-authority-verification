from pathlib import Path
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash, validate_execution
from app.engines.financial_runtime import evaluate_financial
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.runtime_authority_payment import (
    prepare_payment_execution,
    final_bind_payment,
    mint_rai_bound_execution_permit,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


import pytest
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test


@pytest.fixture(autouse=True)
def _isolate_authority_usage_reference_state():
    # Independent tests must not inherit process-local aggregate reservations.
    # Multiple exercises inside one test still share the same state.
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()


def _attempt(req):
    return ExecutionAttempt(
        actor_id=req.actor_id,
        principal_id=req.principal_id,
        action=req.action,
        target=req.target,
        amount=req.amount,
        currency=req.currency,
        source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,
        mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time,
    )


def test_rai_final_bind_causally_mints_capability_consumed_by_protected_boundary():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED"

    permit = mint_rai_bound_execution_permit(req, prepared, bind_at=req.requested_execution_time)
    assert permit is not None
    assert permit.rai_determination_id == prepared.determination.determination_id
    assert permit.rai_constraint_id == prepared.constraint.constraint_id
    assert permit.rai_protected_operation_id == prepared.operation.operation_id
    assert permit.rai_authority_exercise_id == prepared.determination.authority_exercise_id
    assert permit.rai_execution_attempt_id == prepared.determination.execution_attempt_id

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=action_binding_hash(_attempt(req)),
    )
    assert outcome == "CONSEQUENCE_FORMED"


def test_rai_bound_permit_is_not_minted_when_final_bind_blocks():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    req.amount = req.amount + 1
    permit = mint_rai_bound_execution_permit(req, prepared, bind_at=req.requested_execution_time)
    assert permit is None


def test_post_resolution_beneficiary_account_substitution_blocks_final_bind():
    """MV-003 second-order: account correspondence must survive through final bind."""
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )

    substituted = replace(
        req,
        beneficiary_account_reference="ACCT-SUPPLIER-X-ATTACKER",
    )

    final = final_bind_payment(
        substituted,
        prepared,
        bind_at=req.requested_execution_time,
    )
    assert final.status != "PERMITTED", (
        "EXECUTION CORRESPONDENCE FAILURE: beneficiary account changed after "
        "authority resolution but final bind still permitted the operation"
    )

    permit = mint_rai_bound_execution_permit(
        substituted,
        prepared,
        bind_at=req.requested_execution_time,
    )
    assert permit is None, (
        "EXECUTION CORRESPONDENCE FAILURE: substituted beneficiary account "
        "received an RAI-bound execution capability"
    )


def test_distinct_execution_attempts_for_same_institutional_act_preserve_operation_identity():
    """IC-FAIL-006: attempt identity must not redefine institutional-act identity."""
    from app.engines.authority_determination import materialise_protected_operation
    from app.engines.authority_lineage import (
        create_authority_exercise,
        create_execution_attempt,
    )
    from app.engines.authority_resolution import resolve_payment_authority

    req = load_scenario(SCENARIO, rebase_to_now=False)
    _, _, _, scope, context = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    exercise = create_authority_exercise(
        resolution_context_id=context.context_id,
        effective_authority_scope_id=scope.scope_id,
        protected_operation_class=context.protected_operation_class,
        created_at=req.requested_execution_time,
    )
    first = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        created_at=req.requested_execution_time,
    )
    retry = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        created_at=req.requested_execution_time,
        parent_execution_attempt_id=first.execution_attempt_id,
    )

    first_operation = materialise_protected_operation(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=first.execution_attempt_id,
    )
    retry_operation = materialise_protected_operation(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=retry.execution_attempt_id,
    )

    assert first.execution_attempt_id != retry.execution_attempt_id
    assert retry.parent_execution_attempt_id == first.execution_attempt_id
    assert retry.attempt_ordinal == first.attempt_ordinal + 1
    assert first_operation.institutional_operation_id == retry_operation.institutional_operation_id, (
        "LINEAGE FAILURE: a retry of the same institutional act acquired a new "
        "institutional operation identity merely because execution-attempt identity changed"
    )
    assert first_operation.operation_id != retry_operation.operation_id, (
        "LINEAGE FAILURE: distinct execution attempts collapsed to the same concrete "
        "protected-operation materialisation"
    )


def test_distinct_institutional_act_cannot_reuse_prior_attempt_lineage():
    """IC-FAIL-006 converse: new institutional act cannot inherit an old attempt."""
    from app.engines.authority_determination import materialise_protected_operation
    from app.engines.authority_lineage import (
        bind_attempt_to_operation,
        create_authority_exercise,
        create_execution_attempt,
    )
    from app.engines.authority_resolution import resolve_payment_authority

    req = load_scenario(SCENARIO, rebase_to_now=False)
    _, _, _, scope, context = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    exercise = create_authority_exercise(
        resolution_context_id=context.context_id,
        effective_authority_scope_id=scope.scope_id,
        protected_operation_class=context.protected_operation_class,
        created_at=req.requested_execution_time,
    )
    attempt = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        created_at=req.requested_execution_time,
    )
    original = materialise_protected_operation(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
    )
    bind_attempt_to_operation(
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
        protected_operation_id=original.operation_id,
    )

    distinct_req = replace(
        req,
        institutional_operation_id="PAYMENT-INSTRUCTION-DISTINCT-002",
    )
    distinct = materialise_protected_operation(
        distinct_req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
    )

    assert distinct.institutional_operation_id != original.institutional_operation_id
    assert distinct.operation_id != original.operation_id
    with pytest.raises(ValueError, match="already bound to different operation"):
        bind_attempt_to_operation(
            authority_exercise_id=exercise.authority_exercise_id,
            execution_attempt_id=attempt.execution_attempt_id,
            protected_operation_id=distinct.operation_id,
        )


def test_authority_exercise_cannot_span_distinct_institutional_acts():
    """IC-FAIL-006: one authority exercise must not silently span distinct acts."""
    from app.engines.authority_determination import (
        bind_authority_to_operation,
        issue_authorised_execution_constraint,
        materialise_protected_operation,
    )
    from app.engines.authority_lineage import (
        create_authority_exercise,
        create_execution_attempt,
    )
    from app.engines.authority_resolution import resolve_payment_authority

    req = load_scenario(SCENARIO, rebase_to_now=False)
    _, _, _, scope, context = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    exercise = create_authority_exercise(
        resolution_context_id=context.context_id,
        effective_authority_scope_id=scope.scope_id,
        protected_operation_class=context.protected_operation_class,
        created_at=req.requested_execution_time,
    )
    first_attempt = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        created_at=req.requested_execution_time,
    )
    first_operation = materialise_protected_operation(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=first_attempt.execution_attempt_id,
    )
    first_binding = bind_authority_to_operation(scope, first_operation)
    issue_authorised_execution_constraint(
        context=context,
        scope=scope,
        operation=first_operation,
        binding=first_binding,
        resolved_at=req.requested_execution_time,
        authority_exercise=exercise,
        execution_attempt=first_attempt,
    )

    distinct_req = replace(
        req,
        institutional_operation_id="PAYMENT-INSTRUCTION-DISTINCT-EXERCISE-002",
    )
    second_attempt = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        created_at=req.requested_execution_time,
        parent_execution_attempt_id=first_attempt.execution_attempt_id,
    )
    second_operation = materialise_protected_operation(
        distinct_req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=second_attempt.execution_attempt_id,
    )
    assert second_operation.institutional_operation_id != first_operation.institutional_operation_id
    second_binding = bind_authority_to_operation(scope, second_operation)

    with pytest.raises(ValueError, match="authority exercise.*institutional operation"):
        issue_authorised_execution_constraint(
            context=context,
            scope=scope,
            operation=second_operation,
            binding=second_binding,
            resolved_at=req.requested_execution_time,
            authority_exercise=exercise,
            execution_attempt=second_attempt,
        )


def test_legacy_gateway_cannot_form_protected_consequence_without_rai_chain():
    """Failure-first route-closure challenge.

    The legacy receipt/gateway path must not retain an independent route to the
    protected consequence once RAI is claimed as mandatory for this operation.
    """
    req = load_scenario(SCENARIO, rebase_to_now=False)
    now = datetime.now(timezone.utc)
    req = replace(
        req,
        requested_execution_time=now,
        screening_captured_at=now,
        mandate_valid_until=now + timedelta(hours=1),
    )

    response, receipt = evaluate_financial(req, sealed_at=now)
    assert response.decision == "ALLOW"

    attempt = ExecutionAttempt(
        actor_id=req.actor_id,
        principal_id=req.principal_id,
        action=req.action,
        target=req.target,
        amount=req.amount,
        currency=req.currency,
        source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,
        mandate_id=req.mandate_id,
        attempted_at=now,
    )
    gateway = validate_execution(receipt, attempt)
    assert gateway.status == "PERMITTED"
    assert gateway.execution_permit is not None
    assert gateway.execution_permit.rai_determination_id is None

    outcome = execute_protected_consequence(
        permit=gateway.execution_permit,
        attempted_action_binding_hash=action_binding_hash(attempt),
    )

    assert outcome != "CONSEQUENCE_FORMED", (
        "ROUTE CLOSURE FAILURE: legacy gateway formed the protected consequence "
        "without the mandatory RAI determination/final-bind chain"
    )


def test_signed_rai_labels_without_registered_final_bind_cannot_form_consequence():
    """Second-order route-closure challenge: labels are not provenance.

    A caller that can reach the low-level permit signer must not be able to make
    an execution capability acceptable merely by supplying plausible RAI IDs.
    """
    from app.engines.authority_store import get_authority_state_version
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit

    req = load_scenario(SCENARIO, rebase_to_now=False)
    now = datetime.now(timezone.utc)
    req = replace(
        req,
        requested_execution_time=now,
        screening_captured_at=now,
        mandate_valid_until=now + timedelta(hours=1),
    )
    attempt = ExecutionAttempt(
        actor_id=req.actor_id,
        principal_id=req.principal_id,
        action=req.action,
        target=req.target,
        amount=req.amount,
        currency=req.currency,
        source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,
        mandate_id=req.mandate_id,
        attempted_at=now,
    )
    attempted_hash = action_binding_hash(attempt)
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    permit = issue_execution_permit(
        authority_receipt_id="FORGED-RAI-PROVENANCE",
        action_binding_hash=attempted_hash,
        authority_state_version=get_authority_state_version(),
        authority_snapshot_id=snapshot.snapshot_id,
        authority_subject_principal_id=snapshot.mandate.principal_id,
        authority_subject_mandate_id=snapshot.mandate.mandate_id,
        authority_epoch_id=snapshot.authority_epoch_id,
        authority_fence_scope_key=snapshot.authority_fence_scope_key,
        authority_fence=snapshot.authority_fence,
        authoritative_source_id=snapshot.authoritative_source_id,
        source_competence_root_id=snapshot.source_competence_root_id,
        authority_semantics_version=snapshot.semantics.version,
        authority_semantics_definition_id=snapshot.semantics.definition_id,
        authority_semantics_source_id=snapshot.semantics.source_id,
        valid_until=(now + timedelta(seconds=60)).isoformat(),
        rai_determination_id="DET-ATTACKER-SUPPLIED",
        rai_constraint_id="CONSTRAINT-ATTACKER-SUPPLIED",
        rai_protected_operation_id="OP-ATTACKER-SUPPLIED",
        rai_authority_exercise_id="EX-ATTACKER-SUPPLIED",
        rai_execution_attempt_id="ATT-ATTACKER-SUPPLIED",
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None
    assert permit.rai_determination_id is not None

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=attempted_hash,
    )
    assert outcome == "DENIED_RAI_EXECUTION_BINDING_REQUIRED"


def test_registered_rai_capability_cannot_be_rebound_to_different_action():
    """Third-order correspondence challenge against a genuine registered permit."""
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None

    substituted = _attempt(req)
    substituted.amount = substituted.amount + 1
    substituted_hash = action_binding_hash(substituted)
    assert substituted_hash != permit.action_binding_hash

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=substituted_hash,
    )
    assert outcome == "DENIED_ACTION_BINDING_MISMATCH"


def test_registered_rai_capability_signature_copy_with_changed_lineage_is_rejected():
    """Third-order challenge: genuine registry entry cannot bless altered lineage."""
    from dataclasses import replace as dc_replace

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None

    altered = dc_replace(
        permit,
        rai_execution_attempt_id="ATT-SUBSTITUTED-AFTER-MINT",
    )
    outcome = execute_protected_consequence(
        permit=altered,
        attempted_action_binding_hash=permit.action_binding_hash,
    )
    assert outcome == "DENIED_INVALID_EXECUTION_PERMIT"


def test_genuine_registered_rai_capability_is_single_use_at_commit_boundary():
    """Fourth-order challenge: a genuine capability cannot be replayed."""
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None
    attempted_hash = action_binding_hash(_attempt(req))

    first = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=attempted_hash,
    )
    second = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=attempted_hash,
    )

    assert first == "CONSEQUENCE_FORMED"
    assert second == "DENIED_EXECUTION_PERMIT_REPLAY"


def test_protected_consequence_cannot_form_if_prepared_usage_reservation_is_not_currently_reserved():
    """Failure-first: usage reservation must be a causal commitment prerequisite.

    A genuine RAI final-bind/permit must not remain sufficient if the authority
    usage reservation that justified this exact attempt has already been
    dispositioned before protected consequence formation.
    """
    from app.engines.authority_usage import release_authority_usage

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None

    release_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("COMPETENT-NONFORMATION-BEFORE-COMMIT",),
    )

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=action_binding_hash(_attempt(req)),
    )
    assert outcome != "CONSEQUENCE_FORMED", (
        "USAGE CAUSALITY FAILURE: protected consequence formed even though the "
        "exact prepared authority-usage reservation was no longer RESERVED"
    )


def test_successful_protected_commitment_consumes_the_exact_authority_usage_reservation():
    """Failure-first: commitment must disposition the exact supporting usage."""
    from app.engines.authority_usage import get_usage_reservation

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None
    before = get_usage_reservation(prepared.usage_reservation_id)
    assert before is not None and before.state.value == "reserved"

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=action_binding_hash(_attempt(req)),
    )
    assert outcome == "CONSEQUENCE_FORMED"

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "consumed", (
        "USAGE DISPOSITION FAILURE: protected commitment formed but the exact "
        "supporting authority-usage reservation remained unconsumed"
    )


def test_failure_after_unresolved_commitment_entry_does_not_leave_usage_merely_reserved():
    """Failure-first: uncertainty after commitment entry must quarantine usage.

    Once the protected boundary has durably consumed the permit and opened an
    unresolved outcome, an exception before represented formation must not leave
    the exact authority usage reservation looking freely RESERVED.
    """
    import pytest
    from app.engines.authority_usage import get_usage_reservation

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None

    def fail_inside_commitment_interval():
        raise RuntimeError("synthetic failure after unresolved commitment entry")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        execute_protected_consequence(
            permit=permit,
            attempted_action_binding_hash=action_binding_hash(_attempt(req)),
            before_formation_hook=fail_inside_commitment_interval,
        )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "quarantined", (
        "USAGE UNCERTAINTY FAILURE: commitment interval was entered and execution "
        "failed before represented formation, but the exact authority usage "
        "reservation remained available as RESERVED rather than QUARANTINED"
    )


def test_commitment_interval_failure_must_not_claim_competent_nonformation():
    """Failure-first: local interruption is not proof of consequence non-formation.

    After durable permit consumption and unresolved outcome creation, failure of
    the local formation hook establishes uncertainty unless competent external
    evidence proves non-formation. The stored outcome must not overclaim.
    """
    import pytest
    from app.engines.consequence_outcome_store import get_consequence_outcome

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None
    attempted_hash = action_binding_hash(_attempt(req))

    def fail_inside_commitment_interval():
        raise RuntimeError("synthetic unresolved commitment interval failure")

    with pytest.raises(RuntimeError, match="synthetic unresolved"):
        execute_protected_consequence(
            permit=permit,
            attempted_action_binding_hash=attempted_hash,
            before_formation_hook=fail_inside_commitment_interval,
        )

    stored = get_consequence_outcome(permit.signature, attempted_hash)
    assert stored is not None
    assert stored.outcome == "CONSEQUENCE_OUTCOME_UNRESOLVED", (
        "OUTCOME EVIDENCE FAILURE: local commitment-interval interruption was "
        "recorded as competent non-formation rather than preserved as unresolved"
    )


def test_quarantined_usage_cannot_be_released_by_unstructured_evidence_id_alone():
    """Failure-first: release requires competent outcome evidence, not a string.

    A quarantined reservation represents unresolved post-commit consequence
    state. An arbitrary caller-supplied evidence identifier must not be enough
    to turn that uncertainty into reusable authority capacity.
    """
    import pytest
    from app.engines.authority_usage import (
        get_usage_reservation,
        quarantine_authority_usage,
        release_authority_usage,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )

    quarantine_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("SYNTHETIC-UNRESOLVED-EVIDENCE",),
    )
    quarantined = get_usage_reservation(prepared.usage_reservation_id)
    assert quarantined is not None
    assert quarantined.state.value == "quarantined"

    with pytest.raises(ValueError):
        release_authority_usage(
            prepared.usage_reservation_id,
            evidence_ids=("CALLER-SAYS-NOT-FORMED",),
        )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "quarantined"


def test_quarantined_usage_can_be_released_only_by_competent_nonformation_resolution():
    """Positive control: quarantine must be resolvable to RELEASED by competent non-formation evidence."""
    from app.engines.authority_usage import (
        get_usage_reservation,
        quarantine_authority_usage,
        resolve_quarantined_authority_usage,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    quarantine_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",),
    )

    from app.engines.outcome_evidence import (
        CompetentOutcomeEvidence,
        register_competent_outcome_evidence,
    )
    attempted_hash = action_binding_hash(_attempt(req))
    evidence_id = "EVIDENCE:NONFORMATION:EXACT-EXECUTION"
    register_competent_outcome_evidence(
        CompetentOutcomeEvidence(
            evidence_id=evidence_id,
            permit_signature="REFERENCE-PERMIT:NON_FORMATION",
            action_binding_hash=attempted_hash,
            outcome="NON_FORMATION",
            authoritative_source_id="REFERENCE-CONSEQUENCE-OBSERVER-001",
            source_competence_id="REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        )
    )
    resolve_quarantined_authority_usage(
        prepared.usage_reservation_id,
        resolution="NON_FORMATION",
        evidence_ids=(evidence_id,),
        permit_signature="REFERENCE-PERMIT:NON_FORMATION",
        action_binding_hash=attempted_hash,
    )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "released"


def test_quarantined_usage_can_be_consumed_only_by_competent_formation_resolution():
    """Positive control: quarantine must be resolvable to CONSUMED by competent formation evidence."""
    from app.engines.authority_usage import (
        get_usage_reservation,
        quarantine_authority_usage,
        resolve_quarantined_authority_usage,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    quarantine_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",),
    )

    from app.engines.outcome_evidence import (
        CompetentOutcomeEvidence,
        register_competent_outcome_evidence,
    )
    attempted_hash = action_binding_hash(_attempt(req))
    evidence_id = "EVIDENCE:FORMATION:EXACT-EXECUTION"
    register_competent_outcome_evidence(
        CompetentOutcomeEvidence(
            evidence_id=evidence_id,
            permit_signature="REFERENCE-PERMIT:FORMATION",
            action_binding_hash=attempted_hash,
            outcome="FORMATION",
            authoritative_source_id="REFERENCE-CONSEQUENCE-OBSERVER-001",
            source_competence_id="REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        )
    )
    resolve_quarantined_authority_usage(
        prepared.usage_reservation_id,
        resolution="FORMATION",
        evidence_ids=(evidence_id,),
        permit_signature="REFERENCE-PERMIT:FORMATION",
        action_binding_hash=attempted_hash,
    )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "consumed"


def test_quarantine_resolution_rejects_forged_competence_prefix():
    """Failure-first: caller-controlled syntax must not manufacture evidence competence."""
    import pytest
    from app.engines.authority_usage import (
        get_usage_reservation,
        quarantine_authority_usage,
        resolve_quarantined_authority_usage,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    quarantine_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",),
    )

    forged = "COMPETENT-NONFORMATION:ATTACKER-CONTROLLED-ASSERTION"
    with pytest.raises(ValueError, match="competent|evidence|provenance"):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="NON_FORMATION",
            evidence_ids=(forged,),
            permit_signature="ATTACKER-PERMIT",
            action_binding_hash=action_binding_hash(_attempt(req)),
        )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "quarantined", (
        "EVIDENCE COMPETENCE FAILURE: caller-manufactured prefix released "
        "quarantined authority without independently grounded outcome evidence"
    )


def test_quarantine_resolution_rejects_competent_evidence_for_different_execution():
    """Failure-first correspondence control: competent evidence must bind this exact execution."""
    import pytest
    from app.engines.authority_usage import (
        get_usage_reservation,
        quarantine_authority_usage,
        resolve_quarantined_authority_usage,
    )
    from app.engines.outcome_evidence import (
        CompetentOutcomeEvidence,
        register_competent_outcome_evidence,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    quarantine_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",),
    )

    evidence_id = "EVIDENCE:NONFORMATION:DIFFERENT-EXECUTION"
    register_competent_outcome_evidence(
        CompetentOutcomeEvidence(
            evidence_id=evidence_id,
            permit_signature="OTHER-PERMIT",
            action_binding_hash="OTHER-ACTION-BINDING",
            outcome="NON_FORMATION",
            authoritative_source_id="REFERENCE-CONSEQUENCE-OBSERVER-001",
            source_competence_id="REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        )
    )

    with pytest.raises(ValueError, match="competent|exact execution|evidence"):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="NON_FORMATION",
            evidence_ids=(evidence_id,),
            permit_signature="THIS-PERMIT",
            action_binding_hash=action_binding_hash(_attempt(req)),
        )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "quarantined"


def test_quarantine_resolution_rejects_competent_evidence_with_opposite_outcome():
    """Outcome correspondence: competent FORMATION evidence cannot resolve as NON_FORMATION."""
    import pytest
    from app.engines.authority_usage import (
        get_usage_reservation,
        quarantine_authority_usage,
        resolve_quarantined_authority_usage,
    )
    from app.engines.outcome_evidence import (
        CompetentOutcomeEvidence,
        register_competent_outcome_evidence,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    quarantine_authority_usage(
        prepared.usage_reservation_id,
        evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",),
    )
    permit_signature = "REFERENCE-PERMIT:OUTCOME-MISMATCH"
    attempted_hash = action_binding_hash(_attempt(req))
    evidence_id = "EVIDENCE:FORMATION:OUTCOME-MISMATCH"
    register_competent_outcome_evidence(
        CompetentOutcomeEvidence(
            evidence_id=evidence_id,
            permit_signature=permit_signature,
            action_binding_hash=attempted_hash,
            outcome="FORMATION",
            authoritative_source_id="REFERENCE-CONSEQUENCE-OBSERVER-001",
            source_competence_id="REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        )
    )

    with pytest.raises(ValueError, match="competent|exact execution|evidence"):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="NON_FORMATION",
            evidence_ids=(evidence_id,),
            permit_signature=permit_signature,
            action_binding_hash=attempted_hash,
        )

    after = get_usage_reservation(prepared.usage_reservation_id)
    assert after is not None
    assert after.state.value == "quarantined"


def test_competent_outcome_evidence_identity_cannot_be_rebound():
    """Evidence identity must be immutable across execution and outcome bindings."""
    import pytest
    from app.engines.outcome_evidence import (
        CompetentOutcomeEvidence,
        register_competent_outcome_evidence,
    )

    evidence_id = "EVIDENCE:IMMUTABLE-IDENTITY-001"
    original = CompetentOutcomeEvidence(
        evidence_id=evidence_id,
        permit_signature="PERMIT:ORIGINAL",
        action_binding_hash="ACTION:ORIGINAL",
        outcome="NON_FORMATION",
        authoritative_source_id="REFERENCE-CONSEQUENCE-OBSERVER-001",
        source_competence_id="REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
    )
    register_competent_outcome_evidence(original)

    rebound = CompetentOutcomeEvidence(
        evidence_id=evidence_id,
        permit_signature="PERMIT:REBOUND",
        action_binding_hash="ACTION:REBOUND",
        outcome="FORMATION",
        authoritative_source_id="REFERENCE-CONSEQUENCE-OBSERVER-001",
        source_competence_id="REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
    )
    with pytest.raises(ValueError, match="identity|bound|evidence"):
        register_competent_outcome_evidence(rebound)


def test_disagreeing_registered_outcomes_preserve_quarantine():
    """Two registered outcomes for one execution must not be caller-selectable."""
    import pytest
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:DISAGREEMENT"
    binding = action_binding_hash(_attempt(req))
    yes_id, no_id = "EVIDENCE:FORMED:D1", "EVIDENCE:NOT-FORMED:D2"
    register_competent_outcome_evidence(CompetentOutcomeEvidence(yes_id, sig, binding, "FORMATION", "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"))
    register_competent_outcome_evidence(CompetentOutcomeEvidence(no_id, sig, binding, "NON_FORMATION", "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"))

    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(prepared.usage_reservation_id, resolution="NON_FORMATION", evidence_ids=(no_id,), permit_signature=sig, action_binding_hash=binding)
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_duplicate_consistent_competent_outcome_evidence_can_resolve_quarantine():
    """Positive control: multiple agreeing competent observations must not create false conflict."""
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:AGREEING-EVIDENCE"
    binding = action_binding_hash(_attempt(req))
    first_id, second_id = "EVIDENCE:NOT-FORMED:AGREE-1", "EVIDENCE:NOT-FORMED:AGREE-2"
    for evidence_id in (first_id, second_id):
        register_competent_outcome_evidence(CompetentOutcomeEvidence(evidence_id, sig, binding, "NON_FORMATION", "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"))

    resolve_quarantined_authority_usage(prepared.usage_reservation_id, resolution="NON_FORMATION", evidence_ids=(first_id,), permit_signature=sig, action_binding_hash=binding)
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "released"


def test_later_agreeing_observation_does_not_silently_override_prior_disagreement():
    """No implicit latest-wins rule: disagreement remains unresolved absent explicit supersession semantics."""
    import pytest
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:NO-LATEST-WINS"
    binding = action_binding_hash(_attempt(req))
    observations = (
        ("EVIDENCE:FORMED:EARLY", "FORMATION"),
        ("EVIDENCE:NOT-FORMED:EARLY", "NON_FORMATION"),
        ("EVIDENCE:NOT-FORMED:LATER", "NON_FORMATION"),
    )
    for evidence_id, outcome in observations:
        register_competent_outcome_evidence(CompetentOutcomeEvidence(evidence_id, sig, binding, outcome, "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"))

    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(prepared.usage_reservation_id, resolution="NON_FORMATION", evidence_ids=("EVIDENCE:NOT-FORMED:LATER",), permit_signature=sig, action_binding_hash=binding)
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_explicit_final_supersession_can_resolve_prior_provisional_disagreement():
    """Positive control for an explicit evidence lifecycle; registration order alone is insufficient."""
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:EXPLICIT-SUPERSESSION"
    binding = action_binding_hash(_attempt(req))

    provisional_formed = CompetentOutcomeEvidence(
        "EVIDENCE:PROVISIONAL:FORMED", sig, binding, "FORMATION",
        "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        finality_state="PROVISIONAL",
    )
    provisional_not_formed = CompetentOutcomeEvidence(
        "EVIDENCE:PROVISIONAL:NOT-FORMED:INCOMPLETE-SET", sig, binding, "NON_FORMATION",
        "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        finality_state="PROVISIONAL",
    )
    final_not_formed = CompetentOutcomeEvidence(
        "EVIDENCE:FINAL:NOT-FORMED", sig, binding, "NON_FORMATION",
        "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001",
        finality_state="FINAL",
        supersedes_evidence_ids=(provisional_formed.evidence_id, provisional_not_formed.evidence_id),
    )
    for evidence in (provisional_formed, provisional_not_formed, final_not_formed):
        register_competent_outcome_evidence(evidence)

    resolve_quarantined_authority_usage(
        prepared.usage_reservation_id,
        resolution="NON_FORMATION",
        evidence_ids=(final_not_formed.evidence_id,),
        permit_signature=sig,
        action_binding_hash=binding,
    )
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "released"


def test_final_evidence_cannot_supersede_observation_from_different_execution():
    """Supersession correspondence must remain inside the exact execution."""
    import pytest
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    prior = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:OTHER-EXEC", "PERMIT:A", "ACTION:A", "FORMATION", source, competence, finality_state="PROVISIONAL")
    register_competent_outcome_evidence(prior)
    successor = CompetentOutcomeEvidence("EVIDENCE:FINAL:CROSS-EXEC", "PERMIT:B", "ACTION:B", "NON_FORMATION", source, competence, finality_state="FINAL", supersedes_evidence_ids=(prior.evidence_id,))
    with pytest.raises(ValueError, match="exact execution|supersession"):
        register_competent_outcome_evidence(successor)


def test_final_outcome_evidence_cannot_be_superseded():
    """Final evidence is not silently demoted by another observation."""
    import pytest
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    prior = CompetentOutcomeEvidence("EVIDENCE:FINAL:IMMUTABLE", "PERMIT:FINALITY", "ACTION:FINALITY", "FORMATION", source, competence, finality_state="FINAL")
    register_competent_outcome_evidence(prior)
    successor = CompetentOutcomeEvidence("EVIDENCE:FINAL:REPLACEMENT", "PERMIT:FINALITY", "ACTION:FINALITY", "NON_FORMATION", source, competence, finality_state="FINAL", supersedes_evidence_ids=(prior.evidence_id,))
    with pytest.raises(ValueError, match="provisional|supersed"):
        register_competent_outcome_evidence(successor)


def test_provisional_outcome_evidence_cannot_supersede_prior_observation():
    """Only final evidence may perform explicit supersession."""
    import pytest
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    prior = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:PRIOR", "PERMIT:PROV", "ACTION:PROV", "FORMATION", source, competence, finality_state="PROVISIONAL")
    register_competent_outcome_evidence(prior)
    successor = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:SUCCESSOR", "PERMIT:PROV", "ACTION:PROV", "NON_FORMATION", source, competence, finality_state="PROVISIONAL", supersedes_evidence_ids=(prior.evidence_id,))
    with pytest.raises(ValueError, match="final|supersed"):
        register_competent_outcome_evidence(successor)


def test_final_evidence_cannot_selectively_supersede_only_one_side_of_disagreement():
    """Failure-first: final supersession must not manufacture coherence by pruning only one conflicting predecessor."""
    import pytest
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:SELECTIVE-SUPERSESSION"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    formed = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:FORMED:SELECTIVE", sig, binding, "FORMATION", source, competence, finality_state="PROVISIONAL")
    not_formed = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:NOT-FORMED:SELECTIVE", sig, binding, "NON_FORMATION", source, competence, finality_state="PROVISIONAL")
    for evidence in (formed, not_formed):
        register_competent_outcome_evidence(evidence)

    selective_final = CompetentOutcomeEvidence(
        "EVIDENCE:FINAL:NOT-FORMED:SELECTIVE", sig, binding, "NON_FORMATION", source, competence,
        finality_state="FINAL", supersedes_evidence_ids=(formed.evidence_id,),
    )
    register_competent_outcome_evidence(selective_final)

    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="NON_FORMATION",
            evidence_ids=(selective_final.evidence_id,),
            permit_signature=sig,
            action_binding_hash=binding,
        )
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_final_supersession_cannot_omit_same_outcome_member_of_prior_contradictory_set():
    """Whole-set means the entire contradictory provisional observation set, not merely every outcome class."""
    import pytest
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:INCOMPLETE-WHOLE-SET"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    a = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:FORMED:A:INCOMPLETE-WHOLE-SET", sig, binding, "FORMATION", source, competence, finality_state="PROVISIONAL")
    b = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:FORMED:B:INCOMPLETE-WHOLE-SET", sig, binding, "FORMATION", source, competence, finality_state="PROVISIONAL")
    n = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:NOT-FORMED:INCOMPLETE-WHOLE-SET", sig, binding, "NON_FORMATION", source, competence, finality_state="PROVISIONAL")
    for evidence in (a, b, n):
        register_competent_outcome_evidence(evidence)
    final = CompetentOutcomeEvidence(
        "EVIDENCE:FINAL:NOT-FORMED:INCOMPLETE-WHOLE-SET", sig, binding, "NON_FORMATION", source, competence,
        finality_state="FINAL", supersedes_evidence_ids=(a.evidence_id, n.evidence_id),
    )
    register_competent_outcome_evidence(final)
    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id, resolution="NON_FORMATION", evidence_ids=(final.evidence_id,),
            permit_signature=sig, action_binding_hash=binding,
        )
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_two_final_observations_with_opposite_outcomes_preserve_quarantine():
    """Conflicting FINAL evidence has no precedence rule and must remain unresolved."""
    import pytest
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:FINAL-DISAGREEMENT"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    formed = CompetentOutcomeEvidence("EVIDENCE:FINAL:FORMED:FINAL-DISAGREEMENT", sig, binding, "FORMATION", source, competence, finality_state="FINAL")
    not_formed = CompetentOutcomeEvidence("EVIDENCE:FINAL:NOT-FORMED:FINAL-DISAGREEMENT", sig, binding, "NON_FORMATION", source, competence, finality_state="FINAL")
    register_competent_outcome_evidence(formed)
    register_competent_outcome_evidence(not_formed)

    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="NON_FORMATION",
            evidence_ids=(not_formed.evidence_id,),
            permit_signature=sig,
            action_binding_hash=binding,
        )
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_final_evidence_cannot_supersede_provisional_set_that_includes_unknown_source_observation():
    """Supersession cannot erase uncertainty by excluding an observation merely because its source is not competent for resolution."""
    import pytest
    import app.engines.outcome_evidence as oe
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:UNKNOWN-SOURCE-DISAGREEMENT"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    competent = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:KNOWN:UNKNOWN-SOURCE-CASE", sig, binding, "FORMATION", source, competence, finality_state="PROVISIONAL")
    register_competent_outcome_evidence(competent)
    # Simulate preserved external observation not admitted as competent resolution evidence.
    unknown = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:UNKNOWN-SOURCE", sig, binding, "NON_FORMATION", "UNKNOWN-OBSERVER", "UNKNOWN-COMPETENCE", finality_state="PROVISIONAL")
    with oe._LOCK:
        oe._EVIDENCE[unknown.evidence_id] = unknown
    final = CompetentOutcomeEvidence("EVIDENCE:FINAL:KNOWN:UNKNOWN-SOURCE-CASE", sig, binding, "FORMATION", source, competence, finality_state="FINAL", supersedes_evidence_ids=(competent.evidence_id,))
    register_competent_outcome_evidence(final)

    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(prepared.usage_reservation_id, resolution="FORMATION", evidence_ids=(final.evidence_id,), permit_signature=sig, action_binding_hash=binding)
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_agreeing_unknown_source_observation_does_not_veto_competent_final_resolution():
    """Untrusted agreeing noise must not gain veto power over an otherwise coherent competent FINAL outcome."""
    import app.engines.outcome_evidence as oe
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:AGREEING-UNKNOWN-SOURCE"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    competent = CompetentOutcomeEvidence("EVIDENCE:FINAL:NON-FORMATION:AGREEING-UNKNOWN", sig, binding, "NON_FORMATION", source, competence, finality_state="FINAL")
    register_competent_outcome_evidence(competent)
    unknown = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:UNKNOWN:AGREEING", sig, binding, "NON_FORMATION", "UNKNOWN-OBSERVER", "UNKNOWN-COMPETENCE", finality_state="PROVISIONAL")
    with oe._LOCK:
        oe._EVIDENCE[unknown.evidence_id] = unknown

    resolved = resolve_quarantined_authority_usage(
        prepared.usage_reservation_id,
        resolution="NON_FORMATION",
        evidence_ids=(competent.evidence_id,),
        permit_signature=sig,
        action_binding_hash=binding,
    )
    assert resolved.to_state.value == "released"
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "released"


def test_unknown_source_cannot_match_callers_requested_outcome_to_veto_opposite_competent_final():
    """Unknown-source evidence is compared with the competent evidence set, not trusted caller-selected resolution."""
    import pytest
    import app.engines.outcome_evidence as oe
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:CALLER-SELECTED-UNKNOWN-OUTCOME"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    formed = CompetentOutcomeEvidence("EVIDENCE:FINAL:FORMED:CALLER-SELECTED", sig, binding, "FORMATION", source, competence, finality_state="FINAL")
    register_competent_outcome_evidence(formed)
    unknown = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:UNKNOWN:CALLER-NON-FORMATION", sig, binding, "NON_FORMATION", "UNKNOWN-OBSERVER", "UNKNOWN-COMPETENCE", finality_state="PROVISIONAL")
    with oe._LOCK:
        oe._EVIDENCE[unknown.evidence_id] = unknown

    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="NON_FORMATION",
            evidence_ids=(unknown.evidence_id,),
            permit_signature=sig,
            action_binding_hash=binding,
        )
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "quarantined"


def test_later_contradictory_observation_cannot_arrive_after_final_resolution_and_release():
    """Once FINAL evidence has caused irreversible usage disposition, later contradictory evidence must not reopen the execution history."""
    import pytest
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:POST-FINAL-CONTRADICTION"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    final_nonformation = CompetentOutcomeEvidence("EVIDENCE:FINAL:NON-FORMATION:POST-FINAL", sig, binding, "NON_FORMATION", source, competence, finality_state="FINAL")
    register_competent_outcome_evidence(final_nonformation)
    resolve_quarantined_authority_usage(prepared.usage_reservation_id, resolution="NON_FORMATION", evidence_ids=(final_nonformation.evidence_id,), permit_signature=sig, action_binding_hash=binding)
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "released"

    later_formed = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:FORMATION:AFTER-FINAL", sig, binding, "FORMATION", source, competence, finality_state="PROVISIONAL")
    register_competent_outcome_evidence(later_formed)

    from app.engines.outcome_evidence import get_closed_outcome_disposition
    assert get_closed_outcome_disposition(permit_signature=sig, action_binding_hash=binding) == "NON_FORMATION"
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "released"

    # The contradictory observation is preserved; it does not silently rewrite
    # the already-relied-upon disposition or masquerade as a new resolution.
    with pytest.raises(ValueError):
        resolve_quarantined_authority_usage(
            prepared.usage_reservation_id,
            resolution="FORMATION",
            evidence_ids=(later_formed.evidence_id,),
            permit_signature=sig,
            action_binding_hash=binding,
        )


def test_later_agreeing_competent_evidence_is_preserved_after_closed_disposition():
    """Disposition closure must not become an evidence-ingestion freeze; later agreeing competent evidence may corroborate history."""
    from app.engines.authority_usage import get_usage_reservation, quarantine_authority_usage, resolve_quarantined_authority_usage
    from app.engines.outcome_evidence import CompetentOutcomeEvidence, register_competent_outcome_evidence, get_closed_outcome_disposition

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    quarantine_authority_usage(prepared.usage_reservation_id, evidence_ids=("UNRESOLVED:LOCAL-INTERRUPTION",))
    sig = "REFERENCE-PERMIT:POST-DISPOSITION-CORROBORATION"
    binding = action_binding_hash(_attempt(req))
    source, competence = "REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"
    final_nonformation = CompetentOutcomeEvidence("EVIDENCE:FINAL:NON-FORMATION:CORROBORATION-BASE", sig, binding, "NON_FORMATION", source, competence, finality_state="FINAL")
    register_competent_outcome_evidence(final_nonformation)
    resolve_quarantined_authority_usage(prepared.usage_reservation_id, resolution="NON_FORMATION", evidence_ids=(final_nonformation.evidence_id,), permit_signature=sig, action_binding_hash=binding)

    later_agreeing = CompetentOutcomeEvidence("EVIDENCE:PROVISIONAL:NON-FORMATION:AFTER-DISPOSITION", sig, binding, "NON_FORMATION", source, competence, finality_state="PROVISIONAL")
    register_competent_outcome_evidence(later_agreeing)

    assert get_closed_outcome_disposition(permit_signature=sig, action_binding_hash=binding) == "NON_FORMATION"
    assert get_usage_reservation(prepared.usage_reservation_id).state.value == "released"


def test_two_exercises_cannot_each_receive_fresh_capacity_from_same_governing_mandate():
    """IC-FAIL-005 failure-first: aggregate mandate capacity must span authority exercises, not reset per exercise."""
    from dataclasses import replace
    from decimal import Decimal

    req = load_scenario(SCENARIO, rebase_to_now=False)
    req_a = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-AGGREGATE-A")
    req_b = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-AGGREGATE-B")

    first = prepare_payment_execution(req_a, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req_a.requested_execution_time)

    import pytest
    with pytest.raises(ValueError):
        prepare_payment_execution(req_b, route_id="R1", executor_id="PAYMENT-EXECUTOR-1", resolved_at=req_b.requested_execution_time)


def test_aggregate_mandate_capacity_allows_multiple_exercises_within_limit():
    """IC-FAIL-005 positive control: shared aggregate scope must not become an always-deny gate."""
    from dataclasses import replace
    from decimal import Decimal

    req = load_scenario(SCENARIO, rebase_to_now=False)
    req_a = replace(req, amount=Decimal("400000.00"), institutional_operation_id="PAYMENT-AGGREGATE-POS-A")
    req_b = replace(req, amount=Decimal("500000.00"), institutional_operation_id="PAYMENT-AGGREGATE-POS-B")

    first = prepare_payment_execution(
        req_a, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_a.requested_execution_time,
    )
    second = prepare_payment_execution(
        req_b, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_b.requested_execution_time,
    )

    from app.engines.authority_usage import get_usage_reservation

    first_reservation = get_usage_reservation(first.usage_reservation_id)
    second_reservation = get_usage_reservation(second.usage_reservation_id)

    assert first_reservation is not None
    assert second_reservation is not None
    assert first_reservation.reserved_amount_or_units == Decimal("400000.00")
    assert second_reservation.reserved_amount_or_units == Decimal("500000.00")
    assert first.usage_policy_id == second.usage_policy_id


def test_authority_epoch_change_does_not_resurrect_aggregate_mandate_capacity():
    """Failure-first: authority-state epoch change alone must not replenish mandate economics."""
    from dataclasses import replace
    from decimal import Decimal
    from app.engines.institutional_authority import advance_authority_epoch_for_test

    req = load_scenario(SCENARIO, rebase_to_now=False)
    req_a = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-EPOCH-CAPACITY-A")
    req_b = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-EPOCH-CAPACITY-B")

    first = prepare_payment_execution(
        req_a, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_a.requested_execution_time,
    )
    assert first is not None

    advance_authority_epoch_for_test()

    with pytest.raises(ValueError):
        prepare_payment_execution(
            req_b, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
            resolved_at=req_b.requested_execution_time,
        )


def test_caller_cannot_self_issue_fresh_aggregate_window_to_replenish_mandate_capacity():
    """Failure-first: caller-chosen usage-window identity must not manufacture fresh mandate capacity."""
    from dataclasses import replace
    from decimal import Decimal
    from app.engines.authority_domain import AuthorityUsageMode, AuthorityUsagePolicy
    from app.engines.authority_usage import register_usage_policy, reserve_authority_usage

    req = load_scenario(SCENARIO, rebase_to_now=False)
    req_a = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-WINDOW-A")
    first = prepare_payment_execution(
        req_a, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_a.requested_execution_time,
    )
    assert first is not None

    # A caller now attempts to manufacture a fresh economic window for the
    # unchanged governing mandate. No authoritative replenishment event or
    # competent evidence exists for this new window.
    forged_policy = AuthorityUsagePolicy(
        usage_policy_id="USAGE-POLICY:MANDATE:institution-001:MANDATE-TREASURY-001:CALLER-WINDOW-002",
        authority_scope_id=first.determination.effective_authority_scope_id,
        mode=AuthorityUsageMode.AGGREGATE,
        scope_key="MANDATE:institution-001:MANDATE-TREASURY-001:CALLER-WINDOW-002",
        capacity=Decimal("1000000.00"),
        window_id="CALLER-WINDOW-002",
        disposition_rule_id="NORM-PAY-001:aggregate-amount:v1",
    )
    # The refusal now occurs at the earlier and stronger boundary: an
    # untrusted caller cannot register the fresh economic scope at all.
    with pytest.raises(ValueError, match="authoritative derivation"):
        register_usage_policy(forged_policy)


def test_authoritative_usage_window_rollover_can_establish_fresh_normative_capacity():
    """Failure-first positive mirror: a competent normative window transition must be able to establish the next aggregate pool."""
    from dataclasses import replace
    from decimal import Decimal
    from app.engines.authority_usage import consume_authority_usage
    from app.engines.institutional_authority import advance_usage_window_for_test

    req = load_scenario(SCENARIO, rebase_to_now=False)
    req_a = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-WINDOW-ROLLOVER-A")
    req_b = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-WINDOW-ROLLOVER-B")

    first = prepare_payment_execution(
        req_a, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_a.requested_execution_time,
    )
    consume_authority_usage(
        first.usage_reservation_id,
        evidence_ids=("REFERENCE:COMMITMENT-FORMED:WINDOW-1",),
    )

    # This is intentionally an authoritative reference-state transition, not a
    # caller-selected window string. The fixture requires frozen usage-window
    # semantics; the implementation does not yet expose this transition.
    advance_usage_window_for_test()

    second = prepare_payment_execution(
        req_b, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_b.requested_execution_time,
    )
    assert second is not None
    assert second.usage_policy_id != first.usage_policy_id


def test_usage_window_rollover_does_not_refund_unresolved_prior_window_authority():
    """Second-order: rollover must not turn prior-window unresolved authority into reusable authority."""
    from dataclasses import replace
    from decimal import Decimal
    from app.engines.authority_usage import quarantine_authority_usage, get_usage_reservation
    from app.engines.institutional_authority import advance_usage_window_for_test

    req = load_scenario(SCENARIO, rebase_to_now=False)
    req_a = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-WINDOW-UNRESOLVED-A")
    req_b = replace(req, amount=Decimal("600000.00"), institutional_operation_id="PAYMENT-WINDOW-UNRESOLVED-B")

    first = prepare_payment_execution(
        req_a, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_a.requested_execution_time,
    )
    quarantine_authority_usage(
        first.usage_reservation_id,
        evidence_ids=("UNRESOLVED:PRIOR-WINDOW-COMMITMENT",),
    )
    assert get_usage_reservation(first.usage_reservation_id).state.value == "quarantined"

    advance_usage_window_for_test()

    second = prepare_payment_execution(
        req_b, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req_b.requested_execution_time,
    )
    assert second is not None

    # The new window may have its own normative capacity, but rollover must not
    # mutate/refund the unresolved reservation attributed to the prior window.
    prior = get_usage_reservation(first.usage_reservation_id)
    assert prior.state.value == "quarantined"
    assert prior.reserved_amount_or_units == Decimal("600000.00")
    assert second.usage_policy_id != first.usage_policy_id


def test_usage_window_transition_cannot_be_replayed_back_to_prior_window():
    """Second-order failure-first: authoritative usage-window state must be monotonic; prior window identity cannot be replayed."""
    from app.engines.institutional_authority import (
        advance_usage_window_for_test,
        get_authority_snapshot,
        set_usage_window_for_test,
        _USAGE_WINDOW_TRANSITION_CAPABILITY,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None
    prior_window = before.usage_window_id

    next_window = advance_usage_window_for_test()
    assert next_window != prior_window

    # A stale/replayed transition must not be able to move authoritative state
    # backwards to the prior economic window.
    with pytest.raises(ValueError, match="usage window"):
        set_usage_window_for_test(prior_window, transition_capability=_USAGE_WINDOW_TRANSITION_CAPABILITY)

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.usage_window_id == next_window


def test_usage_window_transition_rejects_duplicate_current_window():
    """Second-order: duplicate/equal window transition must not create a new authoritative transition."""
    from app.engines.institutional_authority import (
        advance_usage_window_for_test,
        get_authority_snapshot,
        set_usage_window_for_test,
        _USAGE_WINDOW_TRANSITION_CAPABILITY,
    )

    current_window = advance_usage_window_for_test()
    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None
    assert before.usage_window_id == current_window

    with pytest.raises(ValueError, match="strictly forward"):
        set_usage_window_for_test(current_window, transition_capability=_USAGE_WINDOW_TRANSITION_CAPABILITY)

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.usage_window_id == current_window
    assert after.authority_fence == before.authority_fence


def test_usage_window_transition_rejects_wrong_window_domain():
    """Second-order: a foreign window namespace must not replace the authoritative economic window."""
    from app.engines.institutional_authority import (
        get_authority_snapshot,
        set_usage_window_for_test,
        _USAGE_WINDOW_TRANSITION_CAPABILITY,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    with pytest.raises(ValueError, match="domain mismatch"):
        set_usage_window_for_test("FOREIGN-WINDOW-999", transition_capability=_USAGE_WINDOW_TRANSITION_CAPABILITY)

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.usage_window_id == before.usage_window_id
    assert after.authority_fence == before.authority_fence


def test_forward_looking_window_value_cannot_self_authorise_rollover():
    """Failure-first: syntactic forwardness is not authority to create a future economic window."""
    from app.engines.institutional_authority import (
        get_authority_snapshot,
        set_usage_window_for_test,
    )

    before = get_authority_snapshot("MANDATE-TREASURY-001")
    assert before is not None

    # A caller can calculate a syntactically forward value. That fact alone
    # must not constitute competent authority to advance the economic window.
    with pytest.raises(ValueError, match="authoritative"):
        set_usage_window_for_test("DAY-999")

    after = get_authority_snapshot("MANDATE-TREASURY-001")
    assert after is not None
    assert after.usage_window_id == before.usage_window_id
    assert after.authority_fence == before.authority_fence


def test_incompatible_authority_source_generations_cannot_form_one_sufficient_context():
    """IC-FAIL-004 failure-first: a version vector must not manufacture cross-source compatibility."""
    from app.engines.authority_evidence_adapters import (
        set_actor_source_version_for_test,
        set_operational_source_version_for_test,
    )
    from app.engines.authority_resolution import AuthorityResolutionError, resolve_payment_authority

    req = load_scenario(SCENARIO, rebase_to_now=False)

    # Simulate independently advanced authoritative sources. Each proposition
    # remains locally competent/current-looking, but no compatibility cut has
    # been established that authorises these generations to coexist.
    set_actor_source_version_for_test(req.actor_id, "ACTOR-GEN-200")
    set_operational_source_version_for_test(req.beneficiary, "OPERATION-GEN-900")

    with pytest.raises(AuthorityResolutionError, match="compatible"):
        resolve_payment_authority(req, resolved_at=req.requested_execution_time)


def test_explicitly_established_newer_source_generations_can_form_sufficient_context():
    """IC-FAIL-004 positive mirror: compatibility control must not become version-1-only permanent denial."""
    from app.engines.authority_evidence_adapters import (
        set_actor_source_version_for_test,
        set_operational_source_version_for_test,
    )
    from app.engines.institutional_authority import (
        register_authority_compatibility_cut_for_test,
        _COMPATIBILITY_CUT_REGISTRATION_CAPABILITY,
    )
    from app.engines.authority_resolution import resolve_payment_authority

    req = load_scenario(SCENARIO, rebase_to_now=False)
    actor_generation = "ACTOR-GEN-201"
    operational_generation = "OPERATION-GEN-901"

    set_actor_source_version_for_test(req.actor_id, actor_generation)
    set_operational_source_version_for_test(req.beneficiary, operational_generation)

    register_authority_compatibility_cut_for_test(
        actor_source_version=actor_generation,
        operational_source_version=operational_generation,
        registration_capability=_COMPATIBILITY_CUT_REGISTRATION_CAPABILITY,
    )

    semantics, evidence, graph, scope, context = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )

    assert context is not None
    assert context.compatibility_rule_id == "NORM-PAY-001:compatibility:v1"
    assert any(item.source_version == actor_generation for item in evidence)
    assert any(item.source_version == operational_generation for item in evidence)


def test_request_presented_target_cannot_define_effective_authority_scope():
    """IC-FAIL-003 failure-first: proposal target is not independent authority evidence."""
    from dataclasses import replace
    from app.engines.authority_resolution import AuthorityResolutionError, resolve_payment_authority

    req = load_scenario(SCENARIO, rebase_to_now=False)
    forged = replace(req, target="ATTACKER-CONTROLLED-TARGET")

    # The request may propose a target, but that value must not become the
    # effective authority scope unless independently grounded by authoritative
    # semantics/evidence.
    with pytest.raises(AuthorityResolutionError, match="target|scope|authoritative"):
        resolve_payment_authority(forged, resolved_at=forged.requested_execution_time)

def test_caller_cannot_self_register_forged_rai_binding_to_form_protected_consequence():
    """Failure-first route-closure: registry write access is not authority provenance.

    A caller able to reach low-level reference helpers must not be able to turn
    a separately minted permit into an RAI capability merely by inserting a
    matching registry record. The mandatory RAI chain must remain causal.
    """
    from app.engines.authority_store import get_authority_state_version
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.rai_execution_registry import register_rai_execution_binding

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    attempted_hash = action_binding_hash(_attempt(req))
    permit = issue_execution_permit(
        authority_receipt_id="SELF-REGISTERED-NON-RAI",
        action_binding_hash=attempted_hash,
        authority_state_version=get_authority_state_version(),
        authority_snapshot_id=snapshot.snapshot_id,
        authority_subject_principal_id=snapshot.mandate.principal_id,
        authority_subject_mandate_id=snapshot.mandate.mandate_id,
        authority_epoch_id=snapshot.authority_epoch_id,
        authority_fence_scope_key=snapshot.authority_fence_scope_key,
        authority_fence=snapshot.authority_fence,
        authoritative_source_id=snapshot.authoritative_source_id,
        source_competence_root_id=snapshot.source_competence_root_id,
        authority_semantics_version=snapshot.semantics.version,
        authority_semantics_definition_id=snapshot.semantics.definition_id,
        authority_semantics_source_id=snapshot.semantics.source_id,
        valid_until=(datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
        rai_determination_id=prepared.determination.determination_id,
        rai_constraint_id=prepared.constraint.constraint_id,
        rai_protected_operation_id=prepared.operation.operation_id,
        rai_authority_exercise_id=prepared.determination.authority_exercise_id,
        rai_execution_attempt_id=prepared.determination.execution_attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    # Deliberately simulate a wrapper/direct path that attempts to write the
    # same shape of registry record without traversing the successful final-bind
    # provenance path. The hardened registry must reject the write itself.
    with pytest.raises(
        ValueError,
        match="RAI execution binding registration requires successful final-bind provenance",
    ):
        register_rai_execution_binding(
            permit_signature=permit.signature,
            determination_id=prepared.determination.determination_id,
            constraint_id=prepared.constraint.constraint_id,
            protected_operation_id=prepared.operation.operation_id,
            authority_exercise_id=prepared.determination.authority_exercise_id,
            execution_attempt_id=prepared.determination.execution_attempt_id,
            action_binding_hash=attempted_hash,
            usage_reservation_id=prepared.usage_reservation_id,
            final_bind_provenance_id="SELF-REGISTERED-NON-CAUSAL-FINAL-BIND",
        )

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=attempted_hash,
    )
    assert outcome != "CONSEQUENCE_FORMED", (
        "ROUTE CLOSURE FAILURE: caller-created permit formed the protected "
        "consequence after forged RAI binding registration was rejected"
    )


def test_semantic_provenance_change_after_permit_mint_cannot_form_protected_consequence():
    """IC-FAIL-007 downstream hostile test: an S1 permit must die after S1 -> S2.

    The payment proposal and proposition values remain unchanged. Only the
    authoritative semantic definition/source provenance changes after successful
    final-bind and permit mint. Protected execution must not accept the stale
    semantic provenance carried by the otherwise valid signed permit.
    """
    from app.engines.institutional_authority import (
        advance_authority_semantics_source_for_test,
        restore_authority_semantics_for_test,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    )
    assert permit is not None

    attempted_hash = action_binding_hash(_attempt(req))
    previous = advance_authority_semantics_source_for_test()
    try:
        outcome = execute_protected_consequence(
            permit=permit,
            attempted_action_binding_hash=attempted_hash,
        )
        assert outcome != "CONSEQUENCE_FORMED", (
            "SEMANTIC PROVENANCE FAILURE: an execution capability derived and "
            "minted under S1 formed the protected consequence after the "
            "authoritative semantic definition/source changed to S2"
        )
        assert outcome in {
            "DENIED_AUTHORITY_STATE_STALE",
            "DENIED_AUTHORITY_SNAPSHOT_STALE",
            "DENIED_AUTHORITY_SEMANTICS_DEFINITION_MISMATCH",
            "DENIED_AUTHORITY_SEMANTICS_SOURCE_MISMATCH",
        }
    finally:
        restore_authority_semantics_for_test(previous)


def test_semantic_provenance_substitution_on_valid_rai_permit_cannot_form_protected_consequence():
    """IC-FAIL-007 hostile substitution: signed provenance cannot be rewritten.

    Start with a legitimately final-bound RAI execution permit. An attacker then
    substitutes semantic definition/source identifiers while preserving the
    permit's original signature and all other execution material. The protected
    boundary must reject the forged permit before consequence formation.
    """
    from dataclasses import replace

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    permit = mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    )
    assert permit is not None

    forged = replace(
        permit,
        authority_semantics_definition_id=permit.authority_semantics_definition_id + ":ATTACKER",
        authority_semantics_source_id=permit.authority_semantics_source_id + ":ATTACKER",
    )
    attempted_hash = action_binding_hash(_attempt(req))

    outcome = execute_protected_consequence(
        permit=forged,
        attempted_action_binding_hash=attempted_hash,
    )
    assert outcome == "DENIED_INVALID_EXECUTION_PERMIT", (
        "SEMANTIC PROVENANCE SUBSTITUTION FAILURE: attacker-rewritten semantic "
        "definition/source provenance survived permit integrity verification"
    )
