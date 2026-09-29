from __future__ import annotations

"""Buyer-readable WHO / WHAT / NOW / MATCH receipt projection.

This module does not make an authority decision and does not mint an execution
capability.  It projects the existing R2 determination and successful final-bind
result into a compact JSON document that can be checked against those artifacts.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.engines.final_bind import FinalBindResult
from app.engines.runtime_authority_payment import PreparedAuthorityExecution


SCHEMA = "flowsignal.public-authority-receipt.v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    return value


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _assert_correspondence(
    prepared: PreparedAuthorityExecution,
    final: FinalBindResult,
) -> None:
    determination = prepared.determination
    operation = prepared.operation
    if final.status != "PERMITTED":
        raise ValueError("public receipt requires successful final-bind")
    if final.reason_code != "FINAL_BIND_AUTHORITY_REVALIDATED":
        raise ValueError("unexpected final-bind reason")
    if final.current_resolution_context_id != determination.resolution_context_id:
        raise ValueError("final-bind does not correspond to the resolved authority context")
    if final.expected_resolution_context_id != determination.resolution_context_id:
        raise ValueError("final-bind expected context mismatch")
    if final.protected_operation_id != operation.operation_id:
        raise ValueError("final-bind protected operation mismatch")
    if final.authority_exercise_id != determination.authority_exercise_id:
        raise ValueError("final-bind authority exercise mismatch")
    if final.execution_attempt_id != determination.execution_attempt_id:
        raise ValueError("final-bind execution attempt mismatch")


def build_public_authority_receipt(
    prepared: PreparedAuthorityExecution,
    final: FinalBindResult,
    *,
    bind_at: datetime,
) -> dict[str, Any]:
    """Project a successful final-bind into the public v1 JSON schema."""
    _assert_correspondence(prepared, final)
    operation = prepared.operation
    determination = prepared.determination

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "who": {
            "authority_subject_id": operation.actor_id,
            "principal_id": operation.principal_id,
            "evidence_anchor": determination.resolution_context_id,
            "claim": "AUTHORITY_SUBJECT_BOUND",
        },
        "what": {
            "protected_operation_id": operation.operation_id,
            "institutional_operation_id": operation.institutional_operation_id,
            "operation_class": operation.operation_class,
            "action": operation.action,
            "target": operation.target,
            "amount": operation.amount,
            "currency": operation.currency,
            "beneficiary_id": operation.beneficiary_id,
            "mandate_id": operation.mandate_id,
        },
        "now": {
            "checked_at": bind_at,
            "determined_at": determination.resolved_at,
            "valid_until": determination.valid_until,
            "resolution_context_id": determination.resolution_context_id,
            "status": "VALID_AT_FINAL_BIND",
        },
        "match": {
            "status": "EXACT_CORRESPONDENCE",
            "authority_operation_binding_id": determination.authority_operation_binding_id,
            "authority_exercise_id": determination.authority_exercise_id,
            "execution_attempt_id": determination.execution_attempt_id,
            "final_bind_reason": final.reason_code,
        },
        "outcome": {
            "decision": "PERMITTED_TO_ACT",
            "consequence_formed": False,
            "note": "This receipt does not assert downstream execution success.",
        },
    }
    canonical_payload = _canonical(payload)
    canonical_payload["integrity"] = {
        "algorithm": "SHA-256",
        "digest": _digest(canonical_payload),
        "security_note": (
            "Digest detects change when compared with trusted runtime artifacts; "
            "it is not an external digital signature."
        ),
    }
    return canonical_payload


def verify_public_authority_receipt(
    receipt: dict[str, Any],
    prepared: PreparedAuthorityExecution,
    final: FinalBindResult,
    *,
    bind_at: datetime,
) -> bool:
    """Verify content and correspondence against trusted runtime artifacts."""
    try:
        _assert_correspondence(prepared, final)
        integrity = receipt["integrity"]
        supplied_digest = integrity["digest"]
        unsigned = {key: value for key, value in receipt.items() if key != "integrity"}
        if not hmac.compare_digest(supplied_digest, _digest(unsigned)):
            return False
        expected = build_public_authority_receipt(
            prepared,
            final,
            bind_at=bind_at,
        )
        return hmac.compare_digest(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            json.dumps(expected, sort_keys=True, separators=(",", ":")),
        )
    except (KeyError, TypeError, ValueError):
        return False


def public_authority_receipt_json(receipt: dict[str, Any], *, indent: int = 2) -> str:
    """Render stable JSON for publication or transport."""
    return json.dumps(receipt, sort_keys=True, indent=indent)
