from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.engines.financial_types import AuthorityReceipt
from app.engines.receipt_integrity import verify_receipt_hmac
from app.engines.authority_store import get_authority_state_version
from app.engines.money import canonical_money_text
from app.engines.permit_authority import (
    ExecutionPermit,
    _GATEWAY_MINT_CAPABILITY,
    issue_execution_permit,
)

@dataclass
class ExecutionAttempt:
    actor_id: str
    principal_id: str
    action: str
    target: str
    amount: Decimal
    currency: str
    source_account: str
    beneficiary: str
    beneficiary_account_reference: str
    purpose: str
    mandate_id: str
    attempted_at: datetime


@dataclass
class GatewayResult:
    status: str
    reason_code: str
    authority_receipt_id: str
    expected_action_binding_hash: str
    attempted_action_binding_hash: str
    execution_permit: ExecutionPermit | None = None


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def action_binding_hash(attempt: ExecutionAttempt) -> str:
    payload = {
        "actor_id": attempt.actor_id,
        "principal_id": attempt.principal_id,
        "action": attempt.action,
        "target": attempt.target,
        "amount": canonical_money_text(attempt.amount),
        "currency": attempt.currency,
        "source_account": attempt.source_account,
        "beneficiary": attempt.beneficiary,
        "beneficiary_account_reference": attempt.beneficiary_account_reference,
        "purpose": attempt.purpose,
        "mandate_id": attempt.mandate_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_execution(
    receipt: AuthorityReceipt,
    attempt: ExecutionAttempt,
) -> GatewayResult:
    attempted_hash = action_binding_hash(attempt)
    if not verify_receipt_hmac(receipt):
        return GatewayResult(
            status="BLOCKED",
            reason_code="AUTHORITY_RECEIPT_INTEGRITY_INVALID",
            authority_receipt_id=receipt.id,
            expected_action_binding_hash=receipt.action_binding_hash,
            attempted_action_binding_hash=attempted_hash,
        )

    current_authority_state_version = get_authority_state_version()

    if receipt.authority_state_version != current_authority_state_version:
        return GatewayResult(
            status="BLOCKED",
            reason_code="AUTHORITY_STATE_STALE_REEVALUATION_REQUIRED",
            authority_receipt_id=receipt.id,
            expected_action_binding_hash=receipt.action_binding_hash,
            attempted_action_binding_hash=attempted_hash,
        )

    if receipt.decision != "ALLOW":
        return GatewayResult(
            status="BLOCKED",
            reason_code="NO_APPLICABLE_ALLOW",
            authority_receipt_id=receipt.id,
            expected_action_binding_hash=receipt.action_binding_hash,
            attempted_action_binding_hash=attempted_hash,
        )

    if receipt.valid_until is None or _aware(attempt.attempted_at) > _aware(receipt.valid_until):
        return GatewayResult(
            status="BLOCKED",
            reason_code="AUTHORITY_DETERMINATION_EXPIRED",
            authority_receipt_id=receipt.id,
            expected_action_binding_hash=receipt.action_binding_hash,
            attempted_action_binding_hash=attempted_hash,
        )

    if attempted_hash != receipt.action_binding_hash:
        return GatewayResult(
            status="BLOCKED",
            reason_code="ACTION_BINDING_MISMATCH",
            authority_receipt_id=receipt.id,
            expected_action_binding_hash=receipt.action_binding_hash,
            attempted_action_binding_hash=attempted_hash,
        )

    permit = issue_execution_permit(
        authority_receipt_id=receipt.id,
        action_binding_hash=attempted_hash,
        authority_state_version=current_authority_state_version,
        authority_snapshot_id=receipt.authority_snapshot_id,
        authority_subject_principal_id=receipt.authority_subject_principal_id,
        authority_subject_mandate_id=receipt.authority_subject_mandate_id,
        authority_epoch_id=receipt.authority_epoch_id,
        authority_fence_scope_key=receipt.authority_fence_scope_key,
        authority_fence=receipt.authority_fence,
        authoritative_source_id=receipt.authoritative_source_id,
        source_competence_root_id=receipt.source_competence_root_id,
        authority_semantics_version=receipt.authority_semantics_version,
        authority_semantics_definition_id=receipt.authority_semantics_definition_id,
        authority_semantics_source_id=receipt.authority_semantics_source_id,
        valid_until=_aware(receipt.valid_until).isoformat(),
        mint_capability=_GATEWAY_MINT_CAPABILITY,
    )
    return GatewayResult(
        status="PERMITTED",
        reason_code="BOUND_ALLOW_VALID",
        authority_receipt_id=receipt.id,
        expected_action_binding_hash=receipt.action_binding_hash,
        attempted_action_binding_hash=attempted_hash,
        execution_permit=permit,
    )
