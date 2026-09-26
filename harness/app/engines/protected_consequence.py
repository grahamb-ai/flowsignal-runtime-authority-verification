from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.engines.authority_store import (
    authority_state_guard,
    get_authority_state_version_unlocked,
)
from app.engines.consequence_outcome_store import record_consequence_outcome
from app.engines.consequence_receipt import (
    ConsequenceOutcomeReceipt,
    create_consequence_outcome_receipt,
)
from app.engines.permit_authority import ExecutionPermit, verify_execution_permit
from app.engines.rai_execution_registry import get_rai_execution_binding, verify_rai_execution_binding
from app.engines.final_bind_provenance import verify_final_bind_provenance
from app.engines.authority_domain import AuthorityUsageState
from app.engines.authority_usage import consume_authority_usage, get_usage_reservation, quarantine_authority_usage
from app.engines.permit_consumption_store import consume_execution_permit_and_begin_outcome_once
from app.engines.rollback_anchor_store import claim_execution_anchor_once
from app.engines.institutional_authority import get_authority_snapshot


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def execute_protected_consequence(
    permit: ExecutionPermit | None,
    attempted_action_binding_hash: str,
    *,
    before_formation_hook: Callable[[], None] | None = None,
) -> str:
    """Consume, but do not mint, a consequence-authorising execution permit.

    Permit issuance/signing lives in the separate reference permit-authority
    component. This represented execution component verifies the permit, checks
    exact action binding and temporal/current-state standing, and establishes
    durable permit consumption together with an initial unresolved execution
    outcome before entering the remaining consequence-formation interval.

    PMQ-002.9 commits permit consumption and CONSEQUENCE_OUTCOME_UNRESOLVED
    together through one attached-database transaction.

    PMQ-002.10 adds a separate surviving rollback anchor. Ordinary replay remains
    distinguishable from rollback: if the anchor already exists and the durable
    permit store also reports the permit consumed, the result remains the prior
    DENIED_EXECUTION_PERMIT_REPLAY. If the anchor already exists but the restored
    execution-state stores accept the permit as apparently unused, execution is
    stopped as DENIED_EXECUTION_STATE_ROLLBACK_OR_REPLAY before consequence
    formation.

    This is a reference-MVP local SQLite boundary. The rollback anchor only
    demonstrates detection when that separate anchor survives rollback of the
    permit-consumption and consequence-outcome stores. It is not claimed as
    resistance to rollback of all local state, production distributed
    transactionality, database HA, cross-host atomicity, fsync/power-loss
    durability, immutable/write-once audit, external payment idempotency or
    production process/IAM/KMS/HSM isolation.
    """
    if permit is None:
        return "DENIED_NO_EXECUTION_PERMIT"

    if not verify_execution_permit(permit):
        return "DENIED_INVALID_EXECUTION_PERMIT"

    if permit.action_binding_hash != attempted_action_binding_hash:
        return "DENIED_ACTION_BINDING_MISMATCH"

    # For this RAI-protected consequence boundary, signed RAI-looking fields are
    # not sufficient. The permit must correspond to a capability registered by
    # the successful final-bind mint path for this exact lineage and action.
    if not verify_rai_execution_binding(
        permit_signature=permit.signature,
        determination_id=permit.rai_determination_id,
        constraint_id=permit.rai_constraint_id,
        protected_operation_id=permit.rai_protected_operation_id,
        authority_exercise_id=permit.rai_authority_exercise_id,
        execution_attempt_id=permit.rai_execution_attempt_id,
        action_binding_hash=attempted_action_binding_hash,
    ):
        return "DENIED_RAI_EXECUTION_BINDING_REQUIRED"

    binding = get_rai_execution_binding(permit.signature)
    if binding is None:
        return "DENIED_RAI_EXECUTION_BINDING_REQUIRED"

    if not verify_final_bind_provenance(
        binding.final_bind_provenance_id,
        determination_id=binding.determination_id,
        constraint_id=binding.constraint_id,
        protected_operation_id=binding.protected_operation_id,
        authority_exercise_id=binding.authority_exercise_id,
        execution_attempt_id=binding.execution_attempt_id,
        action_binding_hash=binding.action_binding_hash,
        usage_reservation_id=binding.usage_reservation_id,
        permit_signature=permit.signature,
    ):
        return "DENIED_FINAL_BIND_PROVENANCE_REQUIRED"

    if permit.valid_until is None:
        return "DENIED_EXECUTION_PERMIT_EXPIRY_MISSING"

    try:
        permit_expiry = _aware(datetime.fromisoformat(permit.valid_until))
    except (TypeError, ValueError):
        return "DENIED_EXECUTION_PERMIT_EXPIRY_INVALID"

    if datetime.now(timezone.utc) > permit_expiry:
        return "DENIED_EXECUTION_PERMIT_EXPIRED"

    with authority_state_guard():
        if datetime.now(timezone.utc) > permit_expiry:
            return "DENIED_EXECUTION_PERMIT_EXPIRED"

        current_authority_state_version = get_authority_state_version_unlocked()
        if permit.authority_state_version != current_authority_state_version:
            return "DENIED_AUTHORITY_STATE_STALE"

        # Replay classification must remain authoritative for an already-consumed
        # capability. Usage state is checked only after durable permit consumption
        # establishes that this is a new commitment attempt.
        anchor_was_new = claim_execution_anchor_once(
            permit_signature=permit.signature,
            action_binding_hash=attempted_action_binding_hash,
        )

        consumption_was_new = consume_execution_permit_and_begin_outcome_once(
            permit.signature,
            attempted_action_binding_hash,
        )

        if not consumption_was_new:
            return "DENIED_EXECUTION_PERMIT_REPLAY"

        if not anchor_was_new:
            return "DENIED_EXECUTION_STATE_ROLLBACK_OR_REPLAY"

        usage_reservation = get_usage_reservation(binding.usage_reservation_id)
        if (
            usage_reservation is None
            or usage_reservation.state != AuthorityUsageState.RESERVED
            or usage_reservation.authority_exercise_id != permit.rai_authority_exercise_id
            or usage_reservation.execution_attempt_id != permit.rai_execution_attempt_id
        ):
            return "DENIED_AUTHORITY_USAGE_RESERVATION_INVALID"

        current_snapshot = get_authority_snapshot(permit.authority_subject_mandate_id)
        if current_snapshot is None:
            return "DENIED_AUTHORITATIVE_STATE_MISSING"
        if permit.authority_subject_principal_id != current_snapshot.mandate.principal_id:
            return "DENIED_AUTHORITY_SUBJECT_PRINCIPAL_MISMATCH"
        if permit.authority_subject_mandate_id != current_snapshot.mandate.mandate_id:
            return "DENIED_AUTHORITY_SUBJECT_MANDATE_MISMATCH"
        if permit.authority_snapshot_id != current_snapshot.snapshot_id:
            return "DENIED_AUTHORITY_SNAPSHOT_STALE"
        if permit.authority_epoch_id != current_snapshot.authority_epoch_id:
            return "DENIED_AUTHORITY_EPOCH_MISMATCH"
        if permit.authority_fence_scope_key != current_snapshot.authority_fence_scope_key:
            return "DENIED_AUTHORITY_FENCE_SCOPE_MISMATCH"
        if permit.authority_fence != current_snapshot.authority_fence:
            return "DENIED_AUTHORITY_FENCE_STALE"
        if permit.authoritative_source_id != current_snapshot.authoritative_source_id:
            return "DENIED_AUTHORITY_SOURCE_MISMATCH"
        if permit.source_competence_root_id != current_snapshot.source_competence_root_id:
            return "DENIED_SOURCE_COMPETENCE_MISMATCH"
        if permit.authority_semantics_version != current_snapshot.semantics.version:
            return "DENIED_AUTHORITY_SEMANTICS_VERSION_MISMATCH"
        if permit.authority_semantics_definition_id != current_snapshot.semantics.definition_id:
            return "DENIED_AUTHORITY_SEMANTICS_DEFINITION_MISMATCH"
        if permit.authority_semantics_source_id != current_snapshot.semantics.source_id:
            return "DENIED_AUTHORITY_SEMANTICS_SOURCE_MISMATCH"

        if before_formation_hook is not None:
            try:
                before_formation_hook()
            except Exception:
                # A local interruption inside the commitment interval is not
                # competent evidence that the represented consequence did not
                # form. The durable unresolved outcome established with permit
                # consumption therefore remains authoritative until stronger
                # outcome evidence resolves it.
                quarantine_authority_usage(
                    binding.usage_reservation_id,
                    evidence_ids=(f"COMMITMENT-INTERVAL-FAILURE:{permit.signature}",),
                )
                raise

        record_consequence_outcome(
            permit_signature=permit.signature,
            action_binding_hash=attempted_action_binding_hash,
            outcome="CONSEQUENCE_FORMED",
        )
        consume_authority_usage(
            binding.usage_reservation_id,
            evidence_ids=(f"PROTECTED-COMMITMENT:{permit.signature}",),
        )

        return "CONSEQUENCE_FORMED"


def execute_protected_consequence_with_receipt(
    permit: ExecutionPermit | None,
    attempted_action_binding_hash: str,
    *,
    before_formation_hook: Callable[[], None] | None = None,
) -> tuple[str, ConsequenceOutcomeReceipt]:
    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=attempted_action_binding_hash,
        before_formation_hook=before_formation_hook,
    )
    receipt = create_consequence_outcome_receipt(
        authority_receipt_id=(permit.authority_receipt_id if permit is not None else None),
        action_binding_hash=attempted_action_binding_hash,
        authority_state_version=(permit.authority_state_version if permit is not None else None),
        outcome=outcome,
    )
    return outcome, receipt
