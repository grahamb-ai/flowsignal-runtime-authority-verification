from __future__ import annotations

"""R2 Slice E — final-bind revalidation.

Re-resolves current authority immediately before authority-relevant commitment
and requires correspondence with the previously authorised operation and
constraint.  This module decides whether the constraint remains admissible; it
does not form or assert downstream consequence.
"""

import hmac
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4
from datetime import datetime, timezone

from app.engines.authority_determination import (
    AuthorityDetermination,
    _constraint_integrity,
    bind_authority_to_operation,
    materialise_protected_operation,
)
from app.engines.authority_domain import AuthorisedExecutionConstraint, ProtectedOperation
from app.engines.authority_resolution import AuthorityResolutionError, resolve_payment_authority
from app.engines.authority_lineage import verify_lineage


@dataclass(frozen=True)
class FinalBindResult:
    status: str
    reason_code: str
    current_resolution_context_id: str | None
    expected_resolution_context_id: str
    protected_operation_id: str
    authority_exercise_id: str
    execution_attempt_id: str
    causal_grant_id: str | None = None


_CAUSAL_GRANT_LOCK = RLock()
_CAUSAL_GRANTS: dict[str, tuple[str, str, str, str, str, str]] = {}


def consume_final_bind_causal_grant(
    grant_id: str | None,
    *,
    determination_id: str,
    constraint_id: str,
    protected_operation_id: str,
    authority_exercise_id: str,
    execution_attempt_id: str,
) -> bool:
    """Consume a one-shot grant emitted only by successful final-bind."""
    if grant_id is None:
        return False
    claimed = (
        determination_id,
        constraint_id,
        protected_operation_id,
        authority_exercise_id,
        execution_attempt_id,
        "FINAL_BIND_AUTHORITY_REVALIDATED",
    )
    with _CAUSAL_GRANT_LOCK:
        expected = _CAUSAL_GRANTS.get(grant_id)
        if expected != claimed:
            return False
        del _CAUSAL_GRANTS[grant_id]
        return True


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _expected_integrity(determination: AuthorityDetermination) -> str:
    return _constraint_integrity({
        "resolution_context_id": determination.resolution_context_id,
        "effective_authority_scope_id": determination.effective_authority_scope_id,
        "protected_operation_id": determination.protected_operation_id,
        "authority_operation_binding_id": determination.authority_operation_binding_id,
        "authority_exercise_id": determination.authority_exercise_id,
        "execution_attempt_id": determination.execution_attempt_id,
        "decision": determination.decision,
        "resolved_at": determination.resolved_at,
        "valid_until": determination.valid_until,
        "determination_id": determination.determination_id,
    })


