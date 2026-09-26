from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

_RECEIPT_HMAC_KEY = b"flowsignal-at0044-harness-key"


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _normalise(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc_text(value)
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if is_dataclass(value):
        return _normalise(asdict(value))
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value


def compute_receipt_hmac(
    *,
    receipt_id: str,
    scenario_id: str,
    decision: str,
    reason_code: str,
    sealed_at: datetime,
    valid_until: datetime | None,
    action_binding_hash: str,
    authority_state_version: int,
    authority_snapshot_id: str,
    authority_subject_principal_id: str,
    authority_subject_mandate_id: str,
    authority_epoch_id: str,
    authority_fence_scope_key: str,
    authority_fence: int,
    authoritative_source_id: str,
    source_competence_root_id: str,
    authority_semantics_version: str,
    authority_semantics_definition_id: str,
    authority_semantics_source_id: str,
    request_snapshot: dict,
    checks: list,
    evidence_references: list,
) -> str:
    payload = {
        "receipt_id": receipt_id,
        "scenario_id": scenario_id,
        "decision": decision,
        "reason_code": reason_code,
        "sealed_at": _utc_text(sealed_at),
        "valid_until": _utc_text(valid_until),
        "action_binding_hash": action_binding_hash,
        "authority_state_version": authority_state_version,
        "authority_snapshot_id": authority_snapshot_id,
        "authority_subject_principal_id": authority_subject_principal_id,
        "authority_subject_mandate_id": authority_subject_mandate_id,
        "authority_epoch_id": authority_epoch_id,
        "authority_fence_scope_key": authority_fence_scope_key,
        "authority_fence": authority_fence,
        "authoritative_source_id": authoritative_source_id,
        "source_competence_root_id": source_competence_root_id,
        "authority_semantics_version": authority_semantics_version,
        "authority_semantics_definition_id": authority_semantics_definition_id,
        "authority_semantics_source_id": authority_semantics_source_id,
        "request_snapshot": _normalise(request_snapshot),
        "checks": _normalise(checks),
        "evidence_references": _normalise(evidence_references),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(_RECEIPT_HMAC_KEY, raw, hashlib.sha256).hexdigest()


def verify_receipt_hmac(receipt) -> bool:
    expected = compute_receipt_hmac(
        receipt_id=receipt.id,
        scenario_id=receipt.scenario_id,
        decision=receipt.decision,
        reason_code=receipt.reason_code,
        sealed_at=receipt.sealed_at,
        valid_until=receipt.valid_until,
        action_binding_hash=receipt.action_binding_hash,
        authority_state_version=receipt.authority_state_version,
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
        request_snapshot=receipt.request_snapshot,
        checks=receipt.checks,
        evidence_references=receipt.evidence_references,
    )
    return hmac.compare_digest(receipt.receipt_hmac, expected)
