"""FS-MON-002 B03 integrated candidate with authoritative revision fencing.

In-memory, single-worker reference only. A trusted caller may update state by a
separate administrative IPC command. This is NOT access-controlled IPC.
The revision is checked immediately before the simulated write, without an await
or callback between check and assignment. Real distributed atomicity unproven.
"""
import multiprocessing as mp
from app.engines.deployment_monitoring_guard import DeploymentRequest
from app.engines.monitoring_policy_auth import verify_policy
from app.engines.monitoring_evidence_auth import verify_evidence

def _worker(conn,policy,evidence,policy_key,evidence_key,policy_id,min_version,now,authorised):
    deployed={}
    state={"authorised":bool(authorised),"revision":1}
    staged={}
    try:
        while True:
            try: message=conn.recv()
            except EOFError: break
            if not isinstance(message,tuple) or len(message)!=2:
                conn.send(("REFUSE","INVALID_MESSAGE",False));continue
            op,arg=message
            if op=="stop":
                conn.send(("OK","STOPPED",False));break
            if op=="read":
                conn.send(("STATE",deployed.get(arg),False));continue
            if op=="set_authority":
                # TEST ADMIN FUNCTION. NOT AUTHENTICATED; must never be agent exposed.
                state["authorised"]=bool(arg)
                state["revision"]+=1
                conn.send(("OK","AUTHORITY_UPDATED",False));continue
            if op=="prepare":
                if not isinstance(arg,DeploymentRequest):
                    conn.send(("REFUSE","INVALID_REQUEST",False));continue
                p=verify_policy(policy,policy_key,expected_id=policy_id,min_version=min_version)
                if p!="VERIFIED":
                    conn.send(("REFUSE",p,False));continue
                e=verify_evidence(evidence,evidence_key,artifact_digest=arg.artifact_digest,
                    target=arg.target,policy_id=policy.policy_id,
                    required_controls=policy.required_controls,now=now)
                if e!="VERIFIED":
                    conn.send(("REFUSE",e,False));continue
                if not state["authorised"] or not arg.authority_receipt_id:
                    conn.send(("REFUSE","AUTHORITY_NOT_ESTABLISHED",False));continue
                token=(arg,state["revision"])
                staged[arg.target]=token
                conn.send(("PREPARED",state["revision"],False));continue
            if op=="commit":
                if not isinstance(arg,DeploymentRequest):
                    conn.send(("REFUSE","INVALID_REQUEST",False));continue
                token=staged.pop(arg.target,None)
                if token is None or token[0]!=arg:
                    conn.send(("REFUSE","NO_MATCHING_PREPARATION",False));continue
                if token[1]!=state["revision"] or not state["authorised"]:
                    conn.send(("REFUSE","AUTHORITY_CHANGED_BEFORE_COMMIT",False));continue
                # Re-evaluate evidence and policy at the final reference bind.
                p=verify_policy(policy,policy_key,expected_id=policy_id,min_version=min_version)
                e=verify_evidence(evidence,evidence_key,artifact_digest=arg.artifact_digest,
                    target=arg.target,policy_id=policy.policy_id,
                    required_controls=policy.required_controls,now=now)
                if p!="VERIFIED" or e!="VERIFIED":
                    conn.send(("REFUSE","FINAL_CONTROL_REVALIDATION_FAILED",False));continue
                deployed[arg.target]=arg.artifact_digest
                conn.send(("ALLOW","SIMULATED_CONSEQUENCE_FORMED",True));continue
            conn.send(("REFUSE","UNSUPPORTED_OPERATION",False))
    finally: conn.close()

class FinalBindReferenceExecutor:
    def __init__(self,policy,evidence,*,policy_key,evidence_key,expected_policy_id,min_version,now,authorised):
        ctx=mp.get_context("spawn")
        parent,child=ctx.Pipe()
        self._conn=parent
        self._process=ctx.Process(target=_worker,args=(
            child,policy,evidence,policy_key,evidence_key,expected_policy_id,min_version,now,authorised),
            daemon=True)
        self._process.start()
        child.close()
    def request(self,op,arg):
        self._conn.send((op,arg))
        return self._conn.recv()
    def close(self):
        if self._process.is_alive():
            try: self.request("stop",None)
            finally:self._process.join(timeout=3)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3)
        self._conn.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
