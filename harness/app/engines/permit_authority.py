from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

_PERMIT_KEY = os.environ.get(
    "FLOWSIGNAL_EXECUTION_PERMIT_KEY",
    "flowsignal-reference-harness-ec0014-key",
).encode("utf-8")
_GATEWAY_MINT_CAPABILITY = object()


@dataclass(frozen=True)
class ExecutionPermit:
    authority_receipt_id: str
    action_binding_hash: str
    authority_state_version: int
    authority_snapshot_id: str
    authority_subject_principal_id: str
    authority_subject_mandate_id: str
    authority_epoch_id: str
    authority_fence_scope_key: str
    authority_fence: int
    authoritative_source_id: str
    source_competence_root_id: str
    authority_semantics_version: str
    authority_semantics_definition_id: str
    authority_semantics_source_id: str
    issued_at: str
    signature: str
    valid_until: str | None = None
    rai_determination_id: str | None = None
    rai_constraint_id: str | None = None
    rai_protected_operation_id: str | None = None
    rai_authority_exercise_id: str | None = None
    rai_execution_attempt_id: str | None = None


def _payload(**fields) -> bytes:
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(**fields) -> str:
    return hmac.new(_PERMIT_KEY, _payload(**fields), hashlib.sha256).hexdigest()


def issue_execution_permit(
    authority_receipt_id: str,
    action_binding_hash: str,
    authority_state_version: int,
    *,
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
    valid_until: str | None = None,
    rai_determination_id: str | None = None,
    rai_constraint_id: str | None = None,
    rai_protected_operation_id: str | None = None,
    rai_authority_exercise_id: str | None = None,
    rai_execution_attempt_id: str | None = None,
    mint_capability: object | None = None,
) -> ExecutionPermit | None:
    if mint_capability is not _GATEWAY_MINT_CAPABILITY or valid_until is None:
        return None
    issued_at = datetime.now(timezone.utc).isoformat()
    fields = dict(
        authority_receipt_id=authority_receipt_id,
        action_binding_hash=action_binding_hash,
        authority_state_version=authority_state_version,
        authority_snapshot_id=authority_snapshot_id,
        authority_subject_principal_id=authority_subject_principal_id,
        authority_subject_mandate_id=authority_subject_mandate_id,
        authority_epoch_id=authority_epoch_id,
        authority_fence_scope_key=authority_fence_scope_key,
        authority_fence=authority_fence,
        authoritative_source_id=authoritative_source_id,
        source_competence_root_id=source_competence_root_id,
        authority_semantics_version=authority_semantics_version,
        authority_semantics_definition_id=authority_semantics_definition_id,
        authority_semantics_source_id=authority_semantics_source_id,
        issued_at=issued_at,
        valid_until=valid_until,
        rai_determination_id=rai_determination_id,
        rai_constraint_id=rai_constraint_id,
        rai_protected_operation_id=rai_protected_operation_id,
        rai_authority_exercise_id=rai_authority_exercise_id,
        rai_execution_attempt_id=rai_execution_attempt_id,
    )
    return ExecutionPermit(**fields, signature=_sign(**fields))


def verify_execution_permit(permit: ExecutionPermit) -> bool:
    fields = {
        k: getattr(permit, k)
        for k in (
            "authority_receipt_id", "action_binding_hash", "authority_state_version",
            "authority_snapshot_id", "authority_subject_principal_id", "authority_subject_mandate_id",
            "authority_epoch_id", "authority_fence_scope_key",
            "authority_fence", "authoritative_source_id", "source_competence_root_id",
            "authority_semantics_version", "authority_semantics_definition_id",
            "authority_semantics_source_id", "issued_at", "valid_until",
            "rai_determination_id", "rai_constraint_id", "rai_protected_operation_id",
            "rai_authority_exercise_id", "rai_execution_attempt_id"
        )
    }
    return hmac.compare_digest(_sign(**fields), permit.signature)
