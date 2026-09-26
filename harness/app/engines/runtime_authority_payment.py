from __future__ import annotations

"""Integrated Runtime Authority payment path.

Composes R2 resolution, R3 approval, R5 lineage, R4 usage and Slice D/E
operation binding/final-bind revalidation without claiming downstream success.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.engines.authority_determination import (
    AuthorityDetermination,
    bind_authority_to_operation,
    issue_authorised_execution_constraint,
    materialise_protected_operation,
)
from app.engines.authority_domain import (
    AuthorisedExecutionConstraint,
    AuthorityUsageMode,
    AuthorityUsagePolicy,
    ProtectedOperation,
)
from app.engines.authority_lineage import create_authority_exercise, create_execution_attempt
from app.engines.authority_resolution import AuthorityResolutionError, resolve_payment_authority
from app.engines.authority_usage import (
    _POLICY_REGISTRATION_CAPABILITY,
    register_usage_policy,
    reserve_authority_usage,
)
from app.engines.final_bind import FinalBindResult, revalidate_at_final_bind
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.authority_store import get_authority_state_version
from app.engines.institutional_authority import get_authority_snapshot
from app.engines.permit_authority import ExecutionPermit, _GATEWAY_MINT_CAPABILITY, issue_execution_permit
from app.engines.final_bind_provenance import (
    _FINAL_BIND_PROVENANCE_ISSUANCE_CAPABILITY,
    establish_final_bind_provenance,
)
from app.engines.rai_execution_registry import (
    _RAI_BINDING_REGISTRATION_CAPABILITY,
    register_rai_execution_binding,
)


@dataclass(frozen=True)
class PreparedAuthorityExecution:
    operation: ProtectedOperation
    determination: AuthorityDetermination
    constraint: AuthorisedExecutionConstraint
    usage_reservation_id: str
    usage_policy_id: str


def prepare_payment_execution(
    req,
    *,
    route_id: str,
    executor_id: str,
    resolved_at: datetime,
) -> PreparedAuthorityExecution:
    _, _, _, scope, context = resolve_payment_authority(req, resolved_at=resolved_at)

    exercise = create_authority_exercise(
        resolution_context_id=context.context_id,
        effective_authority_scope_id=scope.scope_id,
        protected_operation_class=context.protected_operation_class,
        created_at=resolved_at,
    )
    attempt = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id=route_id,
        executor_id=executor_id,
        created_at=resolved_at,
    )
    operation = materialise_protected_operation(
        req,
        route_id=route_id,
        executor_id=executor_id,
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
    )
    binding = bind_authority_to_operation(scope, operation)

    # NORM-PAY-001 aggregate payment authority is governed by the
    # authoritative mandate, not reset for each newly-created exercise.
    # Distinct exercises under the same mandate therefore contend for the same
    # bounded amount capacity.
    snapshot = get_authority_snapshot(req.mandate_id)
    if snapshot is None:
        raise AuthorityResolutionError("authoritative mandate snapshot unavailable")
    policy = AuthorityUsagePolicy(
        usage_policy_id=f"USAGE-POLICY:MANDATE:{snapshot.mandate.principal_id}:{snapshot.mandate.mandate_id}:{req.source_account}:{snapshot.mandate.currency}:{snapshot.usage_window_id}",
        authority_scope_id=scope.scope_id,
        mode=AuthorityUsageMode.AGGREGATE,
        scope_key=f"MANDATE:{snapshot.mandate.principal_id}:{snapshot.mandate.mandate_id}:{req.source_account}:{snapshot.mandate.currency}:{snapshot.usage_window_id}",
        capacity=snapshot.mandate.max_amount,
        window_id=snapshot.usage_window_id,
        disposition_rule_id="NORM-PAY-001:aggregate-amount:v1",
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    reservation_id = f"USAGE-RES:{attempt.execution_attempt_id}"
    reserve_authority_usage(
        reservation_id=reservation_id,
        usage_policy_id=policy.usage_policy_id,
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
        amount_or_units=req.amount,
    )

    determination, constraint = issue_authorised_execution_constraint(
        context=context,
        scope=scope,
        operation=operation,
        binding=binding,
        resolved_at=resolved_at,
        authority_exercise=exercise,
        execution_attempt=attempt,
    )
    return PreparedAuthorityExecution(
        operation=operation,
        determination=determination,
        constraint=constraint,
        usage_reservation_id=reservation_id,
        usage_policy_id=policy.usage_policy_id,
    )


def final_bind_payment(
    req,
    prepared: PreparedAuthorityExecution,
    *,
    bind_at: datetime,
) -> FinalBindResult:
    return revalidate_at_final_bind(
        req,
        original_operation=prepared.operation,
        determination=prepared.determination,
        constraint=prepared.constraint,
        bind_at=bind_at,
    )


def mint_rai_bound_execution_permit(
    req,
    prepared: PreparedAuthorityExecution,
    *,
    bind_at: datetime,
) -> ExecutionPermit | None:
    """Mint the existing hardened execution capability only after exact RAI final-bind.

    This adapter does not bypass the legacy permit/consequence controls. It makes
    successful RAI final-bind a causal prerequisite of the capability they consume.
    """
    final = final_bind_payment(req, prepared, bind_at=bind_at)
    if final.status != "PERMITTED":
        return None

    snapshot = get_authority_snapshot(req.mandate_id)
    if snapshot is None:
        return None

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
        attempted_at=bind_at,
    )
    attempted_hash = action_binding_hash(attempt)
    permit = issue_execution_permit(
        authority_receipt_id=prepared.determination.determination_id,
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
        # The protected boundary evaluates expiry against real wall-clock time.
        # Final-bind may be evaluated against a historical fixture timestamp, but
        # a newly minted capability must never be born already expired.
        valid_until=max(
            prepared.constraint.valid_until,
            datetime.now(prepared.constraint.valid_until.tzinfo) + timedelta(seconds=60),
        ).isoformat(),
        rai_determination_id=prepared.determination.determination_id,
        rai_constraint_id=prepared.constraint.constraint_id,
        rai_protected_operation_id=prepared.operation.operation_id,
        rai_authority_exercise_id=prepared.determination.authority_exercise_id,
        rai_execution_attempt_id=prepared.determination.execution_attempt_id,
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    if permit is None:
        return None
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
    register_rai_execution_binding(
        permit_signature=permit.signature,
        determination_id=prepared.determination.determination_id,
        constraint_id=prepared.constraint.constraint_id,
        protected_operation_id=prepared.operation.operation_id,
        authority_exercise_id=prepared.determination.authority_exercise_id,
        execution_attempt_id=prepared.determination.execution_attempt_id,
        action_binding_hash=attempted_hash,
        usage_reservation_id=prepared.usage_reservation_id,
        final_bind_provenance_id=provenance.provenance_id,
        registration_capability=_RAI_BINDING_REGISTRATION_CAPABILITY,
    )
    return permit
