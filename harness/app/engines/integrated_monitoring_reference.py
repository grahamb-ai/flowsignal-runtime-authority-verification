"""FS-MON-002 integrated reference path; not production isolation.

Trusted controller holds policy/evidence keys and pins minimum policy version.
A separate process owns the simulated consequence store. Static authority
state is an explicit limitation; no real IAM/KMS/attestor or actuator.
"""
import multiprocessing as mp
from app.engines.deployment_monitoring_guard import DeploymentRequest
from app.engines.monitoring_policy_auth import verify_policy
from app.engines.monitoring_evidence_auth import verify_evidence

def _worker(conn, policy, evidence, policy_key, evidence_key, policy_id, min_version, now, authorised):
    deployed={}
    try:
        while True:
            try: msg=conn.recv()
            except EOFError: break
            if not isinstance(msg,tuple) or len(msg)!=2:
                conn.send(("REFUSE","INVALID_MESSAGE",False));continue
            op,payload=msg
            if op=="stop":
                conn.send(("OK","STOPPED",False));break
            if op=="read":
                conn.send(("STATE",deployed.get(payload),False));continue
            if op!="deploy" or not isinstance(payload,DeploymentRequest):
                conn.send(("REFUSE","UNSUPPORTED_OPERATION",False));continue
            p=verify_policy(policy,policy_key,expected_id=policy_id,min_version=min_version)
            if p!="VERIFIED":
                conn.send(("REFUSE",p,False));continue
            v=verify_evidence(evidence,evidence_key,artifact_digest=payload.artifact_digest,
                target=payload.target,policy_id=policy.policy_id,
                required_controls=policy.required_controls,now=now)
            if v!="VERIFIED":
                conn.send(("REFUSE",v,False));continue
            if not authorised or not payload.authority_receipt_id:
                conn.send(("REFUSE","AUTHORITY_NOT_ESTABLISHED",False));continue
            deployed[payload.target]=payload.artifact_digest
            conn.send(("ALLOW","SIMULATED_CONSEQUENCE_FORMED",True))
    finally: conn.close()

class IntegratedReferenceExecutor:
    def __init__(self,policy,evidence,*,policy_key,evidence_key,expected_policy_id,
                 min_version,now,authorised):
        ctx=mp.get_context("spawn")
        parent,child=ctx.Pipe()
        self._conn=parent
        self._process=ctx.Process(target=_worker,
            args=(child,policy,evidence,policy_key,evidence_key,expected_policy_id,min_version,now,authorised),
            daemon=True)
        self._process.start()
        child.close()
    def request(self,op,payload):
        self._conn.send((op,payload))
        return self._conn.recv()
    def close(self):
        if self._process.is_alive():
            try: self.request("stop",None)
            finally: self._process.join(timeout=3)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3)
        self._conn.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
