from datetime import datetime, timezone

from app.engines.authority_evidence_adapters import (
    get_actor_authority_evidence,
    get_operational_authority_evidence,
)


NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)


def _by_prop(items):
    return {item.proposition_id: item for item in items}


def test_actor_evidence_comes_from_authoritative_adapter():
    evidence = _by_prop(
        get_actor_authority_evidence(
            "agent-treasury-01", "institution-001", observed_at=NOW
        )
    )
    assert evidence["actor.authenticated"].observed_value is True
    assert evidence["actor.kya_status"].observed_value == "VERIFIED"
    assert evidence["actor.authenticated"].authoritative_source_id == (
        "INSTITUTIONAL-IDENTITY-STANDING-001"
    )
    assert evidence["actor.authenticated"].subject_binding == "agent-treasury-01"


def test_request_cannot_manufacture_unknown_actor_authority():
    assert get_actor_authority_evidence(
        "attacker-controlled-agent", "institution-001", observed_at=NOW
    ) == ()


def test_principal_mismatch_fails_closed():
    assert get_actor_authority_evidence(
        "agent-treasury-01", "different-principal", observed_at=NOW
    ) == ()


def test_operational_evidence_is_subject_bound():
    evidence = _by_prop(get_operational_authority_evidence("SUPPLIER-X", observed_at=NOW))
    assert evidence["counterparty.status"].observed_value == "APPROVED"
    assert evidence["account.status"].observed_value == "ACTIVE"
    assert evidence["risk.state"].observed_value == "NORMAL"
    assert all(item.subject_binding == "SUPPLIER-X" for item in evidence.values())


def test_unknown_beneficiary_does_not_inherit_presented_status():
    assert get_operational_authority_evidence("ATTACKER-SUPPLIER", observed_at=NOW) == ()
