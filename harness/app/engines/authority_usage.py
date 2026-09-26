from __future__ import annotations

"""R4 — authority usage reservation, disposition and aggregate enforcement.

R2 defines what usage means.  R4 enforces it atomically for this bounded
reference implementation.  Consequence uncertainty is preserved: UNRESOLVED
does not silently refund consumptive authority.
"""

from dataclasses import dataclass
from decimal import Decimal
from threading import RLock

from app.engines.authority_domain import (
    AuthorityUsageDisposition,
    AuthorityUsageMode,
    AuthorityUsagePolicy,
    AuthorityUsageReservation,
    AuthorityUsageState,
)


_LOCK = RLock()
_POLICIES: dict[str, AuthorityUsagePolicy] = {}
_RESERVATIONS: dict[str, AuthorityUsageReservation] = {}
_SCOPE_RESERVATIONS: dict[str, set[str]] = {}

# Bounded reference authority for policy registration. Possession of a policy
# object is not authority to create a new economic usage scope.
_POLICY_REGISTRATION_CAPABILITY = object()


def register_usage_policy(
    policy: AuthorityUsagePolicy, *, registration_capability: object | None = None
) -> None:
    if registration_capability is not _POLICY_REGISTRATION_CAPABILITY:
        raise ValueError("usage policy registration requires authoritative derivation")
    with _LOCK:
        existing = _POLICIES.get(policy.usage_policy_id)
        if existing is not None and existing != policy:
            raise ValueError("usage policy identity already bound differently")
        _POLICIES[policy.usage_policy_id] = policy


def _active_amount(scope_key: str) -> Decimal:
    total = Decimal("0")
    for reservation_id in _SCOPE_RESERVATIONS.get(scope_key, set()):
        reservation = _RESERVATIONS[reservation_id]
        if reservation.state in (
            AuthorityUsageState.RESERVED,
            AuthorityUsageState.CONSUMED,
            AuthorityUsageState.QUARANTINED,
        ):
            value = reservation.reserved_amount_or_units
            if value is not None:
                total += Decimal(str(value))
    return total


def reserve_authority_usage(
    *,
    reservation_id: str,
    usage_policy_id: str,
    authority_exercise_id: str,
    execution_attempt_id: str,
    amount_or_units: Decimal | int | None,
) -> AuthorityUsageReservation:
    with _LOCK:
        policy = _POLICIES.get(usage_policy_id)
        if policy is None:
            raise ValueError("unknown authority usage policy")

        proposed = AuthorityUsageReservation(
            reservation_id=reservation_id,
            usage_policy_id=usage_policy_id,
            authority_exercise_id=authority_exercise_id,
            execution_attempt_id=execution_attempt_id,
            reserved_amount_or_units=amount_or_units,
            state=AuthorityUsageState.RESERVED,
        )
        existing = _RESERVATIONS.get(reservation_id)
        if existing is not None:
            if existing == proposed:
                return existing
            raise ValueError("reservation identity already bound differently")

        if policy.mode == AuthorityUsageMode.SINGLE:
            if any(
                _RESERVATIONS[rid].state in (
                    AuthorityUsageState.RESERVED,
                    AuthorityUsageState.CONSUMED,
                    AuthorityUsageState.QUARANTINED,
                )
                for rid in _SCOPE_RESERVATIONS.get(policy.scope_key, set())
            ):
                raise ValueError("single-use authority already exercised or reserved")

        if policy.mode in (AuthorityUsageMode.BOUNDED, AuthorityUsageMode.AGGREGATE):
            if policy.capacity is None or amount_or_units is None:
                raise ValueError("bounded/aggregate authority requires capacity and reservation amount")
            proposed_total = _active_amount(policy.scope_key) + Decimal(str(amount_or_units))
            if proposed_total > Decimal(str(policy.capacity)):
                raise ValueError("aggregate authority capacity exceeded")

        _RESERVATIONS[reservation_id] = proposed
        _SCOPE_RESERVATIONS.setdefault(policy.scope_key, set()).add(reservation_id)
        return proposed


def _transition(
    reservation_id: str,
    *,
    to_state: AuthorityUsageState,
    disposition_rule_id: str,
    evidence_ids: tuple[str, ...],
) -> AuthorityUsageDisposition:
    with _LOCK:
        current = _RESERVATIONS.get(reservation_id)
        if current is None:
            raise ValueError("unknown authority usage reservation")
        if current.state != AuthorityUsageState.RESERVED:
            raise ValueError("only reserved authority may be dispositioned")

        updated = AuthorityUsageReservation(
            reservation_id=current.reservation_id,
            usage_policy_id=current.usage_policy_id,
            authority_exercise_id=current.authority_exercise_id,
            execution_attempt_id=current.execution_attempt_id,
            reserved_amount_or_units=current.reserved_amount_or_units,
            state=to_state,
        )
        _RESERVATIONS[reservation_id] = updated
        return AuthorityUsageDisposition(
            disposition_id=f"DISP:{reservation_id}:{to_state.value}",
            reservation_id=reservation_id,
            from_state=current.state,
            to_state=to_state,
            disposition_rule_id=disposition_rule_id,
            evidence_ids=evidence_ids,
        )


