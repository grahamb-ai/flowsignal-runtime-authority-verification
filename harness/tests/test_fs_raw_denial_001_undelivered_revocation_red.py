"""FS-RAW-DENIAL-001 delivery-loss FIRST RED: genuine RAI grant plus source
revocation that is NOT delivered to the separate actuator.

The actuator and source are intentionally disconnected at the update boundary.
This is an isolated localhost reference finding, not a live financial incident.
"""
from app.engines.authority_store import advance_authority_state_version,get_authority_state_version
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_rai_external_actuator import (
    KEY, actuator, mint, request, post, rows,
)

def test_undelivered_source_revocation_must_prevent_external_commit(actuator):
    permit=mint(request())
    envelope=export_final_bind(permit,bridge_key=KEY)
    assert envelope is not None
    assert get_authority_state_version()==permit.authority_state_version
    advanced=advance_authority_state_version()
    assert advanced>permit.authority_state_version
    # Deliberately do NOT publish the change to actuator's reference ledger.
    code,response=post(actuator,"/execute-b",envelope,permit.action_binding_hash)
    assert (code,response["formed"],rows(actuator))==(403,False,[]), (
        "FIRST RED: source revoked but delivery was absent. A stale local "
        "fence admitted a represented consequence. This is a reference "
        f"integration delivery gap: HTTP={code}, body={response}, rows={rows(actuator)}."
    )
