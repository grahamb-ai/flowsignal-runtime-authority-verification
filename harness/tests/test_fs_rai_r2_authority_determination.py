from pathlib import Path
from dataclasses import replace

import pytest

from app.engines.authority_determination import (
    bind_authority_to_operation,
    issue_authorised_execution_constraint,
    materialise_protected_operation,
)
from app.engines.authority_resolution import resolve_payment_authority
from app.engines.authority_lineage import create_authority_exercise, create_execution_attempt
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def _resolved():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    _, _, _, scope, context = resolve_payment_authority(
        req, resolved_at=req.requested_execution_time
    )
    return req, scope, context


def test_slice_d_binds_exact_operation_to_context_and_scope():
    req, scope, context = _resolved()
    exercise = create_authority_exercise(
            resolution_context_id=context.context_id,
            effective_authority_scope_id=scope.scope_id,
            protected_operation_class=context.protected_operation_class,
            created_at=req.requested_execution_time,
            authority_exercise_id="EX-001",
        )

    attempt = create_execution_attempt(
            authority_exercise_id=exercise.authority_exercise_id,
            route_id="R1",
            executor_id="PAYMENT-EXECUTOR-1",
            created_at=req.requested_execution_time,
            execution_attempt_id="ATT-001",
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

    assert determination.resolution_context_id == context.context_id
    assert determination.protected_operation_id == operation.operation_id
    assert determination.authority_operation_binding_id == binding.binding_id
    assert constraint.authority_operation_binding_id == binding.binding_id
    assert constraint.authority_exercise_id == "EX-001"
    assert constraint.execution_attempt_id == "ATT-001"


def test_route_change_changes_operation_and_binding_identity():
    req, scope, _ = _resolved()
    r1 = materialise_protected_operation(
        req, route_id="R1", executor_id="EXEC-1",
        authority_exercise_id="EX-1", execution_attempt_id="ATT-1"
    )
    r2 = materialise_protected_operation(
        req, route_id="R2", executor_id="EXEC-1",
        authority_exercise_id="EX-1", execution_attempt_id="ATT-1"
    )
    b1 = bind_authority_to_operation(scope, r1)
    b2 = bind_authority_to_operation(scope, r2)
    assert r1.operation_id != r2.operation_id
    assert b1.binding_id != b2.binding_id
    assert b1.route_binding_id != b2.route_binding_id


def test_executor_change_changes_operation_and_route_binding():
    req, scope, _ = _resolved()
    a = materialise_protected_operation(
        req, route_id="R1", executor_id="EXEC-A",
        authority_exercise_id="EX-1", execution_attempt_id="ATT-1"
    )
    b = materialise_protected_operation(
        req, route_id="R1", executor_id="EXEC-B",
        authority_exercise_id="EX-1", execution_attempt_id="ATT-1"
    )
    assert a.operation_id != b.operation_id
    assert bind_authority_to_operation(scope, a).route_binding_id != (
        bind_authority_to_operation(scope, b).route_binding_id
    )


def test_amount_substitution_outside_scope_is_rejected():
    req, scope, _ = _resolved()
    req.amount = scope.max_amount + 1
    operation = materialise_protected_operation(
        req, route_id="R1", executor_id="EXEC-1",
        authority_exercise_id="EX-1", execution_attempt_id="ATT-1"
    )
    with pytest.raises(ValueError, match="amount"):
        bind_authority_to_operation(scope, operation)


def test_scope_from_one_context_cannot_be_silently_rebound_to_other_derivation():
    req, scope, context = _resolved()
    exercise = create_authority_exercise(
        resolution_context_id=context.context_id,
        effective_authority_scope_id=scope.scope_id,
        protected_operation_class=context.protected_operation_class,
        created_at=req.requested_execution_time,
        authority_exercise_id="EX-DERIVATION",
    )
    attempt = create_execution_attempt(
        authority_exercise_id=exercise.authority_exercise_id,
        route_id="R1",
        executor_id="EXEC-1",
        created_at=req.requested_execution_time,
        execution_attempt_id="ATT-DERIVATION",
    )
    operation = materialise_protected_operation(
        req, route_id="R1", executor_id="EXEC-1",
        authority_exercise_id=exercise.authority_exercise_id,
        execution_attempt_id=attempt.execution_attempt_id,
    )
    binding = bind_authority_to_operation(scope, operation)
    from dataclasses import replace
    incompatible_scope = replace(scope, derivation_graph_id="GRAPH-OTHER")
    with pytest.raises(ValueError, match="derivation mismatch"):
        issue_authorised_execution_constraint(
            context=context,
            scope=incompatible_scope,
            operation=operation,
            binding=binding,
            resolved_at=req.requested_execution_time,
            authority_exercise=exercise,
            execution_attempt=attempt,
        )


def test_retry_preserves_stable_institutional_operation_identity_across_attempt_materialisation():
    """One institutional payment must remain the same act across retry attempts.

    Attempt/materialisation identity may change; the institutional operation
    identity must not. This deliberately tests the separation rather than
    forcing attempt-specific route/executor identity to become the business
    operation identity.
    """
    req, _, _ = _resolved()
    first = materialise_protected_operation(
        req,
        route_id="R1",
        executor_id="EXEC-1",
        authority_exercise_id="EX-STABLE-OP",
        execution_attempt_id="ATT-STABLE-OP-1",
    )
    retry = materialise_protected_operation(
        req,
        route_id="R1",
        executor_id="EXEC-1",
        authority_exercise_id="EX-STABLE-OP",
        execution_attempt_id="ATT-STABLE-OP-2",
    )

    assert first.operation_id != retry.operation_id
    assert first.materialization_id != retry.materialization_id
    assert first.institutional_operation_id == retry.institutional_operation_id


def test_two_distinct_identical_payment_instructions_must_not_collapse_to_same_institutional_operation():
    """Failure-first: content equality is not institutional identity.

    Two separately initiated institutional acts may intentionally carry identical
    payment fields. They must remain distinguishable as institutional operations.
    """
    req, _, _ = _resolved()

    first_req = replace(req, institutional_operation_id="PAYMENT-INSTRUCTION-001")
    second_req = replace(req, institutional_operation_id="PAYMENT-INSTRUCTION-002")
    first = materialise_protected_operation(
        first_req,
        route_id="R1",
        executor_id="EXEC-1",
        authority_exercise_id="EX-DISTINCT-PAYMENT-1",
        execution_attempt_id="ATT-DISTINCT-PAYMENT-1",
    )
    second = materialise_protected_operation(
        second_req,
        route_id="R1",
        executor_id="EXEC-1",
        authority_exercise_id="EX-DISTINCT-PAYMENT-2",
        execution_attempt_id="ATT-DISTINCT-PAYMENT-2",
    )

    assert first.operation_id != second.operation_id
    assert first.institutional_operation_id != second.institutional_operation_id, (
        "INSTITUTIONAL IDENTITY FAILURE: two distinct institutional payment acts "
        "with identical content collapsed to the same institutional_operation_id"
    )
