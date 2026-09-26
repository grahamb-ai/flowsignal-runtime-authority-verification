from app.engines.institutional_authority import get_authority_snapshot


def test_unknown_mandate_has_no_authoritative_snapshot():
    assert get_authority_snapshot("ATTACKER-SUPPLIED-MANDATE") is None


def test_snapshot_binds_semantics_source_competence_epoch_and_fence():
    snap = get_authority_snapshot("MANDATE-TREASURY-001")
    assert snap is not None
    assert snap.snapshot_id
    assert snap.authority_epoch_id == "AUTH-EPOCH-001"
    assert snap.authority_fence_scope_key == "institution-001:MANDATE-TREASURY-001"
    assert snap.authority_fence >= 1
    assert snap.authoritative_source_id == "INSTITUTIONAL-AUTHORITY-STORE-001"
    assert snap.source_competence_root_id == "INSTITUTIONAL-COMPETENCE-ROOT-001"
    assert snap.semantics.version == "NORM-PAY-001-v1.2"
    assert snap.semantics.definition_id
    assert snap.semantics.source_id


def test_snapshot_contains_authoritative_mandate_scope():
    snap = get_authority_snapshot("MANDATE-TREASURY-001")
    assert snap.mandate.principal_id == "institution-001"
    assert snap.mandate.action == "payment.release"
    assert snap.mandate.currency == "GBP"
    assert "TREASURY-001" in snap.mandate.source_accounts
