"""B01 process reference: verify only supported IPC can mutate remote state."""
from dataclasses import replace
from app.engines.deployment_monitoring_guard import DeploymentRequest, MonitoringPolicy, MonitoringAssessment
from app.engines.process_deployment_executor import ProcessDeploymentClient

D = "a" * 64
TARGET = "service:example"
POLICY = MonitoringPolicy("policy-1", frozenset({"alerts", "audit"}))
REQ = DeploymentRequest("migration-agent", D, TARGET, "receipt-1")
GOOD = MonitoringAssessment(D, TARGET, POLICY.policy_id, frozenset({"alerts", "audit"}), True)
REMOVED = replace(GOOD, present_controls=frozenset())

def test_authorised_deployment_formed_only_inside_executor():
    with ProcessDeploymentClient(POLICY, GOOD, True) as c:
        assert c.request("read", TARGET) == ("STATE", None)
        assert c.request("deploy", REQ)[1][2] is True
        assert c.request("read", TARGET) == ("STATE", D)

def test_unauthorised_request_never_commits():
    with ProcessDeploymentClient(POLICY, GOOD, False) as c:
        assert c.request("deploy", REQ)[1][2] is False
        assert c.request("read", TARGET) == ("STATE", None)

def test_missing_monitoring_prevents_consequence():
    with ProcessDeploymentClient(POLICY, REMOVED, True) as c:
        result=c.request("deploy", REQ)
        assert result[1][0] == "REFUSE"
        assert c.request("read", TARGET) == ("STATE", None)

def test_client_local_state_mutation_not_remote_deployment():
    with ProcessDeploymentClient(POLICY, REMOVED, False) as c:
        client_local_dictionary = {TARGET: "b" * 64}
        assert client_local_dictionary[TARGET] == "b" * 64
        assert c.request("read", TARGET) == ("STATE", None)

def test_no_direct_write_operation_exposed():
    with ProcessDeploymentClient(POLICY, REMOVED, False) as c:
        assert c.request("write", (TARGET, D)) == ("ERROR", "UNKNOWN_OPERATION")
        assert c.request("read", TARGET) == ("STATE", None)

def test_invalid_deploy_message_rejected():
    with ProcessDeploymentClient(POLICY, GOOD, True) as c:
        assert c.request("deploy", {"target": TARGET}) == ("ERROR", "INVALID_DEPLOYMENT_REQUEST")
        assert c.request("read", TARGET) == ("STATE", None)

def test_exact_artifact_binding_rejects_substitution():
    with ProcessDeploymentClient(POLICY, GOOD, True) as c:
        result=c.request("deploy", replace(REQ, artifact_digest="b" * 64))
        assert result[1][2] is False
        assert c.request("read", TARGET) == ("STATE", None)