def revalidate_at_final_bind(
    req,
    *,
    original_operation: ProtectedOperation,
    determination: AuthorityDetermination,
    constraint: AuthorisedExecutionConstraint,
    bind_at: datetime,
) -> FinalBindResult:
    bind_time = _aware(bind_at)

    def blocked(reason: str, current_context_id: str | None = None) -> FinalBindResult:
        return FinalBindResult(
            status="BLOCKED",
            reason_code=reason,
            current_resolution_context_id=current_context_id,
            expected_resolution_context_id=determination.resolution_context_id,
            protected_operation_id=original_operation.operation_id,
            authority_exercise_id=determination.authority_exercise_id,
            execution_attempt_id=determination.execution_attempt_id,
        )

    if determination.decision != "ALLOW":
        return blocked("NO_APPLICABLE_ALLOW")
    if bind_time > _aware(determination.valid_until):
        return blocked("AUTHORITY_DETERMINATION_EXPIRED")
    if constraint.valid_until is None or bind_time > _aware(constraint.valid_until):
        return blocked("AUTHORISED_EXECUTION_CONSTRAINT_EXPIRED")

    expected_integrity = _expected_integrity(determination)
    if not hmac.compare_digest(expected_integrity, determination.integrity_material_id):
        return blocked("AUTHORITY_DETERMINATION_INTEGRITY_INVALID")
    if not hmac.compare_digest(expected_integrity, constraint.integrity_material_id):
        return blocked("AUTHORISED_EXECUTION_CONSTRAINT_INTEGRITY_INVALID")

    if constraint.resolution_context_id != determination.resolution_context_id:
        return blocked("CONSTRAINT_CONTEXT_MISMATCH")
    if constraint.authority_operation_binding_id != determination.authority_operation_binding_id:
        return blocked("CONSTRAINT_OPERATION_BINDING_MISMATCH")
    if constraint.authority_exercise_id != determination.authority_exercise_id:
        return blocked("AUTHORITY_EXERCISE_MISMATCH")
    if constraint.execution_attempt_id != determination.execution_attempt_id:
        return blocked("EXECUTION_ATTEMPT_MISMATCH")
    if determination.protected_operation_id != original_operation.operation_id:
        return blocked("PROTECTED_OPERATION_IDENTITY_MISMATCH")

    # Validate the stored operation object's route/executor correspondence
    # independently of the current request. The full operation_id is already
    # bound by the determination above; route/executor are additionally bound
    # into lineage and must not be mutable while retaining that identity.
    from app.engines.authority_lineage import get_execution_attempt
    stored_attempt = get_execution_attempt(determination.execution_attempt_id)
    if (
        stored_attempt is None
        or stored_attempt.route_id != (original_operation.route_id or "")
        or stored_attempt.executor_id != (original_operation.executor_id or "")
    ):
        return blocked("PROTECTED_OPERATION_IDENTITY_MISMATCH")

    if not verify_lineage(
        authority_exercise_id=determination.authority_exercise_id,
        execution_attempt_id=determination.execution_attempt_id,
        protected_operation_id=original_operation.operation_id,
        resolution_context_id=determination.resolution_context_id,
        effective_authority_scope_id=determination.effective_authority_scope_id,
        route_id=original_operation.route_id or "",
        executor_id=original_operation.executor_id or "",
    ):
        return blocked("AUTHORITY_LINEAGE_INVALID")

    # Re-materialise the operation from the bind-time proposal.  Route/executor
    # are taken from the original authorised operation; changing either requires
    # a different operation and therefore a new determination.
    current_operation = materialise_protected_operation(
        req,
        route_id=original_operation.route_id or "",
        executor_id=original_operation.executor_id or "",
        authority_exercise_id=determination.authority_exercise_id,
        execution_attempt_id=determination.execution_attempt_id,
    )
    if current_operation.operation_id != original_operation.operation_id:
        return blocked("PROTECTED_OPERATION_CHANGED")

    try:
        _, _, _, current_scope, current_context = resolve_payment_authority(
            req, resolved_at=bind_time
        )
    except AuthorityResolutionError:
        return blocked("CURRENT_AUTHORITY_NOT_ESTABLISHED")

    current_context_id = current_context.context_id
    if current_context.context_id != determination.resolution_context_id:
        return blocked("AUTHORITY_CONTEXT_CHANGED", current_context_id)

    try:
        current_binding = bind_authority_to_operation(current_scope, current_operation)
    except ValueError:
        return blocked("CURRENT_OPERATION_OUTSIDE_AUTHORITY", current_context_id)

    if current_binding.binding_id != determination.authority_operation_binding_id:
        return blocked("AUTHORITY_OPERATION_CORRESPONDENCE_CHANGED", current_context_id)

    grant_id = f"FBG:{uuid4()}"
    with _CAUSAL_GRANT_LOCK:
        _CAUSAL_GRANTS[grant_id] = (
            determination.determination_id,
            constraint.constraint_id,
            original_operation.operation_id,
            determination.authority_exercise_id,
            determination.execution_attempt_id,
            "FINAL_BIND_AUTHORITY_REVALIDATED",
        )

    return FinalBindResult(
        status="PERMITTED",
        reason_code="FINAL_BIND_AUTHORITY_REVALIDATED",
        current_resolution_context_id=current_context_id,
        expected_resolution_context_id=determination.resolution_context_id,
        protected_operation_id=original_operation.operation_id,
        authority_exercise_id=determination.authority_exercise_id,
        execution_attempt_id=determination.execution_attempt_id,
        causal_grant_id=grant_id,
    )
