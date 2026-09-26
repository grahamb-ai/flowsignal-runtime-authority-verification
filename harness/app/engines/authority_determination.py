from __future__ import annotations

"""R2 Slice D — determination and authorised execution constraint issuance.

This module converts a resolved authority context into an exact protected
operation binding and a bounded execution constraint.  It does not commit the
operation and does not claim downstream consequence formation.
"""

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engines.authority_domain import (
    AuthorityOperationBinding,
    AuthorityResolutionContext,
    AuthorisedExecutionConstraint,
    EffectiveAuthorityScope,
    ProtectedOperation,
)
from app.engines.authority_lineage import (
    AuthorityExercise,
    ExecutionAttemptLineage,
    bind_attempt_to_operation,
    bind_exercise_to_institutional_operation,
)


_CONSTRAINT_KEY = os.environ.get(
    "FLOWSIGNAL_RAI_CONSTRAINT_KEY",
    "flowsignal-reference-r2-constraint-key",
).encode("utf-8")


@dataclass(frozen=True)
class AuthorityDetermination:
    determination_id: str
    resolution_context_id: str
    effective_authority_scope_id: str
    protected_operation_id: str
    authority_operation_binding_id: str
    authority_exercise_id: str
    execution_attempt_id: str
    decision: str
    reason_codes: tuple[str, ...]
    resolved_at: datetime
    valid_until: datetime
    integrity_material_id: str


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical(value):
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    return value


def _stable_id(prefix: str, payload: dict) -> str:
    raw = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()}"


def _constraint_integrity(payload: dict) -> str:
    raw = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hmac.new(_CONSTRAINT_KEY, raw, hashlib.sha256).hexdigest()


def materialise_protected_operation(
    req,
    *,
    route_id: str,
    executor_id: str,
    authority_exercise_id: str,
    execution_attempt_id: str,
) -> ProtectedOperation:
    payload = {
        "operation_class": "treasury.payment",
        "principal_id": req.principal_id,
        "actor_id": req.actor_id,
        "action": req.action,
        "target": req.target,
        "source_account": req.source_account,
        "beneficiary_id": req.beneficiary,
        "beneficiary_account": req.beneficiary_account_reference,
        "amount": req.amount,
        "currency": req.currency,
        "purpose": req.purpose,
        "mandate_id": req.mandate_id,
        "route_id": route_id,
        "executor_id": executor_id,
        "authority_exercise_id": authority_exercise_id,
        "execution_attempt_id": execution_attempt_id,
    }
    # Stable institutional identity deliberately excludes execution-attempt,
    # route and executor materialisation details. Those remain bound separately
    # by operation_id/materialization_id and the execution lineage.
    institutional_payload = {
        "operation_class": "treasury.payment",
        "principal_id": req.principal_id,
        "actor_id": req.actor_id,
        "action": req.action,
        "target": req.target,
        "source_account": req.source_account,
        "beneficiary_id": req.beneficiary,
        "beneficiary_account": req.beneficiary_account_reference,
        "amount": req.amount,
        "currency": req.currency,
        "purpose": req.purpose,
        "mandate_id": req.mandate_id,
    }
    # Institutional identity must originate at the institutional-act boundary,
    # not be inferred from content equality. The content-derived fallback is
    # retained only for older callers that have not yet supplied that identity.
    source_institutional_operation_id = getattr(req, "institutional_operation_id", None)
    institutional_operation_id = (
        _stable_id(
            "INST-OP",
            {
                "source_institutional_operation_id": source_institutional_operation_id,
                "principal_id": req.principal_id,
                "operation_class": "treasury.payment",
            },
        )
        if source_institutional_operation_id
        else _stable_id("INST-OP", institutional_payload)
    )
    # The concrete protected-operation identity must include the stable
    # institutional-act identity. Otherwise two distinct institutional acts with
    # identical payment content and the same execution lineage collapse to the
    # same operation/materialisation identity.
    concrete_payload = {
        **payload,
        "institutional_operation_id": institutional_operation_id,
    }
    operation_id = _stable_id("OP", concrete_payload)
    return ProtectedOperation(
        operation_id=operation_id,
        institutional_operation_id=institutional_operation_id,
        operation_class="treasury.payment",
        principal_id=req.principal_id,
        actor_id=req.actor_id,
        action=req.action,
        target=req.target,
        source_account=req.source_account,
        beneficiary_id=req.beneficiary,
        beneficiary_account=req.beneficiary_account_reference,
        amount=req.amount,
        currency=req.currency,
        purpose=req.purpose,
        mandate_id=req.mandate_id,
        route_id=route_id,
        executor_id=executor_id,
        parameter_envelope_id=None,
        materialization_id=_stable_id("MAT", concrete_payload),
    )


