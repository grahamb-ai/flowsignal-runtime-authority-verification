"""FS-RAW-DENIAL-001: bounded two-adapter remediation candidate.

Both mock adapters submit the SAME canonical request to the existing
FlowSignal gateway before a simulated outcome can be recorded.
No real downstream consequence, payment or shell command is executed.
"""
import base64
import binascii
from dataclasses import dataclass
from app.engines.execution_gateway import validate_execution

@dataclass(frozen=True)
class SyntheticOutcome:
    adapter: str
    status: str
    reason: str
    formed: bool

class GuardedAdapterPair:
    def __init__(self):
        self._events = []

    def invoke(self, adapter, attempt, receipt, representation=None):
        if adapter not in ("A","B"):
            return SyntheticOutcome(adapter,"BLOCKED","UNSUPPORTED_ADAPTER",False)
        if adapter == "B":
            if not isinstance(representation,str):
                return SyntheticOutcome(adapter,"BLOCKED","INVALID_PRESENTATION",False)
            try:
                represented_action=base64.b64decode(
                    representation,validate=True).decode("utf-8")
            except (ValueError,UnicodeDecodeError,binascii.Error):
                return SyntheticOutcome(adapter,"BLOCKED","INVALID_PRESENTATION",False)
            if represented_action != attempt.action:
                return SyntheticOutcome(adapter,"BLOCKED","PRESENTATION_ACTION_MISMATCH",False)
        decision=validate_execution(receipt,attempt)
        if decision.status != "PERMITTED" or decision.execution_permit is None:
            return SyntheticOutcome(adapter,"BLOCKED",decision.reason_code,False)
        # Controlled synthetic journal only. Not a real final-bind consumer.
        self._events.append((attempt.target,attempt.action,adapter))
        return SyntheticOutcome(adapter,"PERMITTED","SYNTHETIC_OUTCOME_RECORDED",True)

    def count(self,target,action):
        return sum(t==target and a==action for t,a,_ in self._events)
