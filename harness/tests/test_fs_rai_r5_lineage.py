from datetime import datetime, timezone

import pytest

from app.engines.authority_lineage import (
    bind_attempt_to_operation,
    create_authority_exercise,
    create_execution_attempt,
    verify_lineage,
)


NOW = datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc)


def test_r5_explicit_lineage_positive_control():
    ex = create_authority_exercise(
        resolution_context_id="CTX-R5-1",
        effective_authority_scope_id="SCOPE-R5-1",
        protected_operation_class="treasury.payment",
        created_at=NOW,
    )
    att = create_execution_attempt(
        authority_exercise_id=ex.authority_exercise_id,
        route_id="R1",
        executor_id="EXEC-1",
        created_at=NOW,
    )
    bind_attempt_to_operation(
        authority_exercise_id=ex.authority_exercise_id,
        execution_attempt_id=att.execution_attempt_id,
        protected_operation_id="OP-1",
    )
    assert verify_lineage(
        authority_exercise_id=ex.authority_exercise_id,
        execution_attempt_id=att.execution_attempt_id,
        protected_operation_id="OP-1",
        resolution_context_id="CTX-R5-1",
        effective_authority_scope_id="SCOPE-R5-1",
        route_id="R1",
        executor_id="EXEC-1",
    )


def test_attempt_cannot_move_between_authority_exercises():
    ex1 = create_authority_exercise(
        resolution_context_id="CTX-R5-A", effective_authority_scope_id="SCOPE-A",
        protected_operation_class="treasury.payment", created_at=NOW
    )
    ex2 = create_authority_exercise(
        resolution_context_id="CTX-R5-B", effective_authority_scope_id="SCOPE-B",
        protected_operation_class="treasury.payment", created_at=NOW
    )
    att = create_execution_attempt(
        authority_exercise_id=ex1.authority_exercise_id,
        route_id="R1", executor_id="EXEC-1", created_at=NOW
    )
    with pytest.raises(ValueError, match="different authority exercise"):
        bind_attempt_to_operation(
            authority_exercise_id=ex2.authority_exercise_id,
            execution_attempt_id=att.execution_attempt_id,
            protected_operation_id="OP-X",
        )


def test_attempt_identity_cannot_be_rebound_to_different_operation():
    ex = create_authority_exercise(
        resolution_context_id="CTX-R5-C", effective_authority_scope_id="SCOPE-C",
        protected_operation_class="treasury.payment", created_at=NOW
    )
    att = create_execution_attempt(
        authority_exercise_id=ex.authority_exercise_id,
        route_id="R1", executor_id="EXEC-1", created_at=NOW
    )
    bind_attempt_to_operation(
        authority_exercise_id=ex.authority_exercise_id,
        execution_attempt_id=att.execution_attempt_id,
        protected_operation_id="OP-ORIGINAL",
    )
    with pytest.raises(ValueError, match="different operation"):
        bind_attempt_to_operation(
            authority_exercise_id=ex.authority_exercise_id,
            execution_attempt_id=att.execution_attempt_id,
            protected_operation_id="OP-SUBSTITUTED",
        )


def test_retry_is_new_attempt_with_parent_lineage():
    ex = create_authority_exercise(
        resolution_context_id="CTX-R5-D", effective_authority_scope_id="SCOPE-D",
        protected_operation_class="treasury.payment", created_at=NOW
    )
    first = create_execution_attempt(
        authority_exercise_id=ex.authority_exercise_id,
        route_id="R1", executor_id="EXEC-1", created_at=NOW
    )
    retry = create_execution_attempt(
        authority_exercise_id=ex.authority_exercise_id,
        parent_execution_attempt_id=first.execution_attempt_id,
        route_id="R1", executor_id="EXEC-1", created_at=NOW
    )
    assert retry.execution_attempt_id != first.execution_attempt_id
    assert retry.parent_execution_attempt_id == first.execution_attempt_id
    assert retry.attempt_ordinal == 2


def test_retry_parent_cannot_cross_exercise_boundary():
    ex1 = create_authority_exercise(
        resolution_context_id="CTX-R5-E1", effective_authority_scope_id="SCOPE-E1",
        protected_operation_class="treasury.payment", created_at=NOW
    )
    ex2 = create_authority_exercise(
        resolution_context_id="CTX-R5-E2", effective_authority_scope_id="SCOPE-E2",
        protected_operation_class="treasury.payment", created_at=NOW
    )
    first = create_execution_attempt(
        authority_exercise_id=ex1.authority_exercise_id,
        route_id="R1", executor_id="EXEC-1", created_at=NOW
    )
    with pytest.raises(ValueError, match="different authority exercise"):
        create_execution_attempt(
            authority_exercise_id=ex2.authority_exercise_id,
            parent_execution_attempt_id=first.execution_attempt_id,
            route_id="R1", executor_id="EXEC-1", created_at=NOW
        )