def consume_authority_usage(
    reservation_id: str, *, evidence_ids: tuple[str, ...] = ()
) -> AuthorityUsageDisposition:
    return _transition(
        reservation_id,
        to_state=AuthorityUsageState.CONSUMED,
        disposition_rule_id="USAGE:COMMITMENT-FORMED",
        evidence_ids=evidence_ids,
    )


def release_authority_usage(
    reservation_id: str, *, evidence_ids: tuple[str, ...]
) -> AuthorityUsageDisposition:
    if not evidence_ids:
        raise ValueError("release requires competent non-formation evidence")
    return _transition(
        reservation_id,
        to_state=AuthorityUsageState.RELEASED,
        disposition_rule_id="USAGE:DEMONSTRABLY-NOT-FORMED",
        evidence_ids=evidence_ids,
    )


def quarantine_authority_usage(
    reservation_id: str, *, evidence_ids: tuple[str, ...] = ()
) -> AuthorityUsageDisposition:
    return _transition(
        reservation_id,
        to_state=AuthorityUsageState.QUARANTINED,
        disposition_rule_id="USAGE:OUTCOME-UNRESOLVED",
        evidence_ids=evidence_ids,
    )


def get_usage_reservation(reservation_id: str) -> AuthorityUsageReservation | None:
    with _LOCK:
        return _RESERVATIONS.get(reservation_id)


def resolve_quarantined_authority_usage(
    reservation_id: str,
    *,
    resolution: str,
    evidence_ids: tuple[str, ...],
    permit_signature: str | None = None,
    action_binding_hash: str | None = None,
) -> AuthorityUsageDisposition:
    """Resolve quarantine only with independently registered exact outcome evidence."""
    from app.engines.outcome_evidence import verify_competent_outcome_evidence

    if resolution not in ("NON_FORMATION", "FORMATION"):
        raise ValueError("unknown quarantine resolution")
    if permit_signature is None or action_binding_hash is None:
        raise ValueError("quarantine resolution requires exact execution evidence binding")
    if not verify_competent_outcome_evidence(
        evidence_ids,
        permit_signature=permit_signature,
        action_binding_hash=action_binding_hash,
        outcome=resolution,
    ):
        raise ValueError("quarantine resolution evidence is not competent for exact execution")

    with _LOCK:
        current = _RESERVATIONS.get(reservation_id)
        if current is None:
            raise ValueError("unknown authority usage reservation")
        if current.state != AuthorityUsageState.QUARANTINED:
            raise ValueError("only quarantined authority may use quarantine resolution")

        to_state = (
            AuthorityUsageState.RELEASED
            if resolution == "NON_FORMATION"
            else AuthorityUsageState.CONSUMED
        )
        updated = AuthorityUsageReservation(
            reservation_id=current.reservation_id,
            usage_policy_id=current.usage_policy_id,
            authority_exercise_id=current.authority_exercise_id,
            execution_attempt_id=current.execution_attempt_id,
            reserved_amount_or_units=current.reserved_amount_or_units,
            state=to_state,
        )
        _RESERVATIONS[reservation_id] = updated
        from app.engines.outcome_evidence import close_outcome_disposition
        close_outcome_disposition(
            permit_signature=permit_signature,
            action_binding_hash=action_binding_hash,
            outcome=resolution,
        )
        return AuthorityUsageDisposition(
            disposition_id=f"DISP:{reservation_id}:{to_state.value}",
            reservation_id=reservation_id,
            from_state=current.state,
            to_state=to_state,
            disposition_rule_id=(
                "USAGE:QUARANTINE-RESOLVED-NOT-FORMED"
                if resolution == "NON_FORMATION"
                else "USAGE:QUARANTINE-RESOLVED-FORMED"
            ),
            evidence_ids=evidence_ids,
        )


def reset_authority_usage_reference_state_for_test() -> None:
    """Clear process-local R4 reference state between independent tests.

    This is deliberately a test/reference-harness boundary only. It must not be
    called between authority exercises that are intended to share one governing
    mandate/epoch aggregate scope.
    """
    with _LOCK:
        _POLICIES.clear()
        _RESERVATIONS.clear()
        _SCOPE_RESERVATIONS.clear()
