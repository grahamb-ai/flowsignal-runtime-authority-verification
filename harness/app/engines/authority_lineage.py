from __future__ import annotations

"""R5 — explicit authority-exercise / execution-attempt lineage.

An authority exercise is the institutional exercise of authority.  An execution
attempt is one concrete attempt to carry that exercise toward commitment.
Attempts may be retried only as new lineage members; an attempt identity cannot
be silently reused or rebound to another exercise/operation.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


@dataclass(frozen=True)
class AuthorityExercise:
    authority_exercise_id: str
    resolution_context_id: str
    effective_authority_scope_id: str
    protected_operation_class: str
    created_at: datetime


@dataclass(frozen=True)
class ExecutionAttemptLineage:
    execution_attempt_id: str
    authority_exercise_id: str
    parent_execution_attempt_id: str | None
    attempt_ordinal: int
    route_id: str
    executor_id: str
    created_at: datetime


@dataclass(frozen=True)
class LineageBinding:
    lineage_binding_id: str
    authority_exercise_id: str
    execution_attempt_id: str
    protected_operation_id: str


_LOCK = RLock()
_EXERCISES: dict[str, AuthorityExercise] = {}
_ATTEMPTS: dict[str, ExecutionAttemptLineage] = {}
_BINDINGS: dict[str, LineageBinding] = {}
_EXERCISE_INSTITUTIONAL_OPERATIONS: dict[str, str] = {}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stable_id(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()}"


def create_authority_exercise(
    *,
    resolution_context_id: str,
    effective_authority_scope_id: str,
    protected_operation_class: str,
    created_at: datetime,
    authority_exercise_id: str | None = None,
) -> AuthorityExercise:
    exercise = AuthorityExercise(
        authority_exercise_id=authority_exercise_id or f"EX-{uuid4()}",
        resolution_context_id=resolution_context_id,
        effective_authority_scope_id=effective_authority_scope_id,
        protected_operation_class=protected_operation_class,
        created_at=_aware(created_at),
    )
    with _LOCK:
        existing = _EXERCISES.get(exercise.authority_exercise_id)
        if existing is not None and existing != exercise:
            raise ValueError("authority exercise identity already bound differently")
        _EXERCISES[exercise.authority_exercise_id] = exercise
    return exercise


def create_execution_attempt(
    *,
    authority_exercise_id: str,
    route_id: str,
    executor_id: str,
    created_at: datetime,
    parent_execution_attempt_id: str | None = None,
    execution_attempt_id: str | None = None,
) -> ExecutionAttemptLineage:
    with _LOCK:
        if authority_exercise_id not in _EXERCISES:
            raise ValueError("unknown authority exercise")
        ordinal = 1
        if parent_execution_attempt_id is not None:
            parent = _ATTEMPTS.get(parent_execution_attempt_id)
            if parent is None:
                raise ValueError("unknown parent execution attempt")
            if parent.authority_exercise_id != authority_exercise_id:
                raise ValueError("parent attempt belongs to different authority exercise")
            ordinal = parent.attempt_ordinal + 1

        attempt = ExecutionAttemptLineage(
            execution_attempt_id=execution_attempt_id or f"ATT-{uuid4()}",
            authority_exercise_id=authority_exercise_id,
            parent_execution_attempt_id=parent_execution_attempt_id,
            attempt_ordinal=ordinal,
            route_id=route_id,
            executor_id=executor_id,
            created_at=_aware(created_at),
        )
        existing = _ATTEMPTS.get(attempt.execution_attempt_id)
        if existing is not None and existing != attempt:
            raise ValueError("execution attempt identity already bound differently")
        _ATTEMPTS[attempt.execution_attempt_id] = attempt
        return attempt


def get_execution_attempt(execution_attempt_id: str) -> ExecutionAttemptLineage | None:
    """Return the immutable registered attempt for final-bind correspondence checks."""
    with _LOCK:
        return _ATTEMPTS.get(execution_attempt_id)


def bind_attempt_to_operation(
    *,
    authority_exercise_id: str,
    execution_attempt_id: str,
    protected_operation_id: str,
) -> LineageBinding:
    with _LOCK:
        exercise = _EXERCISES.get(authority_exercise_id)
        attempt = _ATTEMPTS.get(execution_attempt_id)
        if exercise is None or attempt is None:
            raise ValueError("unknown authority exercise or execution attempt")
        if attempt.authority_exercise_id != authority_exercise_id:
            raise ValueError("execution attempt belongs to different authority exercise")

        key = execution_attempt_id
        proposed = LineageBinding(
            lineage_binding_id=_stable_id(
                "LINEAGE",
                {
                    "authority_exercise_id": authority_exercise_id,
                    "execution_attempt_id": execution_attempt_id,
                    "protected_operation_id": protected_operation_id,
                },
            ),
            authority_exercise_id=authority_exercise_id,
            execution_attempt_id=execution_attempt_id,
            protected_operation_id=protected_operation_id,
        )
        existing = _BINDINGS.get(key)
        if existing is not None and existing != proposed:
            raise ValueError("execution attempt already bound to different operation")
        _BINDINGS[key] = proposed
        return proposed


def bind_exercise_to_institutional_operation(
    *,
    authority_exercise_id: str,
    institutional_operation_id: str,
) -> None:
    """Bind one authority exercise to exactly one institutional act."""
    with _LOCK:
        if authority_exercise_id not in _EXERCISES:
            raise ValueError("unknown authority exercise")
        existing = _EXERCISE_INSTITUTIONAL_OPERATIONS.get(authority_exercise_id)
        if existing is not None and existing != institutional_operation_id:
            raise ValueError("authority exercise already bound to different institutional operation")
        _EXERCISE_INSTITUTIONAL_OPERATIONS[authority_exercise_id] = institutional_operation_id


def verify_lineage(
    *,
    authority_exercise_id: str,
    execution_attempt_id: str,
    protected_operation_id: str,
    resolution_context_id: str,
    effective_authority_scope_id: str,
    route_id: str,
    executor_id: str,
) -> bool:
    with _LOCK:
        exercise = _EXERCISES.get(authority_exercise_id)
        attempt = _ATTEMPTS.get(execution_attempt_id)
        binding = _BINDINGS.get(execution_attempt_id)
        return bool(
            exercise
            and attempt
            and binding
            and exercise.resolution_context_id == resolution_context_id
            and exercise.effective_authority_scope_id == effective_authority_scope_id
            and attempt.authority_exercise_id == authority_exercise_id
            and attempt.route_id == route_id
            and attempt.executor_id == executor_id
            and binding.authority_exercise_id == authority_exercise_id
            and binding.protected_operation_id == protected_operation_id
        )
