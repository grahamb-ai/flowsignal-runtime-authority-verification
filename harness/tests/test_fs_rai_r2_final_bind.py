from dataclasses import replace
from pathlib import Path

from app.engines.authority_determination import (
    bind_authority_to_operation,
    issue_authorised_execution_constraint,
    materialise_protected_operation,
)
from app.engines.authority_resolution import resolve_payment_authority
from app.engines.authority_lineage import create_authority_exercise, create_execution_attempt
from app.engines.final_bind import revalidate_at_final_bind
from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def _authorised_chain():
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

    operation = materialise_protected_operation(
            req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
    )
    binding = bind_authority_to_operation(scope, operation)
    determination, constraint = issue_authorised_execution_constraint(
        context=context,
        scope=scope,
        operation=operation,
        binding=binding,
        resolved_at=req.requested_execution_time,
        authority_exercise=exercise,
        execution_attempt=attempt,
    )
    return req, operation, determination, constraint


def test_slice_e_permits_unchanged_current_authority_and_operation():
    req, operation, determination, constraint = _authorised_chain()
    result = revalidate_at_final_bind(
        req,
        original_operation=operation,
        determination=determination,
        constraint=constraint,
        bind_at=req.requested_execution_time,
    )
    assert result.status == "PERMITTED"
    assert result.reason_code == "FINAL_BIND_AUTHORITY_REVALIDATED"


