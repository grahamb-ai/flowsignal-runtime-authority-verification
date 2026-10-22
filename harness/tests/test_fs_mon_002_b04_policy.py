from dataclasses import replace
from app.engines.monitoring_policy_auth import sign_policy,verify_policy
KEY=b"trusted-policy-authority-test-key"
P=sign_policy(KEY,"monitor-policy",4,{"alerts","audit"})
def v(p,**kw):
    return verify_policy(p,KEY,expected_id=kw.get("expected_id","monitor-policy"),min_version=kw.get("min_version",4))
def test_current_policy(): assert v(P)=="VERIFIED"
def test_forged_policy_signature(): assert v(sign_policy(b"agent-key","monitor-policy",5,{"alerts"}))=="DENIED_POLICY_SIGNATURE_INVALID"
def test_remove_controls_after_signing(): assert v(replace(P,required_controls=()))=="DENIED_POLICY_SIGNATURE_INVALID"
def test_policy_rollback(): assert v(sign_policy(KEY,"monitor-policy",3,{"alerts","audit"}))=="DENIED_POLICY_ROLLBACK"
def test_other_policy_id(): assert v(P,expected_id="different")=="DENIED_POLICY_ID_MISMATCH"
def test_empty_required_controls(): assert v(sign_policy(KEY,"monitor-policy",5,set()))=="DENIED_POLICY_CONTROLS_MISSING"
def test_missing_policy(): assert v(None)=="DENIED_POLICY_MISSING"
def test_version_substitution_without_resigning(): assert v(replace(P,version=999))=="DENIED_POLICY_SIGNATURE_INVALID"
def test_trusted_version_increase_rejects_old_policy(): assert v(P,min_version=5)=="DENIED_POLICY_ROLLBACK"
