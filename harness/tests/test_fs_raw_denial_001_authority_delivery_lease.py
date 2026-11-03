"""FS-RAW-DENIAL-001 reference freshness lease characterization.

Uses real RAI final-bind/export and an independently running localhost
actuator. The trusted publisher is simulated. A lease BOUNDS stale exposure;
it CANNOT guarantee immediate rejection of revocation not yet delivered.
"""
from contextlib import closing
import sqlite3
import pytest
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test

@pytest.fixture(autouse=True)
def isolate_usage_reservations():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

from app.engines.authority_store import advance_authority_state_version
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_rai_external_actuator import (
    KEY, actuator, mint, request, post, rows,
)

def aged_publication(db,seconds):
    with closing(sqlite3.connect(db)) as con:
        with con:
            con.execute(
                "UPDATE authority_fence SET observed_at=observed_at-?",
                (seconds,),
            )

def test_current_authority_publication_accepts_one_valid_grant(actuator):
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    assert exported is not None
    code,result=post(actuator,"/execute-a",exported,permit.action_binding_hash)
    assert (code,result["status"])==(200,"CONSEQUENCE_FORMED")
    assert len(rows(actuator))==1

def test_expired_authority_publication_fails_closed(actuator):
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    aged_publication(actuator[1],120)
    code,result=post(actuator,"/execute-a",exported,permit.action_binding_hash)
    assert (code,result["status"])==(403,"AUTHORITY_STATE_FRESHNESS_EXPIRED")
    assert rows(actuator)==[]

def test_revocation_not_delivered_and_lease_expired_is_refused(actuator):
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    assert exported is not None
    version=advance_authority_state_version()
    assert version>permit.authority_state_version
    # Deliberately do not publish, allowing the previous snapshot to age.
    aged_publication(actuator[1],120)
    code,result=post(actuator,"/execute-b",exported,permit.action_binding_hash)
    assert (code,result["status"])==(403,"AUTHORITY_STATE_FRESHNESS_EXPIRED")
    assert rows(actuator)==[]

def test_unavailable_published_state_fails_closed(actuator):
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    with closing(sqlite3.connect(actuator[1])) as con:
        with con:
            con.execute("DELETE FROM authority_fence")
    code,result=post(actuator,"/execute-a",exported,permit.action_binding_hash)
    assert (code,result["status"])==(403,"AUTHORITY_STATE_UNAVAILABLE")
    assert rows(actuator)==[]

def test_revocation_without_delivery_inside_lease_remains_a_gap(actuator):
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    assert exported is not None
    version=advance_authority_state_version()
    assert version>permit.authority_state_version
    # No publication, but prior publication is still within the allowed lease.
    code,result=post(actuator,"/execute-b",exported,permit.action_binding_hash)
    assert (code,result["status"])==(200,"CONSEQUENCE_FORMED")
    assert len(rows(actuator))==1
    # Characterisation of an UNRESOLVED vulnerability window, not a PASS of
    # the original immediate-revocation invariant.

def test_published_new_version_blocks_old_grant_even_with_fresh_lease(actuator):
    from app.engines.sandbox_authority_fence_publisher import publish_authority_version
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    newer=advance_authority_state_version()
    assert publish_authority_version(actuator[1],newer)
    code,result=post(actuator,"/execute-a",exported,permit.action_binding_hash)
    assert (code,result["status"])==(403,"AUTHORITY_STATE_STALE")
    assert rows(actuator)==[]
