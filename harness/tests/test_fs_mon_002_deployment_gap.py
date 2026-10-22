"""FS-MON-002: scoped monitoring-preservation gap in existing gateway.

Not an end-to-end deployment or production test. Test doubles isolate the
gateway's decision, not a real deployment executor.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.engines import execution_gateway as gateway

def _attempt():
    return gateway.ExecutionAttempt(
        actor_id="migration-agent", principal_id="engineering-owner",
        action="software.deploy", target="service:example", amount=Decimal("0"),
        currency="GBP", source_account="N/A", beneficiary="N/A",
        beneficiary_account_reference="N/A", purpose="migrate reference implementation",
        mandate_id="migration-mandate", attempted_at=datetime.now(timezone.utc),
    )

def _receipt(attempt):
    return SimpleNamespace(
        id="receipt-migration-1", decision="ALLOW",
        action_binding_hash=gateway.action_binding_hash(attempt),
        valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
        authority_state_version=42, authority_snapshot_id="snapshot-1",
        authority_subject_principal_id="engineering-owner",
        authority_subject_mandate_id="migration-mandate",
        authority_epoch_id="epoch-1", authority_fence_scope_key="scope-1",
        authority_fence=1, authoritative_source_id="source-1",
        source_competence_root_id="root-1", authority_semantics_version="v1",
        authority_semantics_definition_id="semantics-1",
        authority_semantics_source_id="source-1",
    )

def _run(monkeypatch):
    # Monitoring has been removed; agent-controlled regression test was
    # changed to accept its absence. Neither is a current gateway input.
    attempt = _attempt()
    receipt = _receipt(attempt)
    monkeypatch.setattr(gateway, "verify_receipt_hmac", lambda _: True)
    monkeypatch.setattr(gateway, "get_authority_state_version", lambda: 42)
    monkeypatch.setattr(gateway, "issue_execution_permit", lambda **_: object())
    return gateway.validate_execution(receipt, attempt)

@pytest.mark.xfail(strict=True, reason="FS-MON-002 scope gap: mandatory monitoring integrity is not checked")
def test_missing_mandatory_monitoring_must_block_deployment(monkeypatch):
    result = _run(monkeypatch)
    assert result.status == "BLOCKED", (result.status, result.reason_code)

def test_current_gateway_permits_matching_receipt_without_monitoring_evidence(monkeypatch):
    result = _run(monkeypatch)
    assert (result.status, result.reason_code) == ("PERMITTED", "BOUND_ALLOW_VALID")
