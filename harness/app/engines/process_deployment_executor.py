"""B01: separate-process *reference* deployment controller.

Process separation prevents ordinary mutation of a local client-side dictionary
from changing controller state. It is NOT a security boundary against code with
same-UID process access, IPC handle theft, OS debugging permissions, or access to
an independent deployment actuator. No real deployment occurs.
"""
import multiprocessing as mp
from app.engines.deployment_monitoring_guard import (
    DeploymentRequest, MonitoringPolicy, MonitoringAssessment,
)
from app.engines.simulated_deployment_revalidation import RevalidatedSimulatedController

def _executor_worker(conn, policy, assessment, authorised):
    # State exists only in this subprocess, and is not sent to the client.
    controller = RevalidatedSimulatedController(
        policy, lambda _: assessment, lambda _: authorised
    )
    try:
        while True:
            try:
                message = conn.recv()
            except EOFError:
                break
            if not isinstance(message, tuple) or len(message) != 2:
                conn.send(("ERROR", "INVALID_MESSAGE"))
                continue
            operation, payload = message
            if operation == "stop":
                conn.send(("OK", "STOPPED"))
                break
            if operation == "deploy":
                if not isinstance(payload, DeploymentRequest):
                    conn.send(("ERROR", "INVALID_DEPLOYMENT_REQUEST"))
                    continue
                outcome = controller.deploy(payload)
                conn.send(("OUTCOME", (outcome.decision, outcome.reason_code, outcome.formed)))
            elif operation == "read":
                if not isinstance(payload, str):
                    conn.send(("ERROR", "INVALID_TARGET"))
                    continue
                conn.send(("STATE", controller.deployed_digest(payload)))
            else:
                conn.send(("ERROR", "UNKNOWN_OPERATION"))
    finally:
        conn.close()

class ProcessDeploymentClient:
    """Trusted test owner provisions policy and callbacks before agent requests."""
    def __init__(self, policy: MonitoringPolicy, assessment: MonitoringAssessment,
                 authorised: bool):
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe()
        self._conn = parent
        self._process = ctx.Process(
            target=_executor_worker, args=(child, policy, assessment, authorised),
            daemon=True)
        self._process.start()
        child.close()

    def request(self, operation, payload):
        self._conn.send((operation, payload))
        return self._conn.recv()

    def close(self):
        if self._process.is_alive():
            try:
                self.request("stop", None)
            finally:
                self._process.join(timeout=3)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3)
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