def test_authority_cut_change_blocks_at_final_bind():
    req, operation, determination, constraint = _authorised_chain()
    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        ),
    )
    result = revalidate_at_final_bind(
        req,
        original_operation=operation,
        determination=determination,
        constraint=constraint,
        bind_at=req.requested_execution_time,
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "AUTHORITY_CONTEXT_CHANGED"


def test_operation_change_after_determination_blocks():
    req, operation, determination, constraint = _authorised_chain()
    req.amount = req.amount + 1
    result = revalidate_at_final_bind(
        req,
        original_operation=operation,
        determination=determination,
        constraint=constraint,
        bind_at=req.requested_execution_time,
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "PROTECTED_OPERATION_CHANGED"


def test_attempt_substitution_blocks():
    req, operation, determination, constraint = _authorised_chain()
    substituted = replace(constraint, execution_attempt_id="ATT-ATTACKER")
    result = revalidate_at_final_bind(
        req,
        original_operation=operation,
        determination=determination,
        constraint=substituted,
        bind_at=req.requested_execution_time,
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "EXECUTION_ATTEMPT_MISMATCH"


def test_tampered_constraint_integrity_blocks():
    req, operation, determination, constraint = _authorised_chain()
    tampered = replace(constraint, integrity_material_id="00" * 32)
    result = revalidate_at_final_bind(
        req,
        original_operation=operation,
        determination=determination,
        constraint=tampered,
        bind_at=req.requested_execution_time,
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "AUTHORISED_EXECUTION_CONSTRAINT_INTEGRITY_INVALID"


def test_route_substitution_is_a_different_operation():
    req, operation, determination, constraint = _authorised_chain()
    substituted_operation = replace(operation, route_id="R2")
    result = revalidate_at_final_bind(
        req,
        original_operation=substituted_operation,
        determination=determination,
        constraint=constraint,
        bind_at=req.requested_execution_time,
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "PROTECTED_OPERATION_IDENTITY_MISMATCH"


def test_r6_caller_cannot_self_register_forged_rai_binding_to_form_protected_consequence():
    """R6 failure-first route closure: registry write reachability is not RAI provenance.

    A caller reaching low-level reference helpers must not be able to mint a
    separately constructed permit, self-register matching RAI-looking fields,
    and thereby make the directly callable protected executor form the protected
    consequence without the successful integrated final-bind/mint chain.
    """
    from datetime import datetime, timedelta, timezone

    from app.engines.authority_store import get_authority_state_version
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import register_rai_execution_binding

    req = load_scenario(SCENARIO, rebase_to_now=False)
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )

    permit = issue_execution_permit(
        authority_receipt_id="FORGED-R6-RECEIPT",
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
        valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        rai_determination_id="FORGED-R6-DETERMINATION",
        rai_constraint_id="FORGED-R6-CONSTRAINT",
        rai_protected_operation_id="FORGED-R6-OPERATION",
        rai_authority_exercise_id="FORGED-R6-EXERCISE",
        rai_execution_attempt_id="FORGED-R6-ATTEMPT",
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    # Public helper reachability must not be sufficient to manufacture the
    # causal RAI provenance required by the executor.
    try:
        register_rai_execution_binding(
            permit_signature=permit.signature,
            determination_id=permit.rai_determination_id,
            constraint_id=permit.rai_constraint_id,
            protected_operation_id=permit.rai_protected_operation_id,
            authority_exercise_id=permit.rai_authority_exercise_id,
            execution_attempt_id=permit.rai_execution_attempt_id,
            action_binding_hash=attempted_hash,
            usage_reservation_id="FORGED-R6-USAGE",
            final_bind_provenance_id="FORGED-R6-FINAL-BIND-PROVENANCE",
        )
    except ValueError:
        pass

    result = execute_protected_consequence(permit, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 route closure failure: low-level mint + self-registration formed "
        "the protected consequence without successful RAI final-bind provenance"
    )
    assert result == "DENIED_RAI_EXECUTION_BINDING_REQUIRED"


def test_r6_possession_of_registry_capability_cannot_manufacture_rai_provenance():
    """R6 second-order attack: registry capability possession is not causal provenance.

    Even a caller that can reach both low-level reference capabilities must not
    turn attacker-chosen RAI identifiers into execution authority merely by
    minting a permit and inserting a matching registry row.
    """
    from datetime import datetime, timedelta, timezone

    from app.engines.authority_store import get_authority_state_version
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import (
        _RAI_BINDING_REGISTRATION_CAPABILITY,
        register_rai_execution_binding,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )

    permit = issue_execution_permit(
        authority_receipt_id="FORGED-R6-CAP-RECEIPT",
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
        valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        rai_determination_id="FORGED-R6-CAP-DETERMINATION",
        rai_constraint_id="FORGED-R6-CAP-CONSTRAINT",
        rai_protected_operation_id="FORGED-R6-CAP-OPERATION",
        rai_authority_exercise_id="FORGED-R6-CAP-EXERCISE",
        rai_execution_attempt_id="FORGED-R6-CAP-ATTEMPT",
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    register_rai_execution_binding(
        permit_signature=permit.signature,
        determination_id=permit.rai_determination_id,
        constraint_id=permit.rai_constraint_id,
        protected_operation_id=permit.rai_protected_operation_id,
        authority_exercise_id=permit.rai_authority_exercise_id,
        execution_attempt_id=permit.rai_execution_attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id="FORGED-R6-CAP-USAGE",
        final_bind_provenance_id="FORGED-R6-CAP-FINAL-BIND-PROVENANCE",
        registration_capability=_RAI_BINDING_REGISTRATION_CAPABILITY,
    )

    result = execute_protected_consequence(permit, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 route closure failure: possession of low-level mint and registry "
        "capabilities manufactured executable RAI provenance"
    )


def test_r6_low_level_capabilities_plus_forged_usage_cannot_form_consequence():
    """R6 third-order attack: writable usage state must not complete forged provenance.

    The attacker is given the reference mint, RAI-registration and usage-policy
    registration capabilities, then constructs a matching RESERVED usage record.
    Protected commitment must still require a causally established RAI chain.
    """
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from app.engines.authority_domain import AuthorityUsageMode, AuthorityUsagePolicy
    from app.engines.authority_store import get_authority_state_version
    from app.engines.authority_usage import (
        _POLICY_REGISTRATION_CAPABILITY,
        register_usage_policy,
        reserve_authority_usage,
    )
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import (
        _RAI_BINDING_REGISTRATION_CAPABILITY,
        register_rai_execution_binding,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
            actor_id=req.actor_id, principal_id=req.principal_id, action=req.action,
            target=req.target, amount=req.amount, currency=req.currency,
            source_account=req.source_account, beneficiary=req.beneficiary,
            beneficiary_account_reference=req.beneficiary_account_reference,
            purpose=req.purpose, mandate_id=req.mandate_id,
            attempted_at=datetime.now(timezone.utc),
        )
    )

    exercise_id = "FORGED-R6-USAGE-EXERCISE"
    attempt_id = "FORGED-R6-USAGE-ATTEMPT"
    reservation_id = "FORGED-R6-USAGE-RESERVATION"
    policy_id = "FORGED-R6-USAGE-POLICY"

    register_usage_policy(
        AuthorityUsagePolicy(
            usage_policy_id=policy_id,
            authority_scope_id="FORGED-R6-SCOPE",
            mode=AuthorityUsageMode.AGGREGATE,
            scope_key="FORGED-R6-USAGE-SCOPE",
            capacity=Decimal("1000000"),
            window_id=snapshot.usage_window_id,
            disposition_rule_id="FORGED-R6-RULE",
        ),
        registration_capability=_POLICY_REGISTRATION_CAPABILITY,
    )
    reserve_authority_usage(
        reservation_id=reservation_id,
        usage_policy_id=policy_id,
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        amount_or_units=req.amount,
    )

    permit = issue_execution_permit(
        authority_receipt_id="FORGED-R6-USAGE-RECEIPT",
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
        valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        rai_determination_id="FORGED-R6-USAGE-DETERMINATION",
        rai_constraint_id="FORGED-R6-USAGE-CONSTRAINT",
        rai_protected_operation_id="FORGED-R6-USAGE-OPERATION",
        rai_authority_exercise_id=exercise_id,
        rai_execution_attempt_id=attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    register_rai_execution_binding(
        permit_signature=permit.signature,
        determination_id=permit.rai_determination_id,
        constraint_id=permit.rai_constraint_id,
        protected_operation_id=permit.rai_protected_operation_id,
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id=reservation_id,
        final_bind_provenance_id="FORGED-R6-FINAL-BIND-PROVENANCE",
        registration_capability=_RAI_BINDING_REGISTRATION_CAPABILITY,
    )

    result = execute_protected_consequence(permit, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 route closure failure: low-level capabilities plus caller-manufactured "
        "usage state formed the protected consequence without causal RAI final-bind"
    )
    assert result == "DENIED_FINAL_BIND_PROVENANCE_REQUIRED"


def test_r6_valid_final_bind_provenance_cannot_be_reused_for_a_second_permit_signature():
    """R6 fourth-order failure-first: valid provenance must not be transferable to a second permit.

    Start with a genuinely successful integrated final-bind/mint chain. A caller
    that can reach the low-level mint and registry capabilities then mints a
    second, separately signed permit carrying the same legitimate RAI lineage
    and registers it against the first permit's genuine final-bind provenance.
    Protected commitment must not treat provenance established for one mint as
    reusable authority for another permit signature.
    """
    from datetime import datetime, timedelta, timezone

    from app.engines.authority_store import get_authority_state_version
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import (
        _RAI_BINDING_REGISTRATION_CAPABILITY,
        get_rai_execution_binding,
        register_rai_execution_binding,
    )
    from app.engines.runtime_authority_payment import (
        mint_rai_bound_execution_permit,
        prepare_payment_execution,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    original_permit = mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    )
    assert original_permit is not None

    original_binding = get_rai_execution_binding(original_permit.signature)
    assert original_binding is not None

    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None
    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )
    assert attempted_hash == original_binding.action_binding_hash

    transplanted_permit = issue_execution_permit(
        authority_receipt_id="R6-TRANSPLANTED-PROVENANCE-SECOND-MINT",
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
        valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        rai_determination_id=original_binding.determination_id,
        rai_constraint_id=original_binding.constraint_id,
        rai_protected_operation_id=original_binding.protected_operation_id,
        rai_authority_exercise_id=original_binding.authority_exercise_id,
        rai_execution_attempt_id=original_binding.execution_attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert transplanted_permit is not None
    assert transplanted_permit.signature != original_permit.signature

    register_rai_execution_binding(
        permit_signature=transplanted_permit.signature,
        determination_id=original_binding.determination_id,
        constraint_id=original_binding.constraint_id,
        protected_operation_id=original_binding.protected_operation_id,
        authority_exercise_id=original_binding.authority_exercise_id,
        execution_attempt_id=original_binding.execution_attempt_id,
        action_binding_hash=original_binding.action_binding_hash,
        usage_reservation_id=original_binding.usage_reservation_id,
        final_bind_provenance_id=original_binding.final_bind_provenance_id,
        registration_capability=_RAI_BINDING_REGISTRATION_CAPABILITY,
    )

    result = execute_protected_consequence(transplanted_permit, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 provenance transfer failure: one genuine successful final-bind "
        "provenance authorised a separately minted permit signature"
    )


def test_r6_valid_final_bind_provenance_cannot_be_transplanted_to_second_chain():
    """R6 next-order: genuine final-bind provenance is chain-specific, not bearer authority.

    Establish two independently prepared chains for the same proposed payment.
    Mint chain B only after replacing the provenance-establishment seam so its
    otherwise legitimate registry row receives chain A's genuine provenance ID.
    Protected commitment must reject that cross-chain provenance mismatch.
    """
    from dataclasses import replace
    from decimal import Decimal
    from datetime import datetime, timezone

    import app.engines.runtime_authority_payment as runtime_authority_payment
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.final_bind_provenance import verify_final_bind_provenance
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import get_rai_execution_binding
    from app.engines.runtime_authority_payment import prepare_payment_execution

    req = replace(
        load_scenario(SCENARIO, rebase_to_now=False),
        amount=Decimal("100000.00"),
        institutional_operation_id="R6-PROVENANCE-TRANSPLANT",
    )

    prepared_a = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    prepared_b = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )

    # Establish chain A provenance through the genuine successful final-bind path.
    permit_a = runtime_authority_payment.mint_rai_bound_execution_permit(
        req, prepared_a, bind_at=req.requested_execution_time,
    )
    assert permit_a is not None
    binding_a = get_rai_execution_binding(permit_a.signature)
    assert binding_a is not None
    assert verify_final_bind_provenance(
        binding_a.final_bind_provenance_id,
        determination_id=binding_a.determination_id,
        constraint_id=binding_a.constraint_id,
        protected_operation_id=binding_a.protected_operation_id,
        authority_exercise_id=binding_a.authority_exercise_id,
        execution_attempt_id=binding_a.execution_attempt_id,
        action_binding_hash=binding_a.action_binding_hash,
        usage_reservation_id=binding_a.usage_reservation_id,
        permit_signature=permit_a.signature,
    )

    original_establish = runtime_authority_payment.establish_final_bind_provenance

    def transplant_provenance(**kwargs):
        from app.engines.final_bind_provenance import _PROVENANCE
        return _PROVENANCE[binding_a.final_bind_provenance_id]

    runtime_authority_payment.establish_final_bind_provenance = transplant_provenance
    try:
        permit_b = runtime_authority_payment.mint_rai_bound_execution_permit(
            req, prepared_b, bind_at=req.requested_execution_time,
        )
    finally:
        runtime_authority_payment.establish_final_bind_provenance = original_establish

    assert permit_b is not None

    result = execute_protected_consequence(permit_b, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 provenance transplant failure: genuine final-bind provenance from "
        "one chain authorised protected commitment on a different chain"
    )
    assert result == "DENIED_FINAL_BIND_PROVENANCE_REQUIRED"



def test_r6_all_low_level_capabilities_cannot_substitute_for_successful_final_bind():
    """R6 next-order failure-first: capability possession must not equal causal final-bind.

    Exercise the strongest in-process misuse case: mint, usage-policy registration,
    RAI registration and provenance-issuance capabilities are all reachable. A
    caller constructs mutually matching state without traversing the integrated
    final-bind path. Protected commitment must still require causal final-bind.
    """
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from app.engines.authority_domain import AuthorityUsageMode, AuthorityUsagePolicy
    from app.engines.authority_store import get_authority_state_version
    from app.engines.authority_usage import (
        _POLICY_REGISTRATION_CAPABILITY,
        register_usage_policy,
        reserve_authority_usage,
    )
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.final_bind_provenance import (
        _FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        establish_final_bind_provenance,
    )
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import (
        _RAI_BINDING_REGISTRATION_CAPABILITY,
        register_rai_execution_binding,
    )

    req = load_scenario(SCENARIO, rebase_to_now=False)
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )

    exercise_id = "R6-ALL-CAPS-EXERCISE"
    attempt_id = "R6-ALL-CAPS-ATTEMPT"
    reservation_id = "R6-ALL-CAPS-RESERVATION"
    policy_id = "R6-ALL-CAPS-POLICY"

    register_usage_policy(
        AuthorityUsagePolicy(
            usage_policy_id=policy_id,
            authority_scope_id="R6-ALL-CAPS-SCOPE",
            mode=AuthorityUsageMode.AGGREGATE,
            scope_key="R6-ALL-CAPS-SCOPE",
            capacity=Decimal("1000000"),
            window_id=snapshot.usage_window_id,
            disposition_rule_id="R6-ALL-CAPS-RULE",
        ),
        registration_capability=_POLICY_REGISTRATION_CAPABILITY,
    )
    reserve_authority_usage(
        reservation_id=reservation_id,
        usage_policy_id=policy_id,
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        amount_or_units=req.amount,
    )

    permit = issue_execution_permit(
        authority_receipt_id="R6-ALL-CAPS-RECEIPT",
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
        valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        rai_determination_id="R6-ALL-CAPS-DETERMINATION",
        rai_constraint_id="R6-ALL-CAPS-CONSTRAINT",
        rai_protected_operation_id="R6-ALL-CAPS-OPERATION",
        rai_authority_exercise_id=exercise_id,
        rai_execution_attempt_id=attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    try:
        provenance = establish_final_bind_provenance(
            determination_id=permit.rai_determination_id,
            constraint_id=permit.rai_constraint_id,
            protected_operation_id=permit.rai_protected_operation_id,
            authority_exercise_id=exercise_id,
            execution_attempt_id=attempt_id,
            action_binding_hash=attempted_hash,
            usage_reservation_id=reservation_id,
            permit_signature=permit.signature,
            issuance_capability=_FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        )
    except ValueError as exc:
        assert str(exc) == "successful causal final-bind grant required"
        return

    register_rai_execution_binding(
        permit_signature=permit.signature,
        determination_id=permit.rai_determination_id,
        constraint_id=permit.rai_constraint_id,
        protected_operation_id=permit.rai_protected_operation_id,
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id=reservation_id,
        final_bind_provenance_id=provenance.provenance_id,
        registration_capability=_RAI_BINDING_REGISTRATION_CAPABILITY,
    )

    result = execute_protected_consequence(permit, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 causal-boundary failure: possession of all low-level reference "
        "capabilities substituted for successful integrated final-bind"
    )


def test_r6_successful_final_bind_causal_grant_is_single_use():
    """R6 next seam: one successful final-bind must not authorise two provenance records.

    Obtain one genuine PERMITTED final-bind result, then consume its causal grant
    to establish provenance once. Reusing that exact grant for a second
    provenance establishment must fail.
    """
    from datetime import datetime, timezone

    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.final_bind_provenance import (
        _FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        establish_final_bind_provenance,
    )
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.authority_store import get_authority_state_version
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.runtime_authority_payment import (
        final_bind_payment,
        prepare_payment_execution,
    )

    from dataclasses import replace
    from decimal import Decimal

    from app.engines.authority_usage import reset_authority_usage_reference_state_for_test

    # This case exercises grant consumption, not aggregate-capacity interaction.
    # Isolate the process-local reference usage state so earlier R6 reservations
    # cannot prevent the case from reaching the intended boundary.
    reset_authority_usage_reference_state_for_test()

    req = replace(
        load_scenario(SCENARIO, rebase_to_now=False),
        amount=Decimal("100000.00"),
        institutional_operation_id="R6-CAUSAL-GRANT-SINGLE-USE",
    )
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED"
    assert final.causal_grant_id is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    def mint(label):
        return issue_execution_permit(
            authority_receipt_id=label,
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
            valid_until=prepared.constraint.valid_until.isoformat(),
            rai_determination_id=prepared.determination.determination_id,
            rai_constraint_id=prepared.constraint.constraint_id,
            rai_protected_operation_id=prepared.operation.operation_id,
            rai_authority_exercise_id=prepared.determination.authority_exercise_id,
            rai_execution_attempt_id=prepared.determination.execution_attempt_id,
            mint_capability=_GATEWAY_MINT_CAPABILITY,
        )

    first_permit = mint("R6-GRANT-SINGLE-USE-1")
    second_permit = mint("R6-GRANT-SINGLE-USE-2")
    assert first_permit is not None and second_permit is not None
    assert first_permit.signature != second_permit.signature

    establish_final_bind_provenance(
        determination_id=prepared.determination.determination_id,
        constraint_id=prepared.constraint.constraint_id,
        protected_operation_id=prepared.operation.operation_id,
        authority_exercise_id=prepared.determination.authority_exercise_id,
        execution_attempt_id=prepared.determination.execution_attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id=prepared.usage_reservation_id,
        permit_signature=first_permit.signature,
        causal_grant_id=final.causal_grant_id,
        issuance_capability=_FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
    )

    import pytest
    with pytest.raises(ValueError, match="successful causal final-bind grant required"):
        establish_final_bind_provenance(
            determination_id=prepared.determination.determination_id,
            constraint_id=prepared.constraint.constraint_id,
            protected_operation_id=prepared.operation.operation_id,
            authority_exercise_id=prepared.determination.authority_exercise_id,
            execution_attempt_id=prepared.determination.execution_attempt_id,
            action_binding_hash=attempted_hash,
            usage_reservation_id=prepared.usage_reservation_id,
            permit_signature=second_permit.signature,
            causal_grant_id=final.causal_grant_id,
            issuance_capability=_FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        )


def test_r6_genuine_causal_grant_cannot_authorise_substituted_determination_and_constraint():
    """R6 failure-first: causal grant must bind the exact final-bind decision artifacts.

    A genuine successful final-bind grant for one prepared chain must not be
    consumable to establish provenance carrying caller-substituted determination
    and constraint identifiers, even when operation/exercise/attempt remain the
    genuine final-bind values.
    """
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from app.engines.authority_store import get_authority_state_version
    from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.final_bind_provenance import (
        _FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        establish_final_bind_provenance,
    )
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.protected_consequence import execute_protected_consequence
    from app.engines.rai_execution_registry import (
        _RAI_BINDING_REGISTRATION_CAPABILITY,
        register_rai_execution_binding,
    )
    from app.engines.runtime_authority_payment import final_bind_payment, prepare_payment_execution

    reset_authority_usage_reference_state_for_test()
    req = replace(
        load_scenario(SCENARIO, rebase_to_now=False),
        amount=Decimal("100000.00"),
        institutional_operation_id="R6-CAUSAL-GRANT-DECISION-SUBSTITUTION",
    )
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED"
    assert final.causal_grant_id is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    substituted_determination = "R6-SUBSTITUTED-DETERMINATION"
    substituted_constraint = "R6-SUBSTITUTED-CONSTRAINT"
    permit = issue_execution_permit(
        authority_receipt_id="R6-DECISION-SUBSTITUTION",
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
        valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        rai_determination_id=substituted_determination,
        rai_constraint_id=substituted_constraint,
        rai_protected_operation_id=prepared.operation.operation_id,
        rai_authority_exercise_id=prepared.determination.authority_exercise_id,
        rai_execution_attempt_id=prepared.determination.execution_attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    try:
        provenance = establish_final_bind_provenance(
            determination_id=substituted_determination,
            constraint_id=substituted_constraint,
            protected_operation_id=prepared.operation.operation_id,
            authority_exercise_id=prepared.determination.authority_exercise_id,
            execution_attempt_id=prepared.determination.execution_attempt_id,
            action_binding_hash=attempted_hash,
            usage_reservation_id=prepared.usage_reservation_id,
            permit_signature=permit.signature,
            causal_grant_id=final.causal_grant_id,
            issuance_capability=_FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        )
    except ValueError as exc:
        assert str(exc) == "successful causal final-bind grant required"
        return

    register_rai_execution_binding(
        permit_signature=permit.signature,
        determination_id=substituted_determination,
        constraint_id=substituted_constraint,
        protected_operation_id=prepared.operation.operation_id,
        authority_exercise_id=prepared.determination.authority_exercise_id,
        execution_attempt_id=prepared.determination.execution_attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id=prepared.usage_reservation_id,
        final_bind_provenance_id=provenance.provenance_id,
        registration_capability=_RAI_BINDING_REGISTRATION_CAPABILITY,
    )

    result = execute_protected_consequence(permit, attempted_hash)
    assert result != "CONSEQUENCE_FORMED", (
        "R6 causal-grant correspondence failure: a genuine final-bind grant "
        "authorised substituted determination/constraint identifiers"
    )


def test_r6_wrong_causal_grant_correspondence_does_not_destroy_valid_grant():
    """R6 availability seam: a mismatched claim must not burn a genuine grant.

    One genuine successful final-bind grant is first presented with deliberately
    wrong decision correspondence. That presentation must fail, but the same grant
    must remain usable exactly once with its genuine final-bind correspondence.
    """
    from dataclasses import replace
    from datetime import datetime, timezone
    from decimal import Decimal

    import pytest

    from app.engines.authority_store import get_authority_state_version
    from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
    from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
    from app.engines.final_bind_provenance import (
        _FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        establish_final_bind_provenance,
    )
    from app.engines.institutional_authority import get_authority_snapshot
    from app.engines.permit_authority import _GATEWAY_MINT_CAPABILITY, issue_execution_permit
    from app.engines.runtime_authority_payment import final_bind_payment, prepare_payment_execution

    reset_authority_usage_reference_state_for_test()
    req = replace(
        load_scenario(SCENARIO, rebase_to_now=False),
        amount=Decimal("100000.00"),
        institutional_operation_id="R6-CAUSAL-GRANT-MISMATCH-PRESERVATION",
    )
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED"
    assert final.causal_grant_id is not None

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
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
            attempted_at=datetime.now(timezone.utc),
        )
    )
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None

    permit = issue_execution_permit(
        authority_receipt_id="R6-GRANT-MISMATCH-PRESERVATION",
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
        valid_until=prepared.constraint.valid_until.isoformat(),
        rai_determination_id=prepared.determination.determination_id,
        rai_constraint_id=prepared.constraint.constraint_id,
        rai_protected_operation_id=prepared.operation.operation_id,
        rai_authority_exercise_id=prepared.determination.authority_exercise_id,
        rai_execution_attempt_id=prepared.determination.execution_attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    assert permit is not None

    with pytest.raises(ValueError, match="successful causal final-bind grant required"):
        establish_final_bind_provenance(
            determination_id="R6-WRONG-DETERMINATION",
            constraint_id=prepared.constraint.constraint_id,
            protected_operation_id=prepared.operation.operation_id,
            authority_exercise_id=prepared.determination.authority_exercise_id,
            execution_attempt_id=prepared.determination.execution_attempt_id,
            action_binding_hash=attempted_hash,
            usage_reservation_id=prepared.usage_reservation_id,
            permit_signature=permit.signature,
            causal_grant_id=final.causal_grant_id,
            issuance_capability=_FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
        )

    provenance = establish_final_bind_provenance(
        determination_id=prepared.determination.determination_id,
        constraint_id=prepared.constraint.constraint_id,
        protected_operation_id=prepared.operation.operation_id,
        authority_exercise_id=prepared.determination.authority_exercise_id,
        execution_attempt_id=prepared.determination.execution_attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id=prepared.usage_reservation_id,
        permit_signature=permit.signature,
        causal_grant_id=final.causal_grant_id,
        issuance_capability=_FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
    )
    assert provenance.determination_id == prepared.determination.determination_id