def bind_authority_to_operation(
    scope: EffectiveAuthorityScope,
    operation: ProtectedOperation,
) -> AuthorityOperationBinding:
    mismatches = []
    if scope.principal_id != operation.principal_id:
        mismatches.append("principal")
    if scope.authority_subject_id != operation.actor_id:
        mismatches.append("actor")
    if scope.action != operation.action:
        mismatches.append("action")
    if scope.target != operation.target:
        mismatches.append("target")
    if scope.mandate_id != operation.mandate_id:
        mismatches.append("mandate")
    if operation.amount is not None and scope.max_amount is not None and operation.amount > scope.max_amount:
        mismatches.append("amount")
    if scope.currency is not None and operation.currency != scope.currency:
        mismatches.append("currency")
    if operation.source_account not in scope.source_accounts:
        mismatches.append("source_account")
    if scope.beneficiary_scope_id is not None and operation.beneficiary_id != scope.beneficiary_scope_id:
        mismatches.append("beneficiary")
    if scope.purpose_scope_id is not None and operation.purpose != scope.purpose_scope_id:
        mismatches.append("purpose")
    if mismatches:
        raise ValueError("operation outside effective authority scope: " + ", ".join(mismatches))

    payload = {
        "scope_id": scope.scope_id,
        "operation_id": operation.operation_id,
        "route_id": operation.route_id,
        "executor_id": operation.executor_id,
        "materialization_id": operation.materialization_id,
    }
    return AuthorityOperationBinding(
        binding_id=_stable_id("BIND", payload),
        effective_authority_scope_id=scope.scope_id,
        protected_operation_id=operation.operation_id,
        parameter_binding_id=None,
        approval_binding_id=None,
        route_binding_id=_stable_id(
            "ROUTE",
            {"route_id": operation.route_id, "executor_id": operation.executor_id},
        ),
    )


def issue_authorised_execution_constraint(
    *,
    context: AuthorityResolutionContext,
    scope: EffectiveAuthorityScope,
    operation: ProtectedOperation,
    binding: AuthorityOperationBinding,
    resolved_at: datetime,
    authority_exercise: AuthorityExercise,
    execution_attempt: ExecutionAttemptLineage,
    lifetime_seconds: int = 60,
) -> tuple[AuthorityDetermination, AuthorisedExecutionConstraint]:
    if binding.effective_authority_scope_id != scope.scope_id:
        raise ValueError("binding does not reference effective authority scope")
    if binding.protected_operation_id != operation.operation_id:
        raise ValueError("binding does not reference protected operation")
    if context.derivation_graph_id != scope.derivation_graph_id:
        raise ValueError("resolution context and effective scope derivation mismatch")

    resolved = _aware(resolved_at)
    valid_until = resolved + timedelta(seconds=lifetime_seconds)
    exercise_id = authority_exercise.authority_exercise_id
    attempt_id = execution_attempt.execution_attempt_id
    if authority_exercise.resolution_context_id != context.context_id:
        raise ValueError("authority exercise belongs to different resolution context")
    if authority_exercise.effective_authority_scope_id != scope.scope_id:
        raise ValueError("authority exercise belongs to different effective scope")
    if execution_attempt.authority_exercise_id != exercise_id:
        raise ValueError("execution attempt belongs to different authority exercise")
    if execution_attempt.route_id != operation.route_id or execution_attempt.executor_id != operation.executor_id:
        raise ValueError("execution attempt route/executor does not match protected operation")
    bind_exercise_to_institutional_operation(
        authority_exercise_id=exercise_id,
        institutional_operation_id=operation.institutional_operation_id,
    )
    bind_attempt_to_operation(
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        protected_operation_id=operation.operation_id,
    )

    base = {
        "resolution_context_id": context.context_id,
        "effective_authority_scope_id": scope.scope_id,
        "protected_operation_id": operation.operation_id,
        "authority_operation_binding_id": binding.binding_id,
        "authority_exercise_id": exercise_id,
        "execution_attempt_id": attempt_id,
        "decision": "ALLOW",
        "resolved_at": resolved,
        "valid_until": valid_until,
    }
    determination_id = _stable_id("DET", base)
    integrity = _constraint_integrity({**base, "determination_id": determination_id})

    determination = AuthorityDetermination(
        determination_id=determination_id,
        resolution_context_id=context.context_id,
        effective_authority_scope_id=scope.scope_id,
        protected_operation_id=operation.operation_id,
        authority_operation_binding_id=binding.binding_id,
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        decision="ALLOW",
        reason_codes=("AUTHORITY_CONTEXT_COHERENT", "OPERATION_CORRESPONDENCE_ESTABLISHED"),
        resolved_at=resolved,
        valid_until=valid_until,
        integrity_material_id=integrity,
    )
    constraint = AuthorisedExecutionConstraint(
        constraint_id=_stable_id(
            "CONSTRAINT",
            {
                "determination_id": determination_id,
                "binding_id": binding.binding_id,
                "context_id": context.context_id,
                "exercise_id": exercise_id,
                "attempt_id": attempt_id,
                "valid_until": valid_until,
            },
        ),
        authority_operation_binding_id=binding.binding_id,
        resolution_context_id=context.context_id,
        authority_exercise_id=exercise_id,
        execution_attempt_id=attempt_id,
        valid_until=valid_until,
        integrity_material_id=integrity,
    )
    return determination, constraint
